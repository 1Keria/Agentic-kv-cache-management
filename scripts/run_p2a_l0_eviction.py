#!/usr/bin/env python3
"""P2-A: 触发 L0 驱逐的实测验证 (v3 - 无共享 prefix 并发策略)

核心洞察：
  - vLLM 的 free_block_queue 包含 prefix cache 的驱逐候选
  - 当新请求需要 blocks 且 free pool 不足时，从 free queue 头部（LRU）弹出
  - 弹出的 blocks 如果有 hash，会被隐式驱逐
  - 关键：需要让 running 请求占用足够的 KV blocks，使 free pool 接近 0

新策略 v3：
  Phase 1: 串行建立 L0+L1 缓存基线
  Phase 2: 并发发送多个**不共享 prefix** 的长输出请求（用不同 system prompt）
           这样每个请求的 KV 占用完全独立，不通过 prefix cache 共享
  Phase 3: 等请求完成后，测试 L0 是否被驱逐

为什么用不共享 prefix：
  - 如果 9 个请求共享 L0 (6,160 tokens)，实际 KV 占用 = 6,160 + 9 × L1
  - 如果 9 个请求不共享 prefix，KV 占用 = 9 × (6,160 + L1) ≈ 9 × 10,000 = 90,000 > 53,072

用法：
  python scripts/run_p2a_l0_eviction.py [--max-tokens 2000] [--concurrent 9]
"""

import asyncio
import json
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp_utils import (
    send_and_record, get_prometheus_metrics, KVTimelineCollector,
    load_real_prompts, get_real_session_prompt, save_run,
    make_text_with_token_count, make_messages,
    BLOCK_SIZE, BASE_URL, EXPERIMENT_DIR
)
from openai import AsyncOpenAI


async def send_and_record_async(messages, label, max_tokens=2000, timeline=None):
    """发送请求并记录完整指标（streaming 模式）"""
    if timeline:
        timeline.record_event("req_start", label)

    client = AsyncOpenAI(base_url=BASE_URL, api_key="dummy")
    start = time.time()
    first_token_time = None
    cached_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0

    stream = await client.chat.completions.create(
        model="Qwen3-8B",
        messages=messages,
        max_tokens=max_tokens,
        temperature=0,
        stream=True,
        stream_options={"include_usage": True},
    )

    async for chunk in stream:
        if first_token_time is None and chunk.choices and chunk.choices[0].delta.content:
            first_token_time = time.time()
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
    }

    if timeline:
        timeline.record_event("req_end", label, extra={
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "ttft_ms": result["ttft_ms"],
        })

    return result


async def run_p2a(max_tokens=2000, num_concurrent=9, label_suffix=""):
    """执行 P2-A 实验（无共享 prefix 并发策略）"""
    prompts = load_real_prompts()
    if not prompts:
        print("ERROR: No real prompts available!")
        return None

    # 计算 L0 大小
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        "/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/"
    )
    django_turn0 = get_real_session_prompt("django", 0)
    system_msg = django_turn0[0]["content"]
    l0_tokens = len(tokenizer.encode(system_msg))
    l0_block_aligned = (l0_tokens // BLOCK_SIZE) * BLOCK_SIZE
    print(f"L0 tokens: {l0_tokens}, block-aligned: {l0_block_aligned}")

    # 获取 GPU KV 容量
    import requests as req
    r = req.get("http://localhost:8000/metrics", timeout=5)
    import re
    for line in r.text.splitlines():
        if 'num_gpu_blocks=' in line and 'cache_config_info' in line:
            m = re.search(r'num_gpu_blocks="(\d+)"', line)
            if m:
                num_gpu_blocks = int(m.group(1))
                total_kv_tokens = num_gpu_blocks * BLOCK_SIZE
                print(f"GPU KV capacity: {num_gpu_blocks} blocks = {total_kv_tokens} tokens")
                break

    timeline = KVTimelineCollector(interval=0.3)
    await timeline.start()

    results = {"phases": {}, "requests": [], "config": {
        "max_tokens": max_tokens,
        "num_concurrent": num_concurrent,
        "l0_tokens": l0_tokens,
        "l0_block_aligned": l0_block_aligned,
    }}

    # ===== Phase 1: 串行建立 L0+L1 缓存基线 =====
    print("\n" + "="*60)
    print("Phase 1: 串行建立 L0+L1 缓存基线")
    print("="*60)

    messages = get_real_session_prompt("django", 0)
    r = await send_and_record(messages, "P1-django-t0-baseline", max_tokens=50, timeline=timeline)
    results["requests"].append(r)
    baseline_cached = r["cached_tokens"]
    baseline_ttft = r["ttft_ms"]
    print(f"  Baseline: prompt={r['prompt_tokens']}, cached={r['cached_tokens']}, "
          f"ttft={r['ttft_ms']}ms")

    results["phases"]["phase1"] = {
        "baseline_cached_tokens": baseline_cached,
        "baseline_ttft_ms": baseline_ttft,
    }

    # ===== Phase 2: 并发发送不共享 prefix 的长输出请求 =====
    print("\n" + "="*60)
    print(f"Phase 2: 并发发送 {num_concurrent} 个不共享 prefix 的长输出请求")
    print("="*60)

    # 为每个并发请求创建不同的 system prompt（不与 L0 共享）
    # 使用 UUID + 编号作为独特前缀，确保每个请求的 prefix 完全不同
    import uuid
    concurrent_tasks = []
    for i in range(num_concurrent):
        # 每个请求用 UUID 开头的独特文本作为 system prompt
        unique_prefix = f"Session-{uuid.uuid4()}-Task-{i}: " + make_text_with_token_count(9900, seed=i)
        user_text = f"Query-{uuid.uuid4()}: Please analyze this."
        messages = make_messages(unique_prefix, user_text)
        label = f"P2-unique-{i}{label_suffix}"
        task = send_and_record_async(messages, label, max_tokens=max_tokens, timeline=timeline)
        concurrent_tasks.append((label, task))

    # 并发发送所有请求
    print(f"  Launching {len(concurrent_tasks)} concurrent unique-prefix requests...")
    phase2_start = time.time()
    task_coros = [t[1] for t in concurrent_tasks]
    task_labels = [t[0] for t in concurrent_tasks]
    phase2_results = await asyncio.gather(*task_coros, return_exceptions=True)
    phase2_elapsed = time.time() - phase2_start

    print(f"  All concurrent requests completed in {phase2_elapsed:.1f}s")
    total_prompt_tokens = 0
    total_completion_tokens = 0
    for label, result in zip(task_labels, phase2_results):
        if isinstance(result, Exception):
            print(f"  [{label}] ERROR: {result}")
            results["requests"].append({"label": label, "error": str(result)})
        else:
            results["requests"].append(result)
            total_prompt_tokens += result["prompt_tokens"]
            total_completion_tokens += result["completion_tokens"]
            print(f"  [{label}] prompt={result['prompt_tokens']}, cached={result['cached_tokens']}, "
                  f"completion={result['completion_tokens']}, ttft={result['ttft_ms']}ms, "
                  f"total={result['total_ms']}ms")

    print(f"  Total prompt tokens: {total_prompt_tokens}, completion: {total_completion_tokens}")
    # 估算总 KV 占用（简化计算，不考虑 prefix cache 共享）
    estimated_kv = total_prompt_tokens + total_completion_tokens
    print(f"  Estimated total KV tokens: ~{estimated_kv} (vs capacity {total_kv_tokens})")

    prom = get_prometheus_metrics()
    results["phases"]["phase2"] = {
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "num_concurrent": len(concurrent_tasks),
        "elapsed_s": phase2_elapsed,
    }

    # ===== Phase 3: 测试 L0 是否被驱逐 =====
    print("\n" + "="*60)
    print("Phase 3: 测试 L0 是否被驱逐 (new django turn 0)")
    print("="*60)

    await asyncio.sleep(2)
    messages = get_real_session_prompt("django", 0)
    r_test = await send_and_record(messages, "P3-django-new-t0", max_tokens=50, timeline=timeline)
    results["requests"].append(r_test)
    print(f"  Test: prompt={r_test['prompt_tokens']}, cached={r_test['cached_tokens']}, "
          f"hit_rate={r_test['hit_rate']:.2%}, ttft={r_test['ttft_ms']}ms")

    # 判断驱逐结果
    print("\n" + "="*60)
    print("RESULTS:")
    print("="*60)
    cached = r_test["cached_tokens"]

    print(f"  Baseline (Phase 1) cached_tokens: {baseline_cached}")
    print(f"  Test (Phase 3) cached_tokens:     {cached}")
    print(f"  L0 block-aligned:                  {l0_block_aligned}")
    print(f"  L0+L1 expected:                    ~{baseline_cached}")

    if cached < l0_block_aligned:
        print(f"\n✅ L0 WAS EVICTED! cached_tokens={cached} < L0_block_aligned={l0_block_aligned}")
        print(f"   P2 confirmed: LRU eviction removes L0 blocks under pressure")
        verdict = "L0_EVICTED"
    elif cached < baseline_cached * 0.7:
        print(f"\n⚠️ Significant cache loss. cached={cached} vs baseline={baseline_cached}")
        print(f"   Some L1 blocks were evicted, L0 may or may not be intact")
        verdict = "PARTIAL_EVICTION"
    elif cached < baseline_cached:
        print(f"\n⚠️ Minor cache loss. cached={cached} vs baseline={baseline_cached}")
        verdict = "MINOR_EVICTION"
    else:
        print(f"\n❌ No significant eviction. cached={cached} ≈ baseline={baseline_cached}")
        print(f"   Free pool still has enough blocks; prefix cache not pressured")
        verdict = "NO_EVICTION"

    results["verdict"] = verdict
    results["test_cached_tokens"] = cached
    results["baseline_cached_tokens"] = baseline_cached

    # 采集最终 Prometheus 指标
    prom = get_prometheus_metrics()
    results["final_metrics"] = {
        "kv_cache_usage_perc": prom.get("kv_cache_usage_perc", 0),
        "prefix_cache_hits_total": prom.get("prefix_cache_hits_total", 0),
        "prefix_cache_queries_total": prom.get("prefix_cache_queries_total", 0),
    }
    results["phases"]["phase3"] = {
        "cached_tokens": cached,
        "ttft_ms": r_test["ttft_ms"],
    }

    timeline_data = await timeline.stop()
    results["timeline"] = timeline_data

    return results


async def main():
    parser = argparse.ArgumentParser(description="P2-A: Trigger L0 eviction (unique prefix strategy)")
    parser.add_argument("--max-tokens", type=int, default=2000,
                        help="Max tokens per concurrent request")
    parser.add_argument("--concurrent", type=int, default=9,
                        help="Number of concurrent requests")
    parser.add_argument("--run-id", type=int, default=1, help="Run ID")
    args = parser.parse_args()

    print(f"P2-A: Trigger L0 Eviction (Unique Prefix Strategy)")
    print(f"  max_tokens={args.max_tokens}, concurrent={args.concurrent}, run_id={args.run_id}")

    results = await run_p2a(max_tokens=args.max_tokens, num_concurrent=args.concurrent,
                            label_suffix=f"_u{args.concurrent}_mt{args.max_tokens}")
    if results:
        save_run("exp_p2a_l0_eviction", args.run_id, results,
                 suffix=f"u{args.concurrent}_mt{args.max_tokens}")
        print(f"\nVerdict: {results['verdict']}")


if __name__ == "__main__":
    asyncio.run(main())
