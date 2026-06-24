#!/usr/bin/env python3
"""Phase 3: Per-Pain-Point Deep Analysis with vLLM Verification.

Each pain point has:
  - Theoretical analysis (from Phase 1A/2A data)
  - vLLM measured verification (real inference)

Pain Points:
  P1: Concurrent requests cannot share prefix cache (M3)
  P2: LRU may evict shared system prompt L0 (M5/M6)
  P3: Preemption causes complete decode output loss (M8)
  P4: Prefix growth causes increasing memory pressure (M4/M7)
  P5: Block boundary waste on short Agent turns (M1/M2)
  P6: GPU prefix cache and offload tier are independently managed (M9)
  P7: No scheduling awareness causes reduced prefix reuse (M3 extension)

Each experiment REQUIRES a fresh vLLM server deployment to ensure clean KV cache.

Output: investigation/data/phase3_pain_points.json
"""

import asyncio
import json
import os
import sys
import time
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
PER_ROW_METRICS = OUTPUT_DIR / "per_row_metrics.json"
SIM_RESULTS = OUTPUT_DIR / "simulation_results.json"
MAX_CONTEXT = 32768

# Session IDs for experiments
DJANGO_SESSIONS = [
    "swebench__django__django-10097__minimax",
    "swebench__django__django-10554__minimax",
    "swebench__django__django-10914__minimax",
    "swebench__django__django-10973__minimax",
    "swebench__django__django-11039__minimax",
]
SYMPY_SESSIONS = [
    "swebench__sympy__sympy-14976__minimax",
    "swebench__sympy__sympy-18199__minimax",
    "swebench__sympy__sympy-18698__minimax",
]


# ============================================================================
# Utility Functions (shared with Phase 2B)
# ============================================================================

def load_per_row_metrics():
    if PER_ROW_METRICS.exists():
        with open(PER_ROW_METRICS) as f:
            return json.load(f)
    return []


def load_sim_results():
    if SIM_RESULTS.exists():
        with open(SIM_RESULTS) as f:
            return json.load(f)
    return {}


def get_theoretical_prefix(metrics, session_id, turn_index):
    for r in metrics:
        if r["session_id"] == session_id and r["turn_index"] == turn_index:
            return r.get("prefix_reusable_tokens", 0), r.get("total_tokens", 0), r.get("l0_tokens", 0)
    return 0, 0, 0


def load_session_turns(session_id: str):
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
                turns.append({"messages": msgs, "output_length": output_len})
    return turns


def messages_to_openai_format(messages):
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
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return total_chars // 3


async def get_prometheus_metrics():
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
                        for target in [
                            "kv_cache_usage_perc", "num_preemptions",
                            "prefix_cache_hits", "prefix_cache_queries",
                            "prompt_tokens_cached",
                            "request_prefill_kv_computed_tokens",
                            "kv_offload_store_bytes", "kv_offload_load_bytes",
                            "kv_offload_stores_skipped",
                        ]:
                            if target in key:
                                metrics[target] = val
                    except ValueError:
                        pass
    except Exception:
        pass
    return metrics


async def send_request(client, messages, label, max_tokens=5):
    start = time.time()
    try:
        stream = await client.chat.completions.create(
            model=MODEL_NAME, messages=messages, max_tokens=max_tokens,
            temperature=0.0, stream=True, stream_options={"include_usage": True},
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
            "label": label, "ttft_ms": ttft_ms,
            "total_ms": round(elapsed * 1000, 1),
            "prompt_tokens": prompt_tokens, "cached_tokens": cached_tokens,
            "hit_rate": round(cached_tokens / prompt_tokens, 4) if prompt_tokens > 0 else 0,
            "completion_tokens": completion_tokens, "success": True,
        }
    except Exception as e:
        return {"label": label, "error": str(e), "success": False}


async def replay_serial(client, session_ids, max_turns, label_prefix, metrics_data):
    """Serial replay of multiple sessions, recording per-turn metrics."""
    all_results = []
    for i, sid in enumerate(session_ids):
        turns = load_session_turns(sid)
        if not turns:
            continue
        label = f"{label_prefix}-S{i+1}"
        print(f"    [{label}] {sid[:50]} ({min(len(turns), max_turns)} turns)")
        for t_idx in range(min(len(turns), max_turns)):
            msgs = messages_to_openai_format(turns[t_idx]["messages"])
            if not msgs:
                continue
            est = estimate_tokens(msgs)
            if est > MAX_CONTEXT - 100:
                print(f"      Turn {t_idx}: SKIP (est {est} > {MAX_CONTEXT})")
                continue
            result = await send_request(client, msgs, f"{label}-T{t_idx}")
            th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, t_idx)
            result["theoretical_prefix_reusable"] = th_p
            result["theoretical_total"] = th_t
            result["theoretical_l0"] = th_l0
            prom = await get_prometheus_metrics()
            result["kv_cache_usage_perc"] = prom.get("kv_cache_usage_perc")
            if result["success"]:
                print(f"      Turn {t_idx}: prompt={result['prompt_tokens']}, "
                      f"cached={result['cached_tokens']} ({result['hit_rate']:.1%}), "
                      f"TTFT={result['ttft_ms']}ms, KV={prom.get('kv_cache_usage_perc', '?')}%")
            all_results.append(result)
            await asyncio.sleep(0.3)
    return all_results


async def send_concurrent(client, session_ids, label_prefix, metrics_data, turn_idx=0):
    """Send multiple sessions' first turns concurrently."""
    tasks = []
    labels = []
    for i, sid in enumerate(session_ids):
        turns = load_session_turns(sid)
        if not turns or turn_idx >= len(turns):
            continue
        msgs = messages_to_openai_format(turns[turn_idx]["messages"])
        if not msgs:
            continue
        label = f"{label_prefix}-S{i+1}"
        tasks.append(send_request(client, msgs, label))
        labels.append((sid, i))

    results = await asyncio.gather(*tasks)

    # Enrich with theoretical data
    for (sid, _), result in zip(labels, results):
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, turn_idx)
        result["theoretical_prefix_reusable"] = th_p
        result["theoretical_total"] = th_t
        result["theoretical_l0"] = th_l0
        if result["success"]:
            print(f"      {sid[:40]}: prompt={result['prompt_tokens']}, "
                  f"cached={result['cached_tokens']} ({result['hit_rate']:.1%}), "
                  f"TTFT={result['ttft_ms']}ms")
    return list(results)


# ============================================================================
# P1: Concurrent requests cannot share prefix cache
# ============================================================================

async def run_p1(client, metrics_data):
    """P1: Concurrent vs serial prefix sharing comparison.

    Theory:
      - N concurrent requests sharing L0+L1 should all see cached_tokens=0
        because blocks aren't registered until after the scheduling step.
      - Same N requests sent serially should see cached_tokens ≈ L0+L1
        for requests 2..N.

    Method:
      1. Concurrent: asyncio.gather 3 django sessions' first turns
      2. Reset server (requires external restart)
      3. Serial: send same 3 sessions sequentially
      4. Compare cached_tokens and TTFT
    """
    print("\n" + "=" * 70)
    print("P1: Concurrent requests cannot share prefix cache (M3)")
    print("=" * 70)

    sessions = DJANGO_SESSIONS[:3]
    result = {"pain_point": "P1_concurrent_prefix_sharing", "theory": {}, "measured": {}}

    # Theory: compute expected hit rates
    for i, sid in enumerate(sessions):
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, 0)
        result["theory"][sid[:40]] = {
            "serial_expected_cached": th_t if i > 0 else 0,  # 2nd+ request should hit first's prefix
            "concurrent_expected_cached": 0,  # No cross-request sharing in concurrent mode
            "l0_tokens": th_l0,
            "l1_tokens": th_t - th_l0,
        }

    # P1-A: Concurrent send
    print("\n  [P1-A] Sending 3 django sessions concurrently (first turn)...")
    conc_results = await send_concurrent(client, sessions, "P1-CONC", metrics_data, turn_idx=0)
    result["measured"]["concurrent"] = conc_results

    # P1-B: Wait a moment, then send serially (same server — prefix from concurrent should be cached now)
    print("\n  [P1-B] Sending 3 django sessions serially (first turn, AFTER concurrent)...")
    serial_results = []
    for i, sid in enumerate(sessions):
        turns = load_session_turns(sid)
        if not turns:
            continue
        msgs = messages_to_openai_format(turns[0]["messages"])
        if not msgs:
            continue
        r = await send_request(client, msgs, f"P1-SER-S{i+1}")
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, 0)
        r["theoretical_prefix_reusable"] = th_p
        r["theoretical_total"] = th_t
        r["theoretical_l0"] = th_l0
        if r["success"]:
            print(f"    {sid[:40]}: prompt={r['prompt_tokens']}, "
                  f"cached={r['cached_tokens']} ({r['hit_rate']:.1%})")
        serial_results.append(r)
        await asyncio.sleep(0.3)
    result["measured"]["serial_after_concurrent"] = serial_results

    # Analysis
    conc_cached = [r["cached_tokens"] for r in conc_results if r["success"]]
    serial_cached = [r["cached_tokens"] for r in serial_results if r["success"]]

    result["analysis"] = {
        "concurrent_avg_cached": round(sum(conc_cached) / len(conc_cached), 1) if conc_cached else 0,
        "serial_avg_cached": round(sum(serial_cached) / len(serial_cached), 1) if serial_cached else 0,
        "concurrent_avg_ttft_ms": round(sum(r["ttft_ms"] for r in conc_results if r["success"] and r.get("ttft_ms")) / max(1, sum(1 for r in conc_results if r["success"] and r.get("ttft_ms"))), 1),
        "serial_avg_ttft_ms": round(sum(r["ttft_ms"] for r in serial_results if r["success"] and r.get("ttft_ms")) / max(1, sum(1 for r in serial_results if r["success"] and r.get("ttft_ms"))), 1),
    }

    # The key finding: concurrent requests see 0% hit on shared prefix
    # while serial requests (after warm-up) see high hit rate
    if conc_cached and serial_cached:
        gap = result["analysis"]["serial_avg_cached"] - result["analysis"]["concurrent_avg_cached"]
        result["analysis"]["cache_hit_gap_tokens"] = gap
        print(f"\n  📊 P1 Result: Concurrent avg_cached={result['analysis']['concurrent_avg_cached']}, "
              f"Serial avg_cached={result['analysis']['serial_avg_cached']}, Gap={gap} tokens")

    return result


# ============================================================================
# P2: LRU may evict shared system prompt L0
# ============================================================================

async def run_p2(client, metrics_data):
    """P2: LRU eviction of shared L0 under memory pressure.

    Theory:
      - L0 blocks are shared by all requests → high ref_cnt while requests running
      - But once all requests using L0 complete, L0 blocks go to free queue
      - If new project requests arrive, L0 blocks may be evicted (LRU = oldest unused)

    Method:
      1. Phase 1: Send 5 django sessions (10 turns each) → L0+L1 cached
      2. Phase 2: Send 5 sympy sessions (10 turns each) → pressure L0 out
      3. Phase 3: Send 1 new django session → check cached_tokens for L0
    """
    print("\n" + "=" * 70)
    print("P2: LRU may evict shared system prompt L0 (M5/M6)")
    print("=" * 70)

    result = {"pain_point": "P2_lru_evicts_l0", "theory": {}, "measured": {}}

    # Theory: L0 tokens that should be preserved
    for sid in DJANGO_SESSIONS[:1]:
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, 0)
        result["theory"]["l0_tokens"] = th_l0
        result["theory"]["l1_tokens"] = th_t - th_l0
        break

    # Phase 1: Fill cache with django sessions
    print("\n  [P2-Phase1] Sending 5 django sessions (10 turns each)...")
    p1_results = await replay_serial(client, DJANGO_SESSIONS[:5], 10, "P2-DJ", metrics_data)
    result["measured"]["phase1_django"] = p1_results

    p1_prom = await get_prometheus_metrics()
    result["measured"]["phase1_kv_usage"] = p1_prom.get("kv_cache_usage_perc")
    print(f"  KV usage after Phase 1: {p1_prom.get('kv_cache_usage_perc', '?')}%")

    # Phase 2: Add sympy sessions to create pressure
    print("\n  [P2-Phase2] Sending 5 sympy sessions (10 turns each)...")
    p2_results = await replay_serial(client, SYMPY_SESSIONS[:3], 10, "P2-SY", metrics_data)
    result["measured"]["phase2_sympy"] = p2_results

    p2_prom = await get_prometheus_metrics()
    result["measured"]["phase2_kv_usage"] = p2_prom.get("kv_cache_usage_perc")
    print(f"  KV usage after Phase 2: {p2_prom.get('kv_cache_usage_perc', '?')}%")

    # If KV usage still low, add more sessions
    kv_after_p2 = p2_prom.get("kv_cache_usage_perc", 0) or 0
    if kv_after_p2 < 70:
        print("  KV usage < 70%, adding more sessions...")
        extra = await replay_serial(client, DJANGO_SESSIONS[3:5], 10, "P2-DX", metrics_data)
        result["measured"]["phase2b_extra"] = extra

    # Phase 3: Test if L0 is still cached
    print("\n  [P2-Phase3] Sending new django session to check L0 cache...")
    test_sid = "swebench__django__django-16379__minimax"
    turns = load_session_turns(test_sid)
    if turns:
        msgs = messages_to_openai_format(turns[0]["messages"])
        test_result = await send_request(client, msgs, "P2-TEST")
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, test_sid, 0)
        test_result["theoretical_l0"] = th_l0
        test_result["theoretical_total"] = th_t
        result["measured"]["phase3_test"] = test_result

        cached = test_result.get("cached_tokens", 0) if test_result["success"] else 0
        l0_tokens = th_l0
        l0_hit_pct = cached / l0_tokens if l0_tokens > 0 else 0

        result["analysis"] = {
            "l0_tokens": l0_tokens,
            "l0_cached": cached,
            "l0_hit_pct": round(l0_hit_pct, 4),
            "l0_evicted": cached < l0_tokens * 0.8,
        }

        if cached < l0_tokens * 0.8:
            print(f"  ⚠ L0 EVICTED: only {cached}/{l0_tokens} = {l0_hit_pct:.1%} cached!")
        else:
            print(f"  L0 still cached: {cached}/{l0_tokens} = {l0_hit_pct:.1%}")

    return result


# ============================================================================
# P3: Preemption causes complete decode output loss
# ============================================================================

async def run_p3(client, metrics_data):
    """P3: Preemption causes decode output loss.

    Theory:
      - When a request is preempted, num_computed_tokens = 0
      - All decode KV blocks are lost (not offloaded with offload_prompt_only=True)
      - Recovery requires full recomputation of all tokens

    Method:
      1. Run 1 session for 10+ turns (accumulate decode KV)
      2. Send many concurrent requests to trigger preemption
      3. Check num_preemptions > 0
      4. Measure TTFT of preempted request's next attempt vs cold start
    """
    print("\n" + "=" * 70)
    print("P3: Preemption causes complete decode output loss (M8)")
    print("=" * 70)

    result = {"pain_point": "P3_preemption_decode_loss", "theory": {}, "measured": {}}

    baseline_prom = await get_prometheus_metrics()
    result["measured"]["baseline_preemptions"] = baseline_prom.get("num_preemptions", 0)

    # Phase 1: Long session to build up decode KV
    print("\n  [P3-Phase1] Running 1 django session for 10 turns (building decode KV)...")
    p1_results = await replay_serial(client, [DJANGO_SESSIONS[0]], 10, "P3-LONG", metrics_data)
    result["measured"]["phase1_long_session"] = p1_results

    p1_prom = await get_prometheus_metrics()
    result["measured"]["phase1_kv_usage"] = p1_prom.get("kv_cache_usage_perc")
    print(f"  KV usage: {p1_prom.get('kv_cache_usage_perc', '?')}%")

    # Phase 2: Concurrent requests to create pressure
    print("\n  [P3-Phase2] Sending concurrent requests to trigger preemption...")
    # Send 5 django + 3 sympy first turns concurrently
    all_sessions = DJANGO_SESSIONS[:5] + SYMPY_SESSIONS[:3]
    p2_results = await send_concurrent(client, all_sessions, "P3-PRESS", metrics_data)
    result["measured"]["phase2_pressure"] = p2_results

    p2_prom = await get_prometheus_metrics()
    total_preemptions = p2_prom.get("num_preemptions", 0) - baseline_prom.get("num_preemptions", 0)
    result["measured"]["phase2_kv_usage"] = p2_prom.get("kv_cache_usage_perc")
    result["measured"]["total_preemptions"] = total_preemptions

    print(f"  KV usage: {p2_prom.get('kv_cache_usage_perc', '?')}%")
    print(f"  Preemptions: {total_preemptions}")

    # If no preemptions, send more concurrent requests
    if total_preemptions == 0:
        print("  No preemptions yet, sending more concurrent requests...")
        # Send second turns concurrently for more pressure
        p2b_results = await send_concurrent(client, DJANGO_SESSIONS[:5], "P3-PRESS2", metrics_data, turn_idx=1)
        result["measured"]["phase2b_more_pressure"] = p2b_results

        p2b_prom = await get_prometheus_metrics()
        total_preemptions = p2b_prom.get("num_preemptions", 0) - baseline_prom.get("num_preemptions", 0)
        result["measured"]["total_preemptions"] = total_preemptions
        print(f"  Preemptions after more pressure: {total_preemptions}")

    # Compute theoretical decode output loss
    # From Phase 1A: output_length per turn
    session_metrics = [r for r in metrics_data if r["session_id"] == DJANGO_SESSIONS[0]]
    decode_cumulative = 0
    for r in session_metrics[:10]:
        decode_cumulative += r.get("output_length", 0)

    result["theory"] = {
        "decode_output_cumulative_10_turns": decode_cumulative,
        "preemption_loss_tokens": decode_cumulative,  # ALL decode output would be lost
        "prefill_recovery_possible": True,  # Prefix cache can recover prefill KV
    }

    result["analysis"] = {
        "preemptions_triggered": total_preemptions > 0,
        "total_preemptions": total_preemptions,
        "potential_decode_loss_tokens": decode_cumulative,
    }

    if total_preemptions > 0:
        print(f"  ✅ Preemptions triggered: {total_preemptions}")
        print(f"  Potential decode loss: {decode_cumulative} tokens")
    else:
        print(f"  ⚠ No preemptions triggered. Need more load or lower gpu_util.")

    return result


# ============================================================================
# P4: Prefix growth causes increasing memory pressure
# ============================================================================

async def run_p4(client, metrics_data):
    """P4: Prefix growth tracking — KV usage over turns.

    Theory:
      - Each turn adds incremental KV tokens
      - Session median growth ratio is 3.2x (first → last turn)
      - 13.6% of sessions exceed 44K token GPU capacity

    Method:
      1. Run 3 sessions concurrently, tracking KV usage per turn
      2. Compare with theoretical growth from Phase 1A
    """
    print("\n" + "=" * 70)
    print("P4: Prefix growth causes increasing memory pressure (M4/M7)")
    print("=" * 70)

    result = {"pain_point": "P4_prefix_growth_pressure", "theory": {}, "measured": {}}

    # Theory: compute per-turn KV footprint from Phase 1A
    for sid in DJANGO_SESSIONS[:3]:
        session_rows = [r for r in metrics_data if r["session_id"] == sid]
        cumulative = 0
        theory_growth = []
        for r in session_rows[:15]:
            cumulative += r["total_tokens"]
            theory_growth.append({
                "turn": r["turn_index"],
                "incremental_tokens": r["total_tokens"],
                "cumulative_tokens": cumulative,
            })
        result["theory"][sid[:40]] = theory_growth

    # Measured: replay 3 sessions, tracking KV usage
    print("\n  [P4] Replaying 3 django sessions, tracking KV usage per turn...")

    # Send turns interleaved across sessions to simulate concurrent sessions
    max_turns = 10
    measured_growth = {i: [] for i in range(3)}
    kv_timeline = []

    for t in range(max_turns):
        for s_idx, sid in enumerate(DJANGO_SESSIONS[:3]):
            turns = load_session_turns(sid)
            if t >= len(turns):
                continue
            msgs = messages_to_openai_format(turns[t]["messages"])
            if not msgs or estimate_tokens(msgs) > MAX_CONTEXT - 100:
                continue

            r = await send_request(client, msgs, f"P4-S{s_idx+1}-T{t}")
            prom = await get_prometheus_metrics()
            r["kv_cache_usage_perc"] = prom.get("kv_cache_usage_perc")
            r["turn_index"] = t
            r["session_index"] = s_idx

            th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, t)
            r["theoretical_total"] = th_t

            measured_growth[s_idx].append(r)
            kv_timeline.append({
                "turn": t, "session": s_idx,
                "kv_usage": prom.get("kv_cache_usage_perc"),
                "prompt_tokens": r.get("prompt_tokens"),
                "cached_tokens": r.get("cached_tokens"),
            })

            if r["success"]:
                print(f"    S{s_idx+1}-T{t}: prompt={r['prompt_tokens']}, "
                      f"cached={r['cached_tokens']}, KV={prom.get('kv_cache_usage_perc', '?')}%")

        await asyncio.sleep(0.2)

    result["measured"]["per_session"] = {f"session_{i}": measured_growth[i] for i in range(3)}
    result["measured"]["kv_timeline"] = kv_timeline

    # Analysis: find when KV exceeds capacity
    max_kv = max((e["kv_usage"] or 0) for e in kv_timeline) if kv_timeline else 0
    result["analysis"] = {
        "max_kv_usage_perc": max_kv,
        "exceeds_80pct": max_kv > 80,
        "exceeds_100pct": max_kv > 95,
    }

    print(f"\n  Max KV usage: {max_kv}%")

    return result


# ============================================================================
# P5: Block boundary waste on short Agent turns
# ============================================================================

async def run_p5(client, metrics_data):
    """P5: Block boundary waste quantification.

    Theory:
      - block_size=16 → waste per incremental = incremental_tokens % 16
      - Expected waste < 16 tokens per turn
      - Over a full session, total waste is bounded

    Method:
      1. Serial replay of 1 session, compute per-turn waste
      2. Waste = theoretical_prefix_reusable - measured_cached_tokens
    """
    print("\n" + "=" * 70)
    print("P5: Block boundary waste on short Agent turns (M1/M2)")
    print("=" * 70)

    result = {"pain_point": "P5_block_boundary_waste", "theory": {}, "measured": {}}

    sid = DJANGO_SESSIONS[0]
    session_rows = [r for r in metrics_data if r["session_id"] == sid]

    # Theory: expected waste per turn
    theory_waste = []
    for r in session_rows[:15]:
        if r["turn_index"] > 0:
            prev_total = session_rows[r["turn_index"] - 1]["total_tokens"] if r["turn_index"] - 1 < len(session_rows) else 0
            expected_cached = (prev_total // 16) * 16  # Block-aligned
            waste = prev_total - expected_cached
            theory_waste.append({
                "turn": r["turn_index"],
                "prev_total_tokens": prev_total,
                "expected_cached": expected_cached,
                "expected_waste": waste,
            })
    result["theory"]["per_turn_waste"] = theory_waste
    total_theory_waste = sum(t["expected_waste"] for t in theory_waste)
    result["theory"]["total_waste_tokens"] = total_theory_waste

    # Measured: serial replay, compute actual waste
    print(f"\n  [P5] Serial replay of {sid[:50]}...")
    turns = load_session_turns(sid)
    measured_waste = []

    for t_idx in range(min(len(turns), 15)):
        msgs = messages_to_openai_format(turns[t_idx]["messages"])
        if not msgs or estimate_tokens(msgs) > MAX_CONTEXT - 100:
            continue

        r = await send_request(client, msgs, f"P5-T{t_idx}")
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, t_idx)
        r["theoretical_prefix_reusable"] = th_p
        r["theoretical_total"] = th_t

        if r["success"] and t_idx > 0:
            actual_waste = th_p - r["cached_tokens"] if th_p > 0 else 0
            measured_waste.append({
                "turn": t_idx,
                "theoretical_prefix": th_p,
                "measured_cached": r["cached_tokens"],
                "actual_waste": actual_waste,
            })

        if r["success"]:
            print(f"    Turn {t_idx}: prompt={r['prompt_tokens']}, "
                  f"cached={r['cached_tokens']}, theory_prefix={th_p}")

        await asyncio.sleep(0.3)

    result["measured"]["per_turn_waste"] = measured_waste
    total_measured_waste = sum(w["actual_waste"] for w in measured_waste)
    result["measured"]["total_waste_tokens"] = total_measured_waste

    # Compute waste as % of total reusable prefix
    total_reusable = sum(w["theoretical_prefix"] for w in measured_waste if w["theoretical_prefix"] > 0)
    waste_pct = round(total_measured_waste / total_reusable * 100, 2) if total_reusable > 0 else 0

    result["analysis"] = {
        "theory_total_waste": total_theory_waste,
        "measured_total_waste": total_measured_waste,
        "waste_matches_theory": abs(total_measured_waste - total_theory_waste) < 50,
        "waste_pct_of_total": waste_pct,
    }

    print(f"\n  Total waste: theory={total_theory_waste}, measured={total_measured_waste}")

    return result


# ============================================================================
# P6: GPU prefix cache and offload tier independently managed
# ============================================================================

async def run_p6(client, metrics_data):
    """P6: Offload tier doesn't help prefix cache hits.

    Theory:
      - GPU prefix cache and CPU offload tier have independent hash tables
      - A block evicted from GPU prefix cache still exists in offload tier
      - But prefix cache lookup doesn't check offload tier
      - So offload ON vs OFF should show same cached_tokens for new requests

    NOTE: This experiment requires TWO separate server deployments:
      - Run 1: KV_OFFLOAD_GIB=8 (offload ON)
      - Run 2: KV_OFFLOAD_GIB=0 (offload OFF)
      Same workload on both.

    Since we can't restart the server from within this script,
    we document the procedure and collect what we can from the current server.
    """
    print("\n" + "=" * 70)
    print("P6: GPU prefix cache and offload tier independently managed (M9)")
    print("=" * 70)

    result = {"pain_point": "P6_cache_hierarchy", "theory": {}, "measured": {}, "procedure": {}}

    # Document the procedure
    result["procedure"] = {
        "step1": "Deploy server with KV_OFFLOAD_GIB=8, run eviction scenario",
        "step2": "Send test request, record cached_tokens",
        "step3": "Deploy server with KV_OFFLOAD_GIB=0, run same scenario",
        "step4": "Send test request, record cached_tokens",
        "expected": "cached_tokens should be the same regardless of offload setting",
        "reason": "GPU prefix cache lookup doesn't check offload tier for hash matches",
    }

    # Theory
    result["theory"]["l0_tokens"] = 6157
    result["theory"]["if_integrated"] = "With integrated offload+prefix cache, evicted L0 blocks could be loaded from offload tier, achieving higher cached_tokens"

    # Run with current server configuration
    # First, create eviction pressure, then test
    print("\n  [P6] Creating eviction pressure then testing L0 cache hit...")
    print("  (This tests the CURRENT server configuration)")

    # Phase 1: Fill cache
    p1_results = await replay_serial(client, DJANGO_SESSIONS[:3], 10, "P6-FILL", metrics_data)
    result["measured"]["phase1_fill"] = p1_results

    # Phase 2: Add pressure from different project
    p2_results = await replay_serial(client, SYMPY_SESSIONS[:2], 8, "P6-PRESS", metrics_data)
    result["measured"]["phase2_pressure"] = p2_results

    # Phase 3: Test L0 cache hit
    test_sid = "swebench__django__django-16379__minimax"
    turns = load_session_turns(test_sid)
    if turns:
        msgs = messages_to_openai_format(turns[0]["messages"])
        test_result = await send_request(client, msgs, "P6-TEST")
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, test_sid, 0)
        test_result["theoretical_l0"] = th_l0
        result["measured"]["test_result"] = test_result

        prom = await get_prometheus_metrics()
        result["measured"]["offload_metrics"] = {
            "store_bytes": prom.get("kv_offload_store_bytes"),
            "load_bytes": prom.get("kv_offload_load_bytes"),
            "stores_skipped": prom.get("kv_offload_stores_skipped"),
        }

    result["analysis"] = {
        "note": "Full P6 requires two server deployments (offload ON vs OFF). "
                "This run uses the current server. Compare with a separate run using different KV_OFFLOAD_GIB.",
    }

    return result


# ============================================================================
# P7: No scheduling awareness — mixed project load prefix reuse
# ============================================================================

async def run_p7(client, metrics_data):
    """P7: Mixed project scheduling — FCFS vs prefix-optimal order.

    Theory:
      - FCFS: 3 django + 2 sympy arrive concurrently → no prefix sharing
      - Optimal: send django first (build L0+L1 cache), then sympy (L0 only)
      - Gap = extra prefill tokens due to suboptimal scheduling

    Method:
      1. Concurrent: send 3 django + 2 sympy first turns together
      2. Sequential optimal: send 3 django first, then 2 sympy
      3. Compare total cached_tokens
    """
    print("\n" + "=" * 70)
    print("P7: No scheduling awareness (M3 extension)")
    print("=" * 70)

    result = {"pain_point": "P7_scheduling_awareness", "theory": {}, "measured": {}}

    sessions = DJANGO_SESSIONS[:3] + SYMPY_SESSIONS[:2]

    # Theory: compute expected cached tokens for optimal vs FCFS
    result["theory"]["fcfs_cached"] = 0  # All concurrent → 0 prefix sharing
    total_l0_l1 = 0
    for sid in sessions:
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, 0)
        total_l0_l1 += th_t  # Could be cached if optimally scheduled
    result["theory"]["optimal_cached"] = total_l0_l1  # If all prefix shared
    result["theory"]["gap_tokens"] = total_l0_l1

    # Measured: concurrent send
    print("\n  [P7-A] Sending 3 django + 2 sympy concurrently...")
    conc_results = await send_concurrent(client, sessions, "P7-CONC", metrics_data)
    result["measured"]["concurrent"] = conc_results

    # Measured: optimal sequential
    print("\n  [P7-B] Sending 3 django first, then 2 sympy (optimal order)...")
    # First: 3 django serially
    dj_results = []
    for i, sid in enumerate(DJANGO_SESSIONS[:3]):
        turns = load_session_turns(sid)
        if not turns:
            continue
        msgs = messages_to_openai_format(turns[0]["messages"])
        r = await send_request(client, msgs, f"P7-OPT-DJ{i+1}")
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, 0)
        r["theoretical_total"] = th_t
        r["theoretical_l0"] = th_l0
        dj_results.append(r)
        await asyncio.sleep(0.3)

    # Then: 2 sympy serially
    sy_results = []
    for i, sid in enumerate(SYMPY_SESSIONS[:2]):
        turns = load_session_turns(sid)
        if not turns:
            continue
        msgs = messages_to_openai_format(turns[0]["messages"])
        r = await send_request(client, msgs, f"P7-OPT-SY{i+1}")
        th_p, th_t, th_l0 = get_theoretical_prefix(metrics_data, sid, 0)
        r["theoretical_total"] = th_t
        r["theoretical_l0"] = th_l0
        sy_results.append(r)
        await asyncio.sleep(0.3)

    result["measured"]["optimal_django"] = dj_results
    result["measured"]["optimal_sympy"] = sy_results

    # Analysis
    conc_total_cached = sum(r.get("cached_tokens", 0) for r in conc_results if r["success"])
    opt_total_cached = sum(r.get("cached_tokens", 0) for r in dj_results + sy_results if r["success"])

    result["analysis"] = {
        "concurrent_total_cached": conc_total_cached,
        "optimal_total_cached": opt_total_cached,
        "gap_tokens": opt_total_cached - conc_total_cached,
        "gap_pct": round((opt_total_cached - conc_total_cached) / opt_total_cached * 100, 1) if opt_total_cached > 0 else 0,
    }

    print(f"\n  📊 P7 Result: Concurrent cached={conc_total_cached}, "
          f"Optimal cached={opt_total_cached}, Gap={opt_total_cached - conc_total_cached} tokens")

    return result


# ============================================================================
# Main
# ============================================================================

async def main():
    print("=" * 70)
    print("Phase 3: Per-Pain-Point Deep Analysis")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 70)

    metrics_data = load_per_row_metrics()
    sim_data = load_sim_results()
    print(f"Loaded {len(metrics_data)} per-row metrics, {len(sim_data)} sim results")

    client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)

    # Verify server is running
    try:
        await client.models.list()
        print("✅ vLLM server is running")
    except Exception as e:
        print(f"❌ vLLM server not available: {e}")
        return 1

    # Get baseline metrics
    baseline = await get_prometheus_metrics()
    print(f"Baseline: KV usage={baseline.get('kv_cache_usage_perc', '?')}%, "
          f"preemptions={baseline.get('num_preemptions', '?')}")

    # Run all pain points
    all_results = {}

    # NOTE: P1 and P7 should be run on a fresh server for best results.
    # P2, P3, P4 need memory pressure, which may require sequential runs.
    # P5 needs a fresh server for accurate waste measurement.
    # P6 requires two server deployments.
    #
    # We run them in an order that maximizes data quality:
    # P5 (needs clean cache) → P1 (needs clean cache) → P4 (builds up pressure)
    # → P7 (concurrent test) → P2 (eviction test) → P3 (preemption test) → P6

    print("\n" + "🔬" * 35)
    print("Running pain points in optimal order for data quality")
    print("NOTE: For best results, restart server between P1 and P2/P3")
    print("🔬" * 35)

    # P5: Block boundary waste (needs clean cache)
    all_results["P5"] = await run_p5(client, metrics_data)

    # P1: Concurrent prefix sharing (needs cache with known state)
    all_results["P1"] = await run_p1(client, metrics_data)

    # P4: Prefix growth pressure
    all_results["P4"] = await run_p4(client, metrics_data)

    # P7: Scheduling awareness
    all_results["P7"] = await run_p7(client, metrics_data)

    # P2: LRU evicts L0 (needs memory pressure from previous runs)
    all_results["P2"] = await run_p2(client, metrics_data)

    # P3: Preemption decode loss (needs maximum pressure)
    all_results["P3"] = await run_p3(client, metrics_data)

    # P6: Cache hierarchy
    all_results["P6"] = await run_p6(client, metrics_data)

    # Final metrics
    final_prom = await get_prometheus_metrics()

    # Save results
    output = {
        "experiment": "phase3_pain_points",
        "timestamp": datetime.now().isoformat(),
        "baseline_metrics": baseline,
        "final_metrics": final_prom,
        "results": all_results,
    }

    output_path = OUTPUT_DIR / "phase3_pain_points.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Saved: {output_path}")

    # Print summary table
    print("\n" + "=" * 70)
    print("PAIN POINT SUMMARY")
    print("=" * 70)
    print(f"{'Pain Point':<8} {'Key Metric':<35} {'Value':<20} {'Status'}")
    print("-" * 80)

    for pname, pdata in all_results.items():
        analysis = pdata.get("analysis", {})
        if pname == "P1":
            gap = analysis.get("cache_hit_gap_tokens", "?")
            print(f"{'P1':<8} {'Concurrent cache hit gap (tokens)':<35} {str(gap):<20} {'✅' if isinstance(gap, (int, float)) and gap > 0 else '⚠'}")
        elif pname == "P2":
            l0_hit = analysis.get("l0_hit_pct", "?")
            evicted = analysis.get("l0_evicted", "?")
            print(f"{'P2':<8} {'L0 hit rate after eviction pressure':<35} {str(l0_hit):<20} {'⚠ EVICTED' if evicted else '✅'}")
        elif pname == "P3":
            preemptions = analysis.get("total_preemptions", "?")
            print(f"{'P3':<8} {'Preemptions triggered':<35} {str(preemptions):<20} {'✅' if isinstance(preemptions, int) and preemptions > 0 else '⚠'}")
        elif pname == "P4":
            max_kv = analysis.get("max_kv_usage_perc", "?")
            print(f"{'P4':<8} {'Max KV usage (%)':<35} {str(max_kv):<20} {'✅' if isinstance(max_kv, (int, float)) and max_kv > 80 else '⚠'}")
        elif pname == "P5":
            waste = analysis.get("measured_total_waste", "?")
            matches = analysis.get("waste_matches_theory", "?")
            print(f"{'P5':<8} {'Total block waste (tokens)':<35} {str(waste):<20} {'✅' if matches else '⚠'}")
        elif pname == "P6":
            print(f"{'P6':<8} {'Needs 2 server deploys to verify':<35} {'N/A':<20} {'📋'}")
        elif pname == "P7":
            gap = analysis.get("gap_tokens", "?")
            print(f"{'P7':<8} {'Scheduling gap (tokens)':<35} {str(gap):<20} {'✅' if isinstance(gap, (int, float)) and gap > 0 else '⚠'}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
