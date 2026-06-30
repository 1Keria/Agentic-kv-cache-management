#!/usr/bin/env python3
"""P2-B: LRU vs Agent-Aware 驱逐对比

目标：通过请求调度顺序模拟 Agent-Aware 驱逐效果，量化差异

配置 A（默认 LRU）：
  Phase 1: 串行发送 django turn 0（建立 L0+L1 缓存）
  Phase 2: 并发发送 9 个不共享 prefix 的长输出请求（触发 L0 驱逐）
  Phase 3: 新 django turn 0 → 记录 cached_tokens_A, TTFT_A

配置 B（模拟 Agent-Aware）：
  Phase 1: 串行发送 django turn 0（建立 L0+L1 缓存）
  Phase 2: 并发发送 9 个不共享 prefix 的长输出请求（同上）
  Phase 2.5: 发送 1 个 django turn 0（"touch" L0 blocks，刷新其在 free queue 中的位置）
  Phase 3: 再发送 9 个不共享 prefix 请求（继续施压）
  Phase 4: 新 django turn 0 → 记录 cached_tokens_B, TTFT_B

预期：cached_tokens_B > cached_tokens_A（touch 操作保护 L0 不被驱逐）

用法：python scripts/run_p2b_lru_vs_aware.py
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
    BLOCK_SIZE, BASE_URL, EXPERIMENT_DIR
)
from openai import AsyncOpenAI


async def send_async(messages, label, max_tokens=2000, timeline=None):
    """发送请求并记录指标"""
    if timeline:
        timeline.record_event("req_start", label)

    client = AsyncOpenAI(base_url=BASE_URL, api_key="dummy")
    start = time.time()
    first_token_time = None
    cached_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0

    stream = await client.chat.completions.create(
        model="Qwen3-8B", messages=messages, max_tokens=max_tokens,
        temperature=0, stream=True, stream_options={"include_usage": True},
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
            "prompt_tokens": prompt_tokens, "cached_tokens": cached_tokens,
        })

    return result


async def make_pressure_requests(num, max_tokens, label_prefix, timeline):
    """创建不共享 prefix 的压力请求"""
    tasks = []
    for i in range(num):
        unique_prefix = f"Session-{uuid.uuid4()}-Task-{i}: " + make_text_with_token_count(9900, seed=i + 100)
        user_text = f"Query-{uuid.uuid4()}: Analyze."
        messages = make_messages(unique_prefix, user_text)
        label = f"{label_prefix}-pressure-{i}"
        tasks.append(send_async(messages, label, max_tokens=max_tokens, timeline=timeline))
    return tasks


async def run_config(config_name, max_tokens=2000, touch_l0=False):
    """运行一种配置"""
    prompts = load_real_prompts()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        "/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/"
    )
    django_turn0 = get_real_session_prompt("django", 0)
    l0_tokens = len(tokenizer.encode(django_turn0[0]["content"]))
    l0_block_aligned = (l0_tokens // BLOCK_SIZE) * BLOCK_SIZE

    timeline = KVTimelineCollector(interval=0.3)
    await timeline.start()

    results = {"config": config_name, "requests": [], "phases": {}}

    # Phase 1: 建立 L0+L1 缓存
    print(f"\n{'='*60}")
    print(f"[{config_name}] Phase 1: 建立 L0+L1 缓存")
    print(f"{'='*60}")

    messages = get_real_session_prompt("django", 0)
    r = await send_and_record(messages, f"{config_name}-P1-django-t0", max_tokens=50, timeline=timeline)
    results["requests"].append(r)
    baseline_cached = r["cached_tokens"]
    baseline_ttft = r["ttft_ms"]
    print(f"  Baseline: cached={baseline_cached}, ttft={baseline_ttft}ms")

    # Phase 2: 压力请求
    print(f"\n{'='*60}")
    print(f"[{config_name}] Phase 2: 压力请求 (9 concurrent)")
    print(f"{'='*60}")

    pressure_tasks = await make_pressure_requests(9, max_tokens, config_name, timeline)
    phase2_results = await asyncio.gather(*pressure_tasks, return_exceptions=True)
    for r in phase2_results:
        if isinstance(r, Exception):
            print(f"  ERROR: {r}")
        else:
            results["requests"].append(r)
            print(f"  [{r['label']}] prompt={r['prompt_tokens']}, completion={r['completion_tokens']}, "
                  f"ttft={r['ttft_ms']}ms")

    results["phases"]["phase2"] = {"num_requests": len(pressure_tasks)}

    # Phase 2.5 (only for Agent-Aware config): Touch L0 blocks
    if touch_l0:
        print(f"\n{'='*60}")
        print(f"[{config_name}] Phase 2.5: Touch L0 blocks (django turn 0)")
        print(f"{'='*60}")

        messages = get_real_session_prompt("django", 0)
        r_touch = await send_and_record(messages, f"{config_name}-P2.5-touch", max_tokens=50, timeline=timeline)
        results["requests"].append(r_touch)
        print(f"  Touch: cached={r_touch['cached_tokens']}, ttft={r_touch['ttft_ms']}ms")

        # Phase 2.75: More pressure after touch
        print(f"\n{'='*60}")
        print(f"[{config_name}] Phase 2.75: More pressure after touch")
        print(f"{'='*60}")

        pressure_tasks2 = await make_pressure_requests(9, max_tokens, f"{config_name}-P2.75", timeline)
        phase2b_results = await asyncio.gather(*pressure_tasks2, return_exceptions=True)
        for r in phase2b_results:
            if isinstance(r, Exception):
                print(f"  ERROR: {r}")
            else:
                results["requests"].append(r)
                print(f"  [{r['label']}] completion={r['completion_tokens']}, ttft={r['ttft_ms']}ms")

        results["phases"]["phase2.5"] = {
            "touch_cached_tokens": r_touch["cached_tokens"],
            "touch_ttft_ms": r_touch["ttft_ms"],
        }

    # Phase 3: 测试 L0 是否存活
    print(f"\n{'='*60}")
    print(f"[{config_name}] Phase 3: 测试 L0 缓存状态")
    print(f"{'='*60}")

    await asyncio.sleep(2)
    messages = get_real_session_prompt("django", 0)
    r_test = await send_and_record(messages, f"{config_name}-P3-django-t0-test", max_tokens=50, timeline=timeline)
    results["requests"].append(r_test)
    print(f"  Test: cached={r_test['cached_tokens']}, ttft={r_test['ttft_ms']}ms")

    results["phases"]["phase3"] = {
        "cached_tokens": r_test["cached_tokens"],
        "ttft_ms": r_test["ttft_ms"],
    }
    results["baseline_cached"] = baseline_cached
    results["baseline_ttft"] = baseline_ttft
    results["l0_block_aligned"] = l0_block_aligned

    # Verdict
    cached = r_test["cached_tokens"]
    if cached >= l0_block_aligned:
        verdict = "L0_SURVIVED"
        print(f"  ✅ L0 survived! cached={cached} >= L0_aligned={l0_block_aligned}")
    else:
        verdict = "L0_EVICTED"
        print(f"  ❌ L0 evicted. cached={cached} < L0_aligned={l0_block_aligned}")

    results["verdict"] = verdict

    timeline_data = await timeline.stop()
    results["timeline"] = timeline_data

    return results


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--run-id", type=int, default=1)
    args = parser.parse_args()

    print(f"P2-B: LRU vs Agent-Aware Eviction Comparison")
    print(f"  max_tokens={args.max_tokens}")

    # Config A: Default LRU (no touch)
    print("\n" + "#"*60)
    print("# Config A: Default LRU (no touch)")
    print("#"*60)
    results_a = await run_config("LRU", max_tokens=args.max_tokens, touch_l0=False)
    save_run("exp_p2b_lru_vs_aware", args.run_id, results_a, suffix="lru")

    # Need fresh server for Config B
    print("\n" + "#"*60)
    print("# RESTARTING SERVER for Config B (clean state)")
    print("#"*60)
    print("Please restart vLLM server and run Config B separately:")
    print(f"  python scripts/run_p2b_lru_vs_aware.py --config aware --run-id {args.run_id}")

    # Config B: Agent-Aware (with touch)
    print("\n" + "#"*60)
    print("# Config B: Agent-Aware (with touch)")
    print("#"*60)
    results_b = await run_config("Aware", max_tokens=args.max_tokens, touch_l0=True)
    save_run("exp_p2b_lru_vs_aware", args.run_id, results_b, suffix="aware")

    # Compare
    print("\n" + "="*60)
    print("COMPARISON:")
    print("="*60)
    print(f"  LRU (Config A):   cached={results_a['phases']['phase3']['cached_tokens']}, "
          f"ttft={results_a['phases']['phase3']['ttft_ms']}ms, verdict={results_a['verdict']}")
    print(f"  Aware (Config B): cached={results_b['phases']['phase3']['cached_tokens']}, "
          f"ttft={results_b['phases']['phase3']['ttft_ms']}ms, verdict={results_b['verdict']}")

    cached_a = results_a['phases']['phase3']['cached_tokens']
    cached_b = results_b['phases']['phase3']['cached_tokens']
    if cached_b > cached_a:
        print(f"\n✅ Agent-Aware preserves more cache! Delta = {cached_b - cached_a} tokens")
    elif cached_b == cached_a:
        print(f"\n⚠️ No difference between LRU and Agent-Aware")
    else:
        print(f"\n⚠️ Agent-Aware actually worse! Delta = {cached_b - cached_a} tokens")


if __name__ == "__main__":
    asyncio.run(main())
