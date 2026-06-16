"""实验 5：Agent 组感知驱逐模拟

展示"agent-aware 驱逐"比普通 LRU 的优势：
- 运行 A（普通 LRU）：3 sqlfluff T1 + 2 astroid T1 → sqlfluff T2
- 运行 B（模拟 agent-aware）：3 sqlfluff T1 + 1 astroid T1 → sqlfluff T2

关键对比：运行 A vs B 的 sqlfluff_T2 的 cached_tokens 差异

Token 配置（与 exp4 一致）：
  L0 = 5000 (全局共享)
  L1_sqlfluff = 1000 (sqlfluff 项目级)
  L1_astroid = 800 (astroid 项目级)
  L2 = 500 (session 级)

  sqlfluff session T1 = 5000+1000+500 = 6500 tokens
  astroid session T1 = 5000+800+500 = 6300 tokens

运行方式：
  # 运行 A（普通 LRU）
  bash scripts/run_vllm_server.sh
  python scripts/run_exp5.py --run lru
  # 重启 server 清除 cache
  bash scripts/run_vllm_server.sh
  python scripts/run_exp5.py --run aware
"""

import argparse
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

# Token 配置（与 exp4 一致）
L0_TOKENS = 5000
L1_SQLFLUFF_TOKENS = 1000
L1_ASTROID_TOKENS = 800
L2_TOKENS = 500

NUM_RUNS = 2


async def run_exp5(run_id: int, run_type: str):
    """单次实验运行

    Args:
        run_id: 运行编号
        run_type: "lru" (普通 LRU) 或 "aware" (模拟 agent-aware)
    """
    exp_name = f"exp5_{run_type}_eviction"
    is_lru = run_type == "lru"
    astroid_count = 2 if is_lru else 1

    print(f"  Run type: {'Default LRU' if is_lru else 'Agent-Aware (simulated)'}")
    print(f"  Astroid sessions in Phase 2: {astroid_count}")

    # 构造各层文本
    l0 = make_text_with_token_count(L0_TOKENS, seed=0)
    l1_sqlfluff = make_text_with_token_count(L1_SQLFLUFF_TOKENS, seed=10)
    l1_astroid = make_text_with_token_count(L1_ASTROID_TOKENS, seed=11)

    sqlfluff_prefix = l0 + l1_sqlfluff
    astroid_prefix = l0 + l1_astroid

    # 启动 Timeline 采集
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    prom_before = get_prometheus_metrics()

    # Phase 1: 3 个 sqlfluff session T1 (串行)
    timeline.record_event("phase_start", "phase1")
    phase1_results = []
    for i in range(3):
        l2 = make_text_with_token_count(L2_TOKENS, seed=100 + i)
        r = await send_and_record(make_messages(sqlfluff_prefix, l2),
                                   f"sqlfluff_T1_{i}",
                                   timeline=timeline)
        phase1_results.append(r)
        print(f"    Phase 1 sqlfluff[{i}]: prompt={r['prompt_tokens']}, "
              f"cached={r['cached_tokens']}, ttft={r['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase1")

    # Phase 2: astroid session T1 (2 个 for LRU, 1 个 for aware)
    timeline.record_event("phase_start", "phase2")
    phase2_results = []
    for i in range(astroid_count):
        l2 = make_text_with_token_count(L2_TOKENS, seed=200 + i)
        r = await send_and_record(make_messages(astroid_prefix, l2),
                                   f"astroid_T1_{i}",
                                   timeline=timeline)
        phase2_results.append(r)
        print(f"    Phase 2 astroid[{i}]: prompt={r['prompt_tokens']}, "
              f"cached={r['cached_tokens']}, ttft={r['ttft_ms']}ms")

    prom_mid = get_prometheus_metrics()
    kv_usage = prom_mid.get("kv_cache_usage_perc", "N/A")
    print(f"    KV usage after Phase 2: {kv_usage}%")
    timeline.record_event("phase_end", "phase2", extra={"kv_usage": kv_usage})

    # Phase 3: sqlfluff session T2 — 观察恢复
    timeline.record_event("phase_start", "phase3")
    l2_t2 = make_text_with_token_count(L2_TOKENS, seed=300)
    r_t2 = await send_and_record(
        make_messages(sqlfluff_prefix, l2_t2), "sqlfluff_T2",
        timeline=timeline)
    print(f"    Phase 3 sqlfluff_T2: prompt={r_t2['prompt_tokens']}, "
          f"cached={r_t2['cached_tokens']}, ttft={r_t2['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase3")

    prom_after = get_prometheus_metrics()
    timeline_data = await timeline.stop()

    expected_l0_l1 = (L0_TOKENS + L1_SQLFLUFF_TOKENS) // BLOCK_SIZE * BLOCK_SIZE
    expected_l0 = L0_TOKENS // BLOCK_SIZE * BLOCK_SIZE

    data = {
        "experiment": exp_name,
        "run_id": run_id,
        "run_type": run_type,
        "astroid_count": astroid_count,
        "l0_tokens": L0_TOKENS,
        "l1_sqlfluff_tokens": L1_SQLFLUFF_TOKENS,
        "l1_astroid_tokens": L1_ASTROID_TOKENS,
        "l2_tokens": L2_TOKENS,
        "block_size": BLOCK_SIZE,
        "expected_cached": {"sqlfluff_T2": expected_l0_l1},
        "requests": phase1_results + phase2_results + [r_t2],
        "prometheus_before": prom_before,
        "prometheus_after": prom_after,
        "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        "timeline": timeline_data,
    }
    save_run(exp_name, run_id, data)

    # 分析
    hit_rate = r_t2["cached_tokens"] / r_t2["prompt_tokens"] if r_t2["prompt_tokens"] > 0 else 0
    print(f"\n  Recovery analysis ({run_type}):")
    print(f"    sqlfluff_T2: cached={r_t2['cached_tokens']}/{r_t2['prompt_tokens']} "
          f"({hit_rate*100:.1f}%), expected L0+L1≈{expected_l0_l1}")

    if r_t2["cached_tokens"] >= expected_l0_l1:
        print(f"    ✅ L0+L1_sqlfluff survived! Agent-aware scheduling helps.")
    elif r_t2["cached_tokens"] >= expected_l0:
        print(f"    ⚠️  Only L0 survived, L1_sqlfluff was evicted")
    else:
        print(f"    ❌ Both L0 and L1 lost")


async def main():
    parser = argparse.ArgumentParser(description="Experiment 5: Agent-Aware Eviction Simulation")
    parser.add_argument("--run", choices=["lru", "aware"], required=True,
                        help="Run type: 'lru' (default LRU) or 'aware' (agent-aware simulated)")
    args = parser.parse_args()

    save_config()
    await wait_for_server()

    exp_name = f"exp5_{args.run}_eviction"

    for i in range(1, NUM_RUNS + 1):
        print(f"\n{'='*50}")
        print(f"Run {i}/{NUM_RUNS} (type={args.run})")
        print(f"{'='*50}")
        await run_exp5(i, args.run)
        if i < NUM_RUNS:
            print("\n⚠️  请重启 vLLM server 后按 Enter 继续...")
            input()

    print(f"\n{'='*50}")
    print("Summarizing...")
    summarize_runs(exp_name)


if __name__ == "__main__":
    asyncio.run(main())
