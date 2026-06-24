"""实验 2：Block-level 粒度浪费量化

测量 block_size=16 在不同 prefix 长度下的尾部 token 浪费：
- 构造不同长度的 prefix
- 第二个请求共享 prefix
- 记录实际命中 token 数 vs 预期命中 token 数

运行方式：
  1. 启动 vLLM server: bash scripts/run_vllm_server.sh
  2. 运行本脚本: cd /share/dai-sys/zhoulongsheng/agentkv && python scripts/run_exp2.py
  3. 每次运行间需重启 server
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

# 不同 prefix 长度测试（与 spec v3 一致）
PREFIX_LENGTHS = [2000, 2001, 2008, 2015, 2016, 100, 99]
UNIQUE_TOKENS = 200
NUM_RUNS = 2


async def run_exp2(run_id: int):
    """单次实验运行"""
    results = []

    # 启动 Timeline 采集
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    for prefix_tokens in PREFIX_LENGTHS:
        print(f"\n  --- prefix_tokens = {prefix_tokens} ---")
        prefix = make_text_with_token_count(prefix_tokens)
        unique_a = make_text_with_token_count(UNIQUE_TOKENS, seed=prefix_tokens * 2)
        unique_b = make_text_with_token_count(UNIQUE_TOKENS, seed=prefix_tokens * 2 + 1)

        prom_before = get_prometheus_metrics()

        # 请求 1：冷启动
        r1 = await send_and_record(make_messages(prefix, unique_a),
                                    f"prefix{prefix_tokens}_cold",
                                    timeline=timeline)
        print(f"    cold: prompt={r1['prompt_tokens']}, cached={r1['cached_tokens']}, ttft={r1['ttft_ms']}ms")

        # 请求 2：应命中 prefix
        r2 = await send_and_record(make_messages(prefix, unique_b),
                                    f"prefix{prefix_tokens}_warm",
                                    timeline=timeline)
        print(f"    warm: prompt={r2['prompt_tokens']}, cached={r2['cached_tokens']}, ttft={r2['ttft_ms']}ms")

        prom_after = get_prometheus_metrics()

        expected_cached = (prefix_tokens // BLOCK_SIZE) * BLOCK_SIZE
        waste = prefix_tokens - r2["cached_tokens"]
        expected_waste = prefix_tokens % BLOCK_SIZE

        results.append({
            "prefix_tokens": prefix_tokens,
            "expected_cached_tokens": expected_cached,
            "actual_cached_tokens": r2["cached_tokens"],
            "expected_waste_tokens": expected_waste,
            "actual_waste_tokens": waste,
            "waste_match": waste == expected_waste,
            "req_cold": r1,
            "req_warm": r2,
            "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        })

        # 每组测试间等待 2 秒，让 KV cache 稳定
        await asyncio.sleep(2)

    # 停止 Timeline
    timeline_data = await timeline.stop()

    data = {
        "experiment": "exp2_block_granularity",
        "run_id": run_id,
        "block_size": BLOCK_SIZE,
        "prefix_lengths": PREFIX_LENGTHS,
        "results": results,
        "timeline": timeline_data,
    }
    save_run("exp2_block_granularity", run_id, data)

    # 验证
    all_match = all(r["waste_match"] for r in results)
    if all_match:
        print(f"\n  ✅ 所有 prefix 长度的 waste 都与预期一致！")
    else:
        mismatched = [r for r in results if not r["waste_match"]]
        print(f"\n  ❌ {len(mismatched)} 个 prefix 长度的 waste 与预期不一致：")
        for r in mismatched:
            print(f"    prefix={r['prefix_tokens']}: expected_waste={r['expected_waste_tokens']}, "
                  f"actual_waste={r['actual_waste_tokens']}")


async def main(num_runs=None):
    save_config()
    await wait_for_server()

    for i in range(1, (num_runs or NUM_RUNS) + 1):
        print(f"\n{'='*50}")
        print(f"Run {i}/{NUM_RUNS}")
        print(f"{'='*50}")
        await run_exp2(i)
        if i < NUM_RUNS:
            print("  → Restarting server (auto mode)...")

    print(f"\n{'='*50}")
    print("Summarizing...")
    summarize_runs("exp2_block_granularity")


if __name__ == "__main__":
    import argparse as _argparse
    _parser = _argparse.ArgumentParser()
    _parser.add_argument("--num-runs", type=int, default=None)
    _args = _parser.parse_args()
    asyncio.run(main(num_runs=_args.num_runs))
