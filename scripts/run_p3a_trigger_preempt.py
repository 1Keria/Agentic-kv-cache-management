#!/usr/bin/env python3
"""P3-A: 触发 Preemption 的实测验证

目标：在 vLLM 中触发真实的 preemption 事件

核心策略：
  1. 并发发送多个不共享 prefix 的长输出请求（max_tokens=4000）
  2. 让 vLLM 调度器同时运行多个请求，KV 占用接近容量
  3. 当调度器发现无法为新请求分配 blocks 时，preempt running 请求

关键指标：
  - num_preemptions > 0 → Preemption 被触发 ✅
  - 被 preempt 请求的恢复 TTFT → 量化 decode 丢失的代价

用法：python scripts/run_p3a_trigger_preempt.py [--max-tokens 4000] [--concurrent 9]
"""

import asyncio
import json
import os
import sys
import time
import argparse
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp_utils import (
    send_and_record, get_prometheus_metrics, KVTimelineCollector,
    load_real_prompts, get_real_session_prompt, save_run,
    make_text_with_token_count, make_messages,
    BLOCK_SIZE, BASE_URL
)
from openai import AsyncOpenAI


async def send_streaming_with_status(messages, label, max_tokens=4000, timeline=None):
    """发送请求，返回完整结果包括 streaming 状态变化"""
    if timeline:
        timeline.record_event("req_start", label)

    client = AsyncOpenAI(base_url=BASE_URL, api_key="dummy")
    start = time.time()
    first_token_time = None
    first_decode_time = None
    cached_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0
    response_text = ""
    was_preempted = False
    token_count_before_gap = 0
    gap_start = None

    stream = await client.chat.completions.create(
        model="Qwen3-8B", messages=messages, max_tokens=max_tokens,
        temperature=0, stream=True, stream_options={"include_usage": True},
    )

    async for chunk in stream:
        # Track first token
        if chunk.choices and chunk.choices[0].delta.content:
            if first_token_time is None:
                first_token_time = time.time()
            elif first_decode_time is None:
                first_decode_time = time.time()

            response_text += chunk.choices[0].delta.content
            token_count_before_gap = len(response_text.split())

        # Detect potential preemption gap (long delay between tokens)
        if chunk.choices and chunk.choices[0].delta.content and gap_start:
            gap_duration = time.time() - gap_start
            if gap_duration > 2.0:
                was_preempted = True
            gap_start = None
        elif chunk.choices and not chunk.choices[0].delta.content:
            if first_token_time:
                gap_start = time.time()

        # Track usage
        if chunk.usage is not None:
            prompt_tokens = chunk.usage.prompt_tokens
            completion_tokens = chunk.usage.completion_tokens
            if (chunk.usage.prompt_tokens_details is not None
                    and chunk.usage.prompt_tokens_details.cached_tokens is not None):
                cached_tokens = chunk.usage.prompt_tokens_details.cached_tokens

    result = {
        "label": label,
        "ttft_ms": round((first_token_time - start) * 1000, 1) if first_token_time else None,
        "total_ms": round((time.time() - start) * 1000, 1),
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "hit_rate": round(cached_tokens / prompt_tokens, 4) if prompt_tokens > 0 else 0,
        "completion_tokens": completion_tokens,
        "was_preempted": was_preempted,
        "response_preview": response_text[:200] if response_text else "",
    }

    if timeline:
        timeline.record_event("req_end", label, extra={
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "completion_tokens": completion_tokens,
            "was_preempted": was_preempted,
        })

    return result


async def run_p3a(max_tokens=4000, num_concurrent=9, label_suffix=""):
    """执行 P3-A 实验"""
    prompts = load_real_prompts()
    if not prompts:
        print("ERROR: No real prompts!")
        return None

    timeline = KVTimelineCollector(interval=0.3)
    await timeline.start()

    results = {"requests": [], "phases": {}, "config": {
        "max_tokens": max_tokens,
        "num_concurrent": num_concurrent,
    }}

    # Get baseline Prometheus metrics
    prom_before = get_prometheus_metrics()
    initial_preemptions = prom_before.get("num_preemptions", 0)

    # ===== Phase 1: Concurrent long-running requests =====
    print("\n" + "="*60)
    print(f"Phase 1: Concurrent {num_concurrent} long-running requests (max_tokens={max_tokens})")
    print("="*60)

    # Use unique prefixes to prevent prefix cache sharing
    # This forces each request to occupy independent KV blocks
    tasks = []
    for i in range(num_concurrent):
        unique_prefix = f"Session-{uuid.uuid4()}-Task-{i}: " + make_text_with_token_count(9900, seed=i)
        user_text = f"Query-{uuid.uuid4()}: Please provide a detailed analysis."
        messages = make_messages(unique_prefix, user_text)
        label = f"P1-req-{i}{label_suffix}"
        tasks.append(send_streaming_with_status(messages, label, max_tokens=max_tokens, timeline=timeline))

    print(f"  Launching {len(tasks)} concurrent requests...")
    phase1_start = time.time()
    phase1_results = await asyncio.gather(*tasks, return_exceptions=True)
    phase1_elapsed = time.time() - phase1_start

    for i, (label, result) in enumerate(zip([f"P1-req-{i}" for i in range(num_concurrent)], phase1_results)):
        if isinstance(result, Exception):
            print(f"  [{label}] ERROR: {result}")
            results["requests"].append({"label": label, "error": str(result)})
        else:
            results["requests"].append(result)
            preempt_mark = " [PREEMPTED?]" if result.get("was_preempted") else ""
            print(f"  [{label}] prompt={result['prompt_tokens']}, completion={result['completion_tokens']}, "
                  f"cached={result['cached_tokens']}, ttft={result['ttft_ms']}ms, "
                  f"total={result['total_ms']}ms{preempt_mark}")

    # Check preemption
    prom_after = get_prometheus_metrics()
    final_preemptions = prom_after.get("num_preemptions", 0)
    new_preemptions = final_preemptions - initial_preemptions
    print(f"\nPhase 1 done. Elapsed: {phase1_elapsed:.1f}s")
    print(f"  Preemptions: {initial_preemptions} → {final_preemptions} (Δ = {new_preemptions})")

    results["phases"]["phase1"] = {
        "num_concurrent": len(tasks),
        "elapsed_s": phase1_elapsed,
        "new_preemptions": new_preemptions,
    }

    # Check server log for preemption events
    # (We'll do this post-hoc)

    # ===== Phase 2: Test cache state after pressure =====
    print("\n" + "="*60)
    print("Phase 2: Test cache state after concurrent requests")
    print("="*60)

    await asyncio.sleep(2)
    django_turn0 = get_real_session_prompt("django", 0)
    if django_turn0:
        r_test = await send_and_record(django_turn0, "P2-django-t0-test", max_tokens=50, timeline=timeline)
        results["requests"].append(r_test)
        print(f"  Test: cached={r_test['cached_tokens']}, ttft={r_test['ttft_ms']}ms")

    # ===== Verdict =====
    print("\n" + "="*60)
    print("RESULTS:")
    print("="*60)

    if new_preemptions > 0:
        print(f"✅ PREEMPTION TRIGGERED! Δ preemptions = {new_preemptions}")
        verdict = "PREEMPTION_TRIGGERED"

        # Analyze preempted requests
        preempted = [r for r in results["requests"] if r.get("was_preempted")]
        if preempted:
            print(f"  {len(preempted)} requests appear to have been preempted (streaming gaps detected)")
            for r in preempted:
                print(f"    [{r['label']}] ttft={r['ttft_ms']}ms, total={r['total_ms']}ms")
    else:
        print(f"❌ No preemption detected. Δ preemptions = {new_preemptions}")
        print(f"   Trying with more concurrent requests or higher max_tokens")
        verdict = "NO_PREEMPTION"

    results["verdict"] = verdict
    results["new_preemptions"] = new_preemptions

    # Final metrics
    prom = get_prometheus_metrics()
    results["final_metrics"] = prom

    timeline_data = await timeline.stop()
    results["timeline"] = timeline_data

    return results


async def main():
    parser = argparse.ArgumentParser(description="P3-A: Trigger Preemption")
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--concurrent", type=int, default=9)
    parser.add_argument("--run-id", type=int, default=1)
    args = parser.parse_args()

    print(f"P3-A: Trigger Preemption")
    print(f"  max_tokens={args.max_tokens}, concurrent={args.concurrent}")

    results = await run_p3a(max_tokens=args.max_tokens, num_concurrent=args.concurrent,
                            label_suffix=f"_c{args.concurrent}_mt{args.max_tokens}")
    if results:
        save_run("exp_p3a_trigger_preempt", args.run_id, results,
                 suffix=f"c{args.concurrent}_mt{args.max_tokens}")
        print(f"\nVerdict: {results['verdict']}")


if __name__ == "__main__":
    asyncio.run(main())
