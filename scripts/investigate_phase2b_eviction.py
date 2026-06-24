#!/usr/bin/env python3
"""Phase 2B: vLLM Multi-Session Eviction Trigger Test.

Goal: Create real memory pressure in vLLM to observe eviction/preemption behavior.

Design:
  1. Deploy vLLM server (gpu_util=0.3, APC enabled, LOG_LEVEL=debug)
  2. Phase 1: Serial replay of 3 django sessions (first 10 turns each)
     - Each session accumulates KV; by turn 3-4, single session ~40-50K tokens
  3. Phase 2: Serial replay of 2 sympy sessions (first 5-8 turns each)
     - Adds more KV pressure
  4. Monitor kv_cache_usage_perc — should approach/exceed 100%
  5. If no eviction triggered, continue adding sessions/turns
  6. Record evict/preempt events from server debug log

Key metrics per request:
  - prompt_tokens, cached_tokens, hit_rate
  - TTFT (ms)
  - kv_cache_usage_perc (from Prometheus)

Output: investigation/data/phase2b_eviction_test.json
"""

import asyncio
import json
import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

import pyarrow.ipc as ipc
from openai import AsyncOpenAI

# --- Config ---
BASE_URL = "http://localhost:8000/v1"
API_KEY = "dummy"
MODEL_NAME = "Qwen3-8B"
TRACE_DIR = Path("experiments/vllm_kv_cache/lmcache_traces")
OUTPUT_DIR = Path("experiments/vllm_kv_cache/investigation/data")
SERVER_LOG = Path("experiments/vllm_kv_cache/server_log_phase2b.log")
PER_ROW_METRICS = OUTPUT_DIR / "per_row_metrics.json"

# Session selection: we need sessions with enough turns and different projects
# to create cross-project pressure
DJANGO_SESSIONS = [
    "swebench__django__django-10097__minimax",
    "swebench__django__django-10554__minimax",
    "swebench__django__django-10914__minimax",
]
SYMPY_SESSIONS = [
    "swebench__sympy__sympy-14976__minimax",
    "swebench__sympy__sympy-18199__minimax",
]

# Max context for Qwen3-8B
MAX_CONTEXT = 32768


def load_per_row_metrics():
    """Load Phase 1A per-row metrics for theoretical comparison."""
    if PER_ROW_METRICS.exists():
        with open(PER_ROW_METRICS) as f:
            return json.load(f)
    return []


def get_theoretical_prefix(metrics, session_id, turn_index):
    """Get theoretical prefix_reusable_tokens for a session turn."""
    for r in metrics:
        if r["session_id"] == session_id and r["turn_index"] == turn_index:
            # prefix_reusable = previous turn's total_tokens (if turn > 0)
            return r.get("prefix_reusable_tokens", 0), r.get("total_tokens", 0), r.get("l0_tokens", 0)
    return 0, 0, 0


def load_session_turns(session_id: str):
    """Load all turns for a given session from Arrow files."""
    turns = []
    for i in range(5):
        path = TRACE_DIR / f"data-0000{i}-of-00005.arrow"
        if not path.exists():
            continue
        reader = ipc.open_stream(str(path))
        table = reader.read_all()
        for j in range(table.num_rows):
            sid = table.column("session_id")[j].as_py()
            if sid == session_id:
                msgs = table.column("input")[j].as_py()
                output_len = table.column("output_length")[j].as_py()
                pre_gap = table.column("pre_gap")[j].as_py()
                turns.append({
                    "messages": msgs,
                    "output_length": output_len,
                    "pre_gap": pre_gap,
                })
    return turns


def messages_to_openai_format(messages):
    """Convert Arrow messages to OpenAI API format.

    Handles tool_calls, tool results, etc. by simplifying them
    into text content that preserves the token structure.
    """
    openai_msgs = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "") or ""
        tool_calls = msg.get("tool_calls") or []
        tool_call_id = msg.get("tool_call_id", "")
        name = msg.get("name", "")

        if role == "assistant" and tool_calls:
            if content:
                openai_msgs.append({"role": "assistant", "content": content})
            else:
                tc_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]
                openai_msgs.append({"role": "assistant", "content": f"[Called tools: {', '.join(tc_names)}]"})
        elif role == "tool":
            tool_content = content if content else "[tool result]"
            openai_msgs.append({"role": "user", "content": f"[Tool result from {name or tool_call_id}]: {tool_content[:500]}"})
        elif content:
            openai_msgs.append({"role": role, "content": content})

    return openai_msgs


def estimate_tokens(messages):
    """Rough token estimate: chars / 3.5 (empirical for Qwen3)."""
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return total_chars // 3


async def get_kv_usage():
    """Scrape kv_cache_usage_perc from Prometheus metrics."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:8000/metrics", timeout=5) as resp:
            text = resp.read().decode()
            for line in text.split("\n"):
                if line.startswith("vllm:kv_cache_usage_perc"):
                    return float(line.split()[1])
    except Exception:
        pass
    return None


async def get_prometheus_metrics():
    """Get key Prometheus metrics."""
    import urllib.request
    metrics = {}
    try:
        with urllib.request.urlopen("http://localhost:8000/metrics", timeout=5) as resp:
            text = resp.read().decode()
            for line in text.split("\n"):
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0]
                    try:
                        val = float(parts[1])
                        # Capture key metrics
                        for target in [
                            "kv_cache_usage_perc",
                            "num_preemptions",
                            "prefix_cache_hits",
                            "prefix_cache_queries",
                            "prompt_tokens_cached",
                            "request_prefill_kv_computed_tokens",
                        ]:
                            if target in key:
                                metrics[target] = val
                    except ValueError:
                        pass
    except Exception as e:
        print(f"  Warning: Prometheus fetch failed: {e}")
    return metrics


async def send_request(client, messages, label, max_tokens=5):
    """Send a chat completion request and measure TTFT + cached_tokens."""
    start = time.time()
    try:
        stream = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.0,
            stream=True,
            stream_options={"include_usage": True},
        )

        first_token_time = None
        prompt_tokens = 0
        cached_tokens = 0
        completion_tokens = 0

        async for chunk in stream:
            if first_token_time is None and chunk.choices and chunk.choices[0].delta.content:
                first_token_time = time.time()
            if chunk.usage is not None:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens
                if (chunk.usage.prompt_tokens_details is not None
                        and chunk.usage.prompt_tokens_details.cached_tokens is not None):
                    cached_tokens = chunk.usage.prompt_tokens_details.cached_tokens

        elapsed = time.time() - start
        ttft_ms = round((first_token_time - start) * 1000, 1) if first_token_time else None

        return {
            "label": label,
            "ttft_ms": ttft_ms,
            "total_ms": round(elapsed * 1000, 1),
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "hit_rate": round(cached_tokens / prompt_tokens, 4) if prompt_tokens > 0 else 0,
            "completion_tokens": completion_tokens,
            "success": True,
        }
    except Exception as e:
        return {"label": label, "error": str(e), "success": False}


async def replay_session(client, session_id, max_turns, phase_label, metrics_data):
    """Replay a session turn-by-turn, recording metrics.

    Returns list of per-turn results.
    """
    turns = load_session_turns(session_id)
    if not turns:
        print(f"  ⚠ No turns found for {session_id}")
        return []

    print(f"\n  [{phase_label}] Replaying {session_id[:50]}... ({min(len(turns), max_turns)} turns)")

    results = []
    for turn_idx in range(min(len(turns), max_turns)):
        messages = messages_to_openai_format(turns[turn_idx]["messages"])

        if not messages:
            continue

        est_tokens = estimate_tokens(messages)
        if est_tokens > MAX_CONTEXT - 100:
            print(f"    Turn {turn_idx}: SKIP (est {est_tokens} tokens > {MAX_CONTEXT})")
            continue

        label = f"{phase_label}-T{turn_idx}"
        result = await send_request(client, messages, label, max_tokens=5)

        # Add theoretical comparison
        th_prefix, th_total, th_l0 = get_theoretical_prefix(metrics_data, session_id, turn_idx)
        result["theoretical_prefix_reusable"] = th_prefix
        result["theoretical_total"] = th_total
        result["theoretical_l0"] = th_l0

        # Add KV usage
        kv_usage = await get_kv_usage()
        result["kv_cache_usage_perc"] = kv_usage

        # Status line
        if result["success"]:
            cached = result["cached_tokens"]
            prompt = result["prompt_tokens"]
            hit = result["hit_rate"]
            ttft = result["ttft_ms"]
            kv = kv_usage
            th_p = th_prefix
            print(f"    Turn {turn_idx}: ✅ prompt={prompt}, cached={cached} ({hit:.1%}), "
                  f"TTFT={ttft}ms, KV={kv}%, theory_prefix={th_p}")
        else:
            print(f"    Turn {turn_idx}: ❌ {result.get('error', 'unknown')}")

        results.append(result)

        # Small delay between requests
        await asyncio.sleep(0.3)

    return results


async def replay_session_concurrent(client, session_ids, max_turns, phase_label, metrics_data):
    """Replay multiple sessions concurrently (asyncio.gather), first turn only.

    Used to test concurrent prefix sharing (Phase 2B extension).
    """
    print(f"\n  [{phase_label}] Sending {len(session_ids)} concurrent first turns...")

    tasks = []
    for session_id in session_ids:
        turns = load_session_turns(session_id)
        if not turns:
            continue
        messages = messages_to_openai_format(turns[0]["messages"])
        if not messages:
            continue
        label = f"{phase_label}-{session_id[:30]}"
        tasks.append(send_request(client, messages, label, max_tokens=5))

    results = await asyncio.gather(*tasks)

    # Add KV usage and theoretical data
    for i, (session_id, result) in enumerate(zip(session_ids, results)):
        kv_usage = await get_kv_usage()
        result["kv_cache_usage_perc"] = kv_usage
        th_prefix, th_total, th_l0 = get_theoretical_prefix(metrics_data, session_id, 0)
        result["theoretical_prefix_reusable"] = th_prefix
        result["theoretical_total"] = th_total
        result["theoretical_l0"] = th_l0

        if result["success"]:
            print(f"    {session_id[:40]}: prompt={result['prompt_tokens']}, "
                  f"cached={result['cached_tokens']} ({result['hit_rate']:.1%}), "
                  f"TTFT={result['ttft_ms']}ms, KV={kv_usage}%")
        else:
            print(f"    {session_id[:40]}: ❌ {result.get('error', 'unknown')}")

    return list(results)


def parse_server_log(log_path, start_time=None):
    """Parse vLLM server debug log for eviction/preemption events."""
    KEYWORDS = {
        "preempt": "preempt",
        "Preempting": "preempt",
        "swap_in": "swap_in",
        "swap_out": "swap_out",
        "swapping": "swap",
        "evict": "evict",
        "Evicting": "evict",
        "offload_store": "offload_store",
        "offload_load": "offload_load",
        "storing": "offload_store",
        "loading": "offload_load",
        "recompute": "recompute",
        "Recomputing": "recompute",
        "cache_full_blocks": "cache_register",
        "free_blocks": "free_blocks",
        "_maybe_evict": "evict_check",
    }

    events = []
    try:
        with open(log_path, "r", errors="ignore") as f:
            for line in f:
                for keyword, event_type in KEYWORDS.items():
                    if keyword in line:
                        t = 0.0
                        if len(line) > 23:
                            try:
                                ts_str = line[:23].strip()
                                from datetime import timezone
                                ts = datetime.fromisoformat(
                                    ts_str.replace(",", ".")
                                ).replace(tzinfo=timezone.utc).timestamp()
                                if start_time:
                                    t = round(ts - start_time, 3)
                                else:
                                    t = round(ts, 3)
                            except (ValueError, IndexError):
                                pass

                        events.append({
                            "t": t,
                            "event": event_type,
                            "detail": line.strip()[:300],
                        })
                        break  # One event per line
    except FileNotFoundError:
        print(f"  ⚠ Server log not found: {log_path}")

    return events


def summarize_log_events(events):
    """Summarize log events by type."""
    summary = {}
    for e in events:
        etype = e["event"]
        if etype not in summary:
            summary[etype] = {"count": 0, "first_t": e["t"], "last_t": e["t"], "examples": []}
        summary[etype]["count"] += 1
        summary[etype]["last_t"] = e["t"]
        if len(summary[etype]["examples"]) < 3:
            summary[etype]["examples"].append(e["detail"][:200])
    return summary


async def main():
    print("=" * 70)
    print("Phase 2B: vLLM Multi-Session Eviction Trigger Test")
    print("=" * 70)
    print(f"Time: {datetime.now().isoformat()}")
    print(f"GPU KV capacity: ~44,000 tokens (gpu_util=0.3, H800)")
    print(f"Expected: kv_cache_usage_perc should approach 100% with enough load")

    # Load Phase 1A metrics for theoretical comparison
    metrics_data = load_per_row_metrics()
    print(f"Loaded {len(metrics_data)} per-row metrics from Phase 1A")

    client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)

    # Verify server is running
    try:
        await client.models.list()
        print("✅ vLLM server is running")
    except Exception as e:
        print(f"❌ vLLM server not available: {e}")
        print("Please start with: bash scripts/run_vllm_server.sh 0.3")
        return 1

    # Record start time for log correlation
    exp_start_time = time.time()

    # Get baseline Prometheus metrics
    baseline_metrics = await get_prometheus_metrics()
    print(f"Baseline: KV usage={baseline_metrics.get('kv_cache_usage_perc', '?')}%, "
          f"preemptions={baseline_metrics.get('num_preemptions', '?')}")

    all_results = {}
    phase_metrics = {}

    # ================================================================
    # Phase 1: Serial replay of 3 django sessions (10 turns each)
    # ================================================================
    print("\n" + "=" * 70)
    print("PHASE 1: Serial replay — 3 django sessions × 10 turns")
    print("=" * 70)
    print("Expected: KV usage grows with each session/turn")
    print("Target: kv_cache_usage_perc > 80% by end of Phase 1")

    phase1_results = []
    for i, session_id in enumerate(DJANGO_SESSIONS):
        label = f"D{i+1}"
        results = await replay_session(client, session_id, max_turns=10,
                                        phase_label=label, metrics_data=metrics_data)
        phase1_results.extend(results)

    phase1_kv = await get_kv_usage()
    phase1_prom = await get_prometheus_metrics()
    phase_metrics["phase1_end"] = phase1_prom
    print(f"\n  Phase 1 complete: KV usage = {phase1_kv}%")
    print(f"  Preemptions so far: {phase1_prom.get('num_preemptions', 0) - baseline_metrics.get('num_preemptions', 0)}")

    all_results["phase1_django_serial"] = phase1_results

    # ================================================================
    # Phase 2: Serial replay of 2 sympy sessions (8 turns each)
    # ================================================================
    print("\n" + "=" * 70)
    print("PHASE 2: Serial replay — 2 sympy sessions × 8 turns")
    print("=" * 70)
    print("Expected: More KV pressure; if not enough, we'll add more sessions")

    phase2_results = []
    for i, session_id in enumerate(SYMPY_SESSIONS):
        label = f"S{i+1}"
        results = await replay_session(client, session_id, max_turns=8,
                                        phase_label=label, metrics_data=metrics_data)
        phase2_results.extend(results)

    phase2_kv = await get_kv_usage()
    phase2_prom = await get_prometheus_metrics()
    phase_metrics["phase2_end"] = phase2_prom
    print(f"\n  Phase 2 complete: KV usage = {phase2_kv}%")
    print(f"  Preemptions so far: {phase2_prom.get('num_preemptions', 0) - baseline_metrics.get('num_preemptions', 0)}")

    all_results["phase2_sympy_serial"] = phase2_results

    # ================================================================
    # Check: Did we trigger eviction?
    # ================================================================
    eviction_triggered = phase2_kv is not None and phase2_kv > 80

    if not eviction_triggered:
        print("\n" + "=" * 70)
        print("⚠ EVICTION NOT YET TRIGGERED (KV usage < 80%)")
        print("Adding more sessions to increase pressure...")
        print("=" * 70)

        # Phase 2b: Add more django sessions with more turns
        EXTRA_SESSIONS = [
            "swebench__django__django-10973__minimax",
            "swebench__django__django-11039__minimax",
            "swebench__django__django-11179__minimax",
        ]

        phase2b_results = []
        for i, session_id in enumerate(EXTRA_SESSIONS):
            label = f"DX{i+1}"
            results = await replay_session(client, session_id, max_turns=10,
                                            phase_label=label, metrics_data=metrics_data)
            phase2b_results.extend(results)

        phase2b_kv = await get_kv_usage()
        phase2b_prom = await get_prometheus_metrics()
        phase_metrics["phase2b_end"] = phase2b_prom
        print(f"\n  Phase 2b complete: KV usage = {phase2b_kv}%")
        eviction_triggered = phase2b_kv is not None and phase2b_kv > 80

        all_results["phase2b_extra_django"] = phase2b_results

    # ================================================================
    # Phase 3: Test prefix hit after pressure — send new django request
    # ================================================================
    print("\n" + "=" * 70)
    print("PHASE 3: Prefix hit test after memory pressure")
    print("=" * 70)
    print("Sending new django session first turn to check if L0 is still cached")

    # Use a django session we haven't sent yet
    test_session = "swebench__django__django-16379__minimax"
    phase3_results = await replay_session(client, test_session, max_turns=1,
                                           phase_label="TEST-DJANGO", metrics_data=metrics_data)
    all_results["phase3_prefix_test"] = phase3_results

    phase3_kv = await get_kv_usage()
    phase3_prom = await get_prometheus_metrics()
    phase_metrics["phase3_end"] = phase3_prom
    print(f"\n  Phase 3 complete: KV usage = {phase3_kv}%")

    # Check L0 hit rate on the test request
    if phase3_results and phase3_results[0]["success"]:
        cached = phase3_results[0]["cached_tokens"]
        l0_tokens = phase3_results[0].get("theoretical_l0", 6157)
        l0_hit_pct = cached / l0_tokens if l0_tokens > 0 else 0
        print(f"  L0 hit: {cached}/{l0_tokens} = {l0_hit_pct:.1%}")
        if cached < l0_tokens * 0.8:
            print(f"  ⚠ L0 partially or fully evicted! Only {cached}/{l0_tokens} cached")
        else:
            print(f"  ✅ L0 still mostly cached")

    # ================================================================
    # Phase 4: Concurrent requests under pressure
    # ================================================================
    print("\n" + "=" * 70)
    print("PHASE 4: Concurrent requests under memory pressure")
    print("=" * 70)
    print("Sending 3 django + 2 sympy first turns concurrently")

    concurrent_sessions = DJANGO_SESSIONS[:3] + SYMPY_SESSIONS[:2]
    phase4_results = await replay_session_concurrent(
        client, concurrent_sessions, max_turns=1,
        phase_label="CONC", metrics_data=metrics_data
    )
    all_results["phase4_concurrent"] = phase4_results

    phase4_kv = await get_kv_usage()
    phase4_prom = await get_prometheus_metrics()
    phase_metrics["phase4_end"] = phase4_prom
    print(f"\n  Phase 4 complete: KV usage = {phase4_kv}%")
    print(f"  Total preemptions: {phase4_prom.get('num_preemptions', 0) - baseline_metrics.get('num_preemptions', 0)}")

    # ================================================================
    # Final Prometheus metrics
    # ================================================================
    final_prom = await get_prometheus_metrics()
    total_preemptions = final_prom.get("num_preemptions", 0) - baseline_metrics.get("num_preemptions", 0)
    total_prefix_hits = final_prom.get("prefix_cache_hits", 0) - baseline_metrics.get("prefix_cache_hits", 0)
    total_prefix_queries = final_prom.get("prefix_cache_queries", 0) - baseline_metrics.get("prefix_cache_queries", 0)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  KV usage: {final_prom.get('kv_cache_usage_perc', '?')}%")
    print(f"  Total preemptions: {total_preemptions}")
    print(f"  Prefix cache hits: {total_prefix_hits}")
    print(f"  Prefix cache queries: {total_prefix_queries}")
    print(f"  Eviction triggered: {'YES ✅' if eviction_triggered else 'NO ⚠'}")

    # ================================================================
    # Parse server log for eviction events
    # ================================================================
    print("\n" + "=" * 70)
    print("Server Log Analysis")
    print("=" * 70)

    # Find the most recent server log
    log_path = None
    for candidate in [
        SERVER_LOG,
        Path("experiments/vllm_kv_cache/server.log"),
        Path("experiments/vllm_kv_cache/server_log_debug_4.5_on.log"),
    ]:
        if candidate.exists():
            log_path = candidate
            break

    if log_path:
        log_events = parse_server_log(log_path)
        log_summary = summarize_log_events(log_events)
        print(f"  Log: {log_path}")
        for etype, info in sorted(log_summary.items()):
            print(f"  {etype}: {info['count']} events (t={info['first_t']:.1f}s - {info['last_t']:.1f}s)")
            for ex in info["examples"][:2]:
                print(f"    → {ex[:120]}")
    else:
        log_events = []
        log_summary = {}
        print("  ⚠ No server log found. Start server with LOG_LEVEL=debug to capture eviction events.")

    # ================================================================
    # Save results
    # ================================================================
    output = {
        "experiment": "phase2b_eviction_test",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "gpu_util": 0.3,
            "gpu_kv_capacity_tokens": 44000,
            "apc_enabled": True,
            "block_size": 16,
        },
        "baseline_metrics": baseline_metrics,
        "final_metrics": final_prom,
        "phase_metrics": phase_metrics,
        "summary": {
            "eviction_triggered": eviction_triggered,
            "final_kv_usage_perc": final_prom.get("kv_cache_usage_perc"),
            "total_preemptions": total_preemptions,
            "total_prefix_hits": total_prefix_hits,
            "total_prefix_queries": total_prefix_queries,
        },
        "log_summary": log_summary,
        "log_events_count": len(log_events),
        "results": all_results,
    }

    output_path = OUTPUT_DIR / "phase2b_eviction_test.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Saved: {output_path}")

    # ================================================================
    # Validation checks
    # ================================================================
    print("\n" + "=" * 70)
    print("VALIDATION")
    print("=" * 70)

    checks_passed = 0
    checks_total = 0

    # Check 1: KV usage should have increased
    checks_total += 1
    initial_kv = baseline_metrics.get("kv_cache_usage_perc", 0) or 0
    final_kv = final_prom.get("kv_cache_usage_perc", 0) or 0
    if final_kv > initial_kv:
        print(f"  ✅ KV usage increased: {initial_kv}% → {final_kv}%")
        checks_passed += 1
    else:
        print(f"  ❌ KV usage did not increase: {initial_kv}% → {final_kv}%")

    # Check 2: Serial sessions should have high hit rates (turn > 0)
    checks_total += 1
    serial_results = phase1_results + phase2_results
    hit_rates = [r["hit_rate"] for r in serial_results if r["success"] and not r["label"].endswith("-T0")]
    if hit_rates:
        avg_hit = sum(hit_rates) / len(hit_rates)
        if avg_hit > 0.5:
            print(f"  ✅ Serial hit rates reasonable: avg={avg_hit:.1%} across {len(hit_rates)} requests")
            checks_passed += 1
        else:
            print(f"  ⚠ Serial hit rates low: avg={avg_hit:.1%} — may indicate eviction of shared prefix")
    else:
        print(f"  ⚠ No serial turn>0 results to check")

    # Check 3: Concurrent requests should have lower hit rates
    checks_total += 1
    if phase4_results:
        conc_hits = [r["hit_rate"] for r in phase4_results if r["success"]]
        if conc_hits:
            avg_conc = sum(conc_hits) / len(conc_hits)
            print(f"  ℹ Concurrent hit rates: avg={avg_conc:.1%}")
            checks_passed += 1  # Informational, always "pass"

    # Check 4: Preemption count
    checks_total += 1
    if total_preemptions > 0:
        print(f"  ✅ Preemptions detected: {total_preemptions}")
        checks_passed += 1
    else:
        print(f"  ⚠ No preemptions detected — may need more load or lower gpu_util")

    # Check 5: Phase 3 prefix test — L0 cached?
    checks_total += 1
    if phase3_results and phase3_results[0]["success"]:
        cached = phase3_results[0]["cached_tokens"]
        l0 = phase3_results[0].get("theoretical_l0", 6157)
        if cached >= l0 * 0.8:
            print(f"  ✅ L0 still cached after pressure: {cached}/{l0}")
            checks_passed += 1
        else:
            print(f"  ⚠ L0 evicted after pressure: {cached}/{l0} (this IS the pain point!)")
            checks_passed += 1  # This is actually the finding we want!

    print(f"\n  Checks: {checks_passed}/{checks_total} passed")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
