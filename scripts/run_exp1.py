"""实验 1：Prefix Cache 基本命中验证

验证 APC 的 block-level hash chain 命中行为：
- 请求 A（冷启动）→ 无命中
- 请求 B（共享 prefix）→ 应命中 prefix block

运行方式：
  1. 启动 vLLM server: bash scripts/run_vllm_server.sh
  2. 运行本脚本: cd /share/dai-sys/zhoulongsheng/agentkv && python scripts/run_exp1.py
  3. 每次运行间需重启 server 以清除 cache
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exp_utils import (
    make_text_with_token_count, make_messages, send_and_record,
    save_run, save_config, summarize_runs, get_prometheus_metrics,
    compute_prometheus_delta, wait_for_server, BLOCK_SIZE,
    KVTimelineCollector,
)

PREFIX_TOKENS = 2000
UNIQUE_TOKENS = 500
NUM_RUNS = 3


async def run_exp1(run_id: int):
    """单次实验运行"""
    prefix = make_text_with_token_count(PREFIX_TOKENS)
    unique_a = make_text_with_token_count(UNIQUE_TOKENS, seed=1)
    unique_b = make_text_with_token_count(UNIQUE_TOKENS, seed=2)

    # 启动 Timeline 采集
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    # 采集 Prometheus baseline
    prom_before = get_prometheus_metrics()

    # 请求 1：冷启动，无命中
    r1 = await send_and_record(make_messages(prefix, unique_a), "req1_cold",
                               timeline=timeline)
    print(f"  req1_cold: prompt={r1['prompt_tokens']}, cached={r1['cached_tokens']}, "
          f"ttft={r1['ttft_ms']}ms, total={r1['total_ms']}ms")

    # 请求 2：共享 prefix，应命中
    r2 = await send_and_record(make_messages(prefix, unique_b), "req2_warm",
                               timeline=timeline)
    print(f"  req2_warm: prompt={r2['prompt_tokens']}, cached={r2['cached_tokens']}, "
          f"ttft={r2['ttft_ms']}ms, total={r2['total_ms']}ms")

    # 采集 Prometheus after
    prom_after = get_prometheus_metrics()
    prom_delta = compute_prometheus_delta(prom_before, prom_after)

    # 停止 Timeline
    timeline_data = await timeline.stop()

    expected_cached = (PREFIX_TOKENS // BLOCK_SIZE) * BLOCK_SIZE
    actual_waste = PREFIX_TOKENS - r2["cached_tokens"]

    data = {
        "experiment": "exp1_prefix_hit",
        "run_id": run_id,
        "prefix_tokens": PREFIX_TOKENS,
        "unique_tokens": UNIQUE_TOKENS,
        "block_size": BLOCK_SIZE,
        "expected_cached_tokens": expected_cached,
        "actual_cached_tokens": r2["cached_tokens"],
        "block_waste_tokens": actual_waste,
        "requests": [r1, r2],
        "prometheus_before": prom_before,
        "prometheus_after": prom_after,
        "prometheus_delta": prom_delta,
        "timeline": timeline_data,
    }
    save_run("exp1_prefix_hit", run_id, data)

    # 验证
    if r2["cached_tokens"] > 0:
        print(f"  ✅ Prefix cache HIT! cached={r2['cached_tokens']}, "
              f"expected={expected_cached}, waste={actual_waste}")
    else:
        print(f"  ❌ Prefix cache MISS! Expected hit but got cached=0")

    if r2["ttft_ms"] and r1["ttft_ms"] and r1["ttft_ms"] > 0:
        reduction = (1 - r2["ttft_ms"] / r1["ttft_ms"]) * 100
        print(f"  TTFT reduction: {reduction:.1f}%")


async def main(num_runs=None):
    save_config()
    await wait_for_server()

    for i in range(1, (num_runs or NUM_RUNS) + 1):
        print(f"\n{'='*50}")
        print(f"Run {i}/{NUM_RUNS}")
        print(f"{'='*50}")
        await run_exp1(i)
        if i < NUM_RUNS:
            print("  → Restarting server (auto mode)...")

    # 汇总
    print(f"\n{'='*50}")
    print("Summarizing...")
    summarize_runs("exp1_prefix_hit")


if __name__ == "__main__":
    import argparse as _argparse
    _parser = _argparse.ArgumentParser()
    _parser.add_argument("--num-runs", type=int, default=None)
    _args = _parser.parse_args()
    asyncio.run(main(num_runs=_args.num_runs))
