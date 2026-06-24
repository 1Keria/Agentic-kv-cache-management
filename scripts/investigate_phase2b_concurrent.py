#!/usr/bin/env python3
"""Phase 2B-v2: Concurrent pressure test to trigger KV cache eviction.

Key insight from Phase 2B-v1: Serial replay doesn't create memory pressure
because blocks are released (ref_cnt=0) after each request completes, but
remain in the hash table for future hits. No concurrent blocks = no pressure.

Solution: Run multiple requests CONCURRENTLY with long generation (max_tokens=500+)
to keep KV blocks occupied simultaneously. This forces the scheduler to allocate
blocks for multiple requests at once, creating real memory pressure.

Design:
  Phase 1: Warm up with 1 django session (5 turns serial) → L0+L1 cached
  Phase 2: Launch 5+ concurrent requests with long generation
  Phase 3: While those are running, launch more requests → trigger eviction
  Phase 4: After completion, test if L0 is still cached

Output: investigation/data/phase2b_concurrent_pressure.json
"""

import asyncio
import json
import time
import sys
from pathlib import Path
from datetime import datetime

import pyarrow.ipc as ipc
from openai import AsyncOpenAI

BASE_URL = "http://localhost:8000/v1"
API_KEY = "dummy"
MODEL_NAME = "Qwen3-8B"
TRACE_DIR = Path("experiments/vllm_kv_cache/lmcache_traces")
OUTPUT_DIR = Path("experiments/vllm_kv_cache/investigation/data")
PER_ROW_METRICS = OUTPUT_DIR / "per_row_metrics.json"
MAX_CONTEXT = 32768


def load_per_row_metrics():
    if PER_ROW_METRICS.exists():
        with open(PER_ROW_METRICS) as f:
            return json.load(f)
    return []


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
    return sum(len(m.get("content", "")) for m in messages) // 3


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
                            "num_gpu_blocks",
                            "num_blocks_pending",
                            "num_blocks_running",
                            "num_blocks_swapped",
                        ]:
                            if target in key:
                                metrics[target] = val
                    except ValueError:
                        pass
    except Exception:
        pass
    return metrics


async def send_long_request(client, messages, label, max_tokens=500):
    """Send a request with long generation to keep KV blocks occupied."""
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


async def send_short_request(client, messages, label, max_tokens=5):
    """Send a short request for quick measurements."""
    return await send_long_request(client, messages, label, max_tokens=max_tokens)


async def monitor_kv_usage(interval=2, duration=300):
    """Background task to monitor KV usage over time."""
    timeline = []
    start = time.time()
    while time.time() - start < duration:
        prom = await get_prometheus_metrics()
        timeline.append({
            "t": round(time.time() - start, 1),
            "kv_usage": prom.get("kv_cache_usage_perc"),
            "preemptions": prom.get("num_preemptions"),
        })
        await asyncio.sleep(interval)
    return timeline


async def main():
    print("=" * 70)
    print("Phase 2B-v2: Concurrent Pressure Test for KV Cache Eviction")
    print("=" * 70)
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Strategy: Run multiple concurrent requests with long generation")
    print(f"to keep KV blocks occupied simultaneously → real memory pressure")

    metrics_data = load_per_row_metrics()
    client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)

    # Verify server
    try:
        await client.models.list()
        print("✅ vLLM server is running")
    except Exception as e:
        print(f"❌ Server not available: {e}")
        return 1

    baseline = await get_prometheus_metrics()
    print(f"Baseline: KV={baseline.get('kv_cache_usage_perc', '?')}%, "
          f"preemptions={baseline.get('num_preemptions', '?')}")

    # Find sessions
    DJANGO_SESSIONS = [
        "swebench__django__django-10097__minimax",
        "swebench__django__django-10554__minimax",
        "swebench__django__django-10914__minimax",
        "swebench__django__django-10973__minimax",
        "swebench__django__django-11179__minimax",
    ]
    SYMPY_SESSIONS = [
        "swebench__sympy__sympy-14976__minimax",
        "swebench__sympy__sympy-18199__minimax",
        "swebench__sympy__sympy-18698__minimax",
        "swebench__sympy__sympy-19040__minimax",
    ]

    all_results = {}

    # ================================================================
    # Phase 1: Warm up — serial replay 1 django session (5 turns)
    # ================================================================
    print("\n" + "=" * 70)
    print("PHASE 1: Warm up — serial replay 1 django session (5 turns)")
    print("=" * 70)

    warmup_results = []
    turns = load_session_turns(DJANGO_SESSIONS[0])
    for t_idx in range(min(5, len(turns))):
        msgs = messages_to_openai_format(turns[t_idx]["messages"])
        if not msgs or estimate_tokens(msgs) > MAX_CONTEXT - 100:
            continue
        r = await send_short_request(client, msgs, f"WARM-T{t_idx}")
        prom = await get_prometheus_metrics()
        r["kv_cache_usage_perc"] = prom.get("kv_cache_usage_perc")
        warmup_results.append(r)
        if r["success"]:
            print(f"  Turn {t_idx}: prompt={r['prompt_tokens']}, cached={r['cached_tokens']} "
                  f"({r['hit_rate']:.1%}), TTFT={r['ttft_ms']}ms, KV={prom.get('kv_cache_usage_perc', '?')}%")
        await asyncio.sleep(0.3)

    all_results["phase1_warmup"] = warmup_results

    # ================================================================
    # Phase 2: Concurrent long requests — 5 django + 4 sympy
    # Each with max_tokens=500 to keep KV blocks occupied
    # ================================================================
    print("\n" + "=" * 70)
    print("PHASE 2: Concurrent long requests (9 sessions, max_tokens=500)")
    print("=" * 70)
    print("Each request generates ~500 tokens, keeping KV blocks occupied")
    print("9 concurrent requests × ~10K prompt + 500 output = ~94K tokens needed")
    print("GPU KV capacity: ~44K tokens → should trigger eviction!")

    # Start KV usage monitor
    monitor_task = asyncio.create_task(monitor_kv_usage(interval=1, duration=600))

    # Prepare messages for all sessions (use turn 0 for each)
    concurrent_tasks = []
    session_labels = []

    for i, sid in enumerate(DJANGO_SESSIONS):
        turns = load_session_turns(sid)
        if not turns:
            continue
        # Use turn 3 (longer prompt, ~11K tokens) for more pressure
        t_idx = min(3, len(turns) - 1)
        msgs = messages_to_openai_format(turns[t_idx]["messages"])
        if not msgs or estimate_tokens(msgs) > MAX_CONTEXT - 600:
            # Fall back to turn 0
            msgs = messages_to_openai_format(turns[0]["messages"])
        if msgs:
            label = f"DJ{i+1}-T{t_idx}"
            concurrent_tasks.append(send_long_request(client, msgs, label, max_tokens=500))
            session_labels.append(label)

    for i, sid in enumerate(SYMPY_SESSIONS):
        turns = load_session_turns(sid)
        if not turns:
            continue
        t_idx = min(3, len(turns) - 1)
        msgs = messages_to_openai_format(turns[t_idx]["messages"])
        if not msgs or estimate_tokens(msgs) > MAX_CONTEXT - 600:
            msgs = messages_to_openai_format(turns[0]["messages"])
        if msgs:
            label = f"SY{i+1}-T{t_idx}"
            concurrent_tasks.append(send_long_request(client, msgs, label, max_tokens=500))
            session_labels.append(label)

    print(f"  Launching {len(concurrent_tasks)} concurrent requests...")
    start_time = time.time()

    # Send all concurrently
    phase2_results = await asyncio.gather(*concurrent_tasks)
    elapsed = time.time() - start_time

    # Stop monitor
    monitor_task.cancel()
    try:
        kv_timeline = await monitor_task
    except asyncio.CancelledError:
        kv_timeline = []

    # Get final metrics
    phase2_prom = await get_prometheus_metrics()
    total_preemptions = phase2_prom.get("num_preemptions", 0) - baseline.get("num_preemptions", 0)

    print(f"\n  Phase 2 complete in {elapsed:.1f}s")
    print(f"  KV usage: {phase2_prom.get('kv_cache_usage_perc', '?')}%")
    print(f"  Preemptions: {total_preemptions}")

    for r in phase2_results:
        if r["success"]:
            print(f"    {r['label']}: prompt={r['prompt_tokens']}, cached={r['cached_tokens']} "
                  f"({r['hit_rate']:.1%}), TTFT={r['ttft_ms']}ms, output={r['completion_tokens']}tok")
        else:
            print(f"    {r['label']}: ❌ {r.get('error', 'unknown')}")

    all_results["phase2_concurrent"] = phase2_results
    all_results["phase2_kv_timeline"] = kv_timeline

    # ================================================================
    # Phase 3: Test L0 cache hit after concurrent pressure
    # ================================================================
    print("\n" + "=" * 70)
    print("PHASE 3: Test L0 cache hit after concurrent pressure")
    print("=" * 70)

    # Wait a moment for KV to settle
    await asyncio.sleep(2)

    # Send a new django session first turn
    test_sid = DJANGO_SESSIONS[0]  # Same session, should have L0+L1 cached
    turns = load_session_turns(test_sid)
    if turns:
        msgs = messages_to_openai_format(turns[0]["messages"])
        test_result = await send_short_request(client, msgs, "TEST-DJANGO-T0")
        prom = await get_prometheus_metrics()
        test_result["kv_cache_usage_perc"] = prom.get("kv_cache_usage_perc")

        # Get theoretical L0
        l0_tokens = 0
        for r in metrics_data:
            if r["session_id"] == test_sid and r["turn_index"] == 0:
                l0_tokens = r.get("l0_tokens", 6157)
                break

        test_result["theoretical_l0"] = l0_tokens
        all_results["phase3_l0_test"] = test_result

        cached = test_result.get("cached_tokens", 0) if test_result["success"] else 0
        l0_hit_pct = cached / l0_tokens if l0_tokens > 0 else 0
        print(f"  L0 hit: {cached}/{l0_tokens} = {l0_hit_pct:.1%}")
        if cached < l0_tokens * 0.8:
            print(f"  ⚠ L0 PARTIALLY/FULLY EVICTED!")
        else:
            print(f"  ✅ L0 still cached")

    # Also test a sympy session (different L1, same L0)
    test_sid2 = SYMPY_SESSIONS[0]
    turns2 = load_session_turns(test_sid2)
    if turns2:
        msgs2 = messages_to_openai_format(turns2[0]["messages"])
        test_result2 = await send_short_request(client, msgs2, "TEST-SYMPY-T0")
        prom = await get_prometheus_metrics()
        test_result2["kv_cache_usage_perc"] = prom.get("kv_cache_usage_perc")

        l0_tokens2 = 0
        for r in metrics_data:
            if r["session_id"] == test_sid2 and r["turn_index"] == 0:
                l0_tokens2 = r.get("l0_tokens", 6157)
                break
        test_result2["theoretical_l0"] = l0_tokens2
        all_results["phase3_l0_test_sympy"] = test_result2

        cached2 = test_result2.get("cached_tokens", 0) if test_result2["success"] else 0
        l0_hit_pct2 = cached2 / l0_tokens2 if l0_tokens2 > 0 else 0
        print(f"  Sympy L0 hit: {cached2}/{l0_tokens2} = {l0_hit_pct2:.1%}")

    # ================================================================
    # Phase 4: More aggressive — concurrent with even longer generation
    # ================================================================
    if total_preemptions == 0:
        print("\n" + "=" * 70)
        print("PHASE 4: More aggressive — 9 concurrent with max_tokens=1000")
        print("=" * 70)

        # Start monitor
        monitor_task2 = asyncio.create_task(monitor_kv_usage(interval=1, duration=600))

        concurrent_tasks2 = []
        for i, sid in enumerate(DJANGO_SESSIONS[:3]):
            turns = load_session_turns(sid)
            if not turns:
                continue
            # Use turn 5 (even longer prompt)
            t_idx = min(5, len(turns) - 1)
            msgs = messages_to_openai_format(turns[t_idx]["messages"])
            if not msgs or estimate_tokens(msgs) > MAX_CONTEXT - 1100:
                t_idx = 0
                msgs = messages_to_openai_format(turns[0]["messages"])
            if msgs:
                label = f"AGG-DJ{i+1}-T{t_idx}"
                concurrent_tasks2.append(send_long_request(client, msgs, label, max_tokens=1000))

        for i, sid in enumerate(SYMPY_SESSIONS[:3]):
            turns = load_session_turns(sid)
            if not turns:
                continue
            t_idx = min(5, len(turns) - 1)
            msgs = messages_to_openai_format(turns[t_idx]["messages"])
            if not msgs or estimate_tokens(msgs) > MAX_CONTEXT - 1100:
                t_idx = 0
                msgs = messages_to_openai_format(turns[0]["messages"])
            if msgs:
                label = f"AGG-SY{i+1}-T{t_idx}"
                concurrent_tasks2.append(send_long_request(client, msgs, label, max_tokens=1000))

        print(f"  Launching {len(concurrent_tasks2)} aggressive concurrent requests...")
        start_time2 = time.time()
        phase4_results = await asyncio.gather(*concurrent_tasks2)
        elapsed2 = time.time() - start_time2

        monitor_task2.cancel()
        try:
            kv_timeline2 = await monitor_task2
        except asyncio.CancelledError:
            kv_timeline2 = []

        phase4_prom = await get_prometheus_metrics()
        total_preemptions2 = phase4_prom.get("num_preemptions", 0) - baseline.get("num_preemptions", 0)

        print(f"\n  Phase 4 complete in {elapsed2:.1f}s")
        print(f"  KV usage: {phase4_prom.get('kv_cache_usage_perc', '?')}%")
        print(f"  Preemptions: {total_preemptions2}")

        for r in phase4_results:
            if r["success"]:
                print(f"    {r['label']}: prompt={r['prompt_tokens']}, cached={r['cached_tokens']} "
                      f"({r['hit_rate']:.1%}), TTFT={r['ttft_ms']}ms, output={r['completion_tokens']}tok")

        all_results["phase4_aggressive"] = phase4_results
        all_results["phase4_kv_timeline"] = kv_timeline2

    # ================================================================
    # Final summary
    # ================================================================
    final_prom = await get_prometheus_metrics()
    final_preemptions = final_prom.get("num_preemptions", 0) - baseline.get("num_preemptions", 0)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Final KV usage: {final_prom.get('kv_cache_usage_perc', '?')}%")
    print(f"  Total preemptions: {final_preemptions}")
    print(f"  Prefix cache hits: {final_prom.get('prefix_cache_hits', 0) - baseline.get('prefix_cache_hits', 0)}")
    print(f"  Prefix cache queries: {final_prom.get('prefix_cache_queries', 0) - baseline.get('prefix_cache_queries', 0)}")

    # Analyze concurrent hit rates
    if phase2_results:
        conc_cached = [r["cached_tokens"] for r in phase2_results if r["success"]]
        conc_prompt = [r["prompt_tokens"] for r in phase2_results if r["success"]]
        total_cached = sum(conc_cached)
        total_prompt = sum(conc_prompt)
        overall_hit = total_cached / total_prompt if total_prompt > 0 else 0
        print(f"\n  Concurrent overall hit rate: {overall_hit:.1%} ({total_cached}/{total_prompt})")
        hit_rates = [f"{r['hit_rate']:.1%}" for r in phase2_results if r["success"]]
        print(f"  Per-request hit rates: {hit_rates}")

    # Save
    output = {
        "experiment": "phase2b_concurrent_pressure",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "gpu_util": 0.3,
            "gpu_kv_capacity_tokens": 44000,
            "apc_enabled": True,
            "block_size": 16,
            "offloading": "disabled",
        },
        "baseline_metrics": baseline,
        "final_metrics": final_prom,
        "total_preemptions": final_preemptions,
        "results": all_results,
    }

    output_path = OUTPUT_DIR / "phase2b_concurrent_pressure.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Saved: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
