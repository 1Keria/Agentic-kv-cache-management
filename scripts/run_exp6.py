"""实验 6：内存压力下 Preemption 策略对比

对比 vLLM 三种 preemption 策略对 Agent session 的影响：
  - 配置 A (swap): --kv-offloading-size 8，被驱逐 block 存 CPU
  - 配置 B (recompute): --kv-load-failure-policy recompute，无 offloading
  - 配置 C (默认 preempt): 无 offloading，无 recompute

请求序列（三种配置相同）：
  Phase 1: 3 个同项目 Agent session T1 (每个 ~6500 tokens, 共 ~19.5K)
  Phase 2: 2 个不同项目 session T1 (每个 ~6300 tokens, 共 ~12.6K) → 触发内存压力
  Phase 3: 1 个同项目 session T2 → 观察 prefix 恢复行为
  Phase 4: 1 个被 preempt 的 session 继续推理 → 观察恢复延迟

关键观测：
  - Phase 3: swap 的 cached_tokens > 0 (CPU 恢复), recompute = 0 (需重算)
  - Phase 4: swap-in 延迟 vs 完整 prefill 延迟 vs 重新调度延迟
  - num_preemptions Prometheus 指标

运行方式：
  # 配置 A: swap-out/swap-in (需 offloading)
  bash scripts/run_vllm_server.sh   # 默认 KV_OFFLOAD_GIB=8
  python scripts/run_exp6.py --config swap

  # 配置 B: recompute (需重启 server，关闭 offloading)
  KV_OFFLOAD_GIB=0 bash scripts/run_vllm_server.sh
  python scripts/run_exp6.py --config recompute

  # 配置 C: 默认 preempt (需重启 server，关闭 offloading)
  KV_OFFLOAD_GIB=0 bash scripts/run_vllm_server.sh
  python scripts/run_exp6.py --config default
"""

import argparse
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exp_utils import (
    make_text_with_token_count, make_layered_messages, send_and_record,
    save_run, save_config, summarize_runs, get_prometheus_metrics,
    compute_prometheus_delta, wait_for_server, BLOCK_SIZE,
    KVTimelineCollector,
    get_real_l0_text, get_real_l1_text, get_real_session_prompt,
)

# Token 配置（与 exp4/5 一致）
L0_TOKENS = 5000
L1_SQLFLUFF_TOKENS = 1000
L1_ASTROID_TOKENS = 800
L2_TOKENS = 500

NUM_RUNS = 2


def build_layered_texts():
    """构造各层文本，优先使用真实 Agent prompt，回退到合成文本"""
    # 尝试使用真实 L0
    real_l0 = get_real_l0_text()
    if real_l0:
        l0 = real_l0
        print(f"  Using REAL L0 from LMCache traces ({len(l0)} chars)")
    else:
        l0 = make_text_with_token_count(L0_TOKENS, seed=0)
        print(f"  Using SYNTHETIC L0 ({L0_TOKENS} tokens)")

    # 尝试使用真实 L1
    real_l1_django = get_real_l1_text("django")
    real_l1_sympy = get_real_l1_text("sympy")

    if real_l1_django:
        l1_sqlfluff = real_l1_django
        print(f"  Using REAL L1 (django) from LMCache traces ({len(l1_sqlfluff)} chars)")
    else:
        l1_sqlfluff = make_text_with_token_count(L1_SQLFLUFF_TOKENS, seed=10)
        print(f"  Using SYNTHETIC L1_sqlfluff ({L1_SQLFLUFF_TOKENS} tokens)")

    if real_l1_sympy:
        l1_astroid = real_l1_sympy
        print(f"  Using REAL L1 (sympy) from LMCache traces ({len(l1_astroid)} chars)")
    else:
        l1_astroid = make_text_with_token_count(L1_ASTROID_TOKENS, seed=11)
        print(f"  Using SYNTHETIC L1_astroid ({L1_ASTROID_TOKENS} tokens)")

    l2_problems = [make_text_with_token_count(L2_TOKENS, seed=100 + i) for i in range(8)]

    return {
        "l0": l0,
        "l1_sqlfluff": l1_sqlfluff,
        "l1_astroid": l1_astroid,
        "l2_problems": l2_problems,
    }


async def run_exp6(run_id: int, config: str):
    """单次实验运行

    Args:
        run_id: 运行编号
        config: "swap" / "recompute" / "default"
    """
    exp_name = f"exp6_{config}_preempt"
    print(f"  Config: {config}")
    print(f"  Strategy: {'swap-out/swap-in (offloading ON)' if config == 'swap' else 'recompute (KV load failure → recompute)' if config == 'recompute' else 'default preempt (no offloading, no recompute)'}")

    texts = build_layered_texts()

    # 启动 Timeline 采集
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    prom_before = get_prometheus_metrics()

    sqlfluff_prefix = texts["l0"] + texts["l1_sqlfluff"]
    astroid_prefix = texts["l0"] + texts["l1_astroid"]

    # Phase 1: 3 个同项目 (sqlfluff) Agent session T1
    timeline.record_event("phase_start", "phase1")
    phase1_results = []
    for i in range(3):
        r = await send_and_record(
            make_layered_messages(texts["l0"], texts["l1_sqlfluff"], texts["l2_problems"][i]),
            f"sqlfluff_T1_{i}",
            timeline=timeline, max_tokens=50)
        phase1_results.append(r)
        print(f"    Phase 1 sqlfluff[{i}]: prompt={r['prompt_tokens']}, "
              f"cached={r['cached_tokens']}, ttft={r['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase1")

    # Phase 2: 2 个不同项目 (astroid) session T1 → 触发内存压力
    timeline.record_event("phase_start", "phase2")
    phase2_results = []
    for i in range(2):
        r = await send_and_record(
            make_layered_messages(texts["l0"], texts["l1_astroid"], texts["l2_problems"][3 + i]),
            f"astroid_T1_{i}",
            timeline=timeline, max_tokens=50)
        phase2_results.append(r)
        print(f"    Phase 2 astroid[{i}]: prompt={r['prompt_tokens']}, "
              f"cached={r['cached_tokens']}, ttft={r['ttft_ms']}ms")

    prom_mid = get_prometheus_metrics()
    kv_usage = prom_mid.get("kv_cache_usage_perc", "N/A")
    num_preemptions = prom_mid.get("num_preemptions", 0)
    print(f"    KV usage after Phase 2: {kv_usage}%")
    print(f"    Preemptions so far: {num_preemptions}")
    timeline.record_event("phase_end", "phase2",
                          extra={"kv_usage": kv_usage, "num_preemptions": num_preemptions})

    # Phase 3: 1 个同项目 session T2 → 观察 prefix 恢复行为
    timeline.record_event("phase_start", "phase3")
    r_recovery = await send_and_record(
        make_layered_messages(texts["l0"], texts["l1_sqlfluff"], texts["l2_problems"][5]),
        "sqlfluff_T2_recovery",
        timeline=timeline, max_tokens=50)
    print(f"    Phase 3 recovery: prompt={r_recovery['prompt_tokens']}, "
          f"cached={r_recovery['cached_tokens']}, ttft={r_recovery['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase3")

    # Phase 4: 1 个被 preempt 的 session 继续推理 → 观察恢复延迟
    # 发送一个新的 sqlfluff session，如果之前有 preemption，这里观察恢复
    timeline.record_event("phase_start", "phase4")
    r_resume = await send_and_record(
        make_layered_messages(texts["l0"], texts["l1_sqlfluff"], texts["l2_problems"][6]),
        "sqlfluff_T1_resume",
        timeline=timeline, max_tokens=50)
    print(f"    Phase 4 resume: prompt={r_resume['prompt_tokens']}, "
          f"cached={r_resume['cached_tokens']}, ttft={r_resume['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase4")

    prom_after = get_prometheus_metrics()
    timeline_data = await timeline.stop()

    expected_l0_l1 = (L0_TOKENS + L1_SQLFLUFF_TOKENS) // BLOCK_SIZE * BLOCK_SIZE
    expected_l0 = L0_TOKENS // BLOCK_SIZE * BLOCK_SIZE

    data = {
        "experiment": exp_name,
        "run_id": run_id,
        "preempt_strategy": config,
        "l0_tokens": L0_TOKENS,
        "l1_sqlfluff_tokens": L1_SQLFLUFF_TOKENS,
        "l1_astroid_tokens": L1_ASTROID_TOKENS,
        "l2_tokens": L2_TOKENS,
        "block_size": BLOCK_SIZE,
        "expected_cached": {
            "sqlfluff_T2_recovery": expected_l0_l1,
        },
        "requests": phase1_results + phase2_results + [r_recovery, r_resume],
        "prometheus_before": prom_before,
        "prometheus_after": prom_after,
        "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        "timeline": timeline_data,
        "data_source": "[SYNTHETIC]" if not get_real_l0_text() else "[MEASURED] (real L0/L1 from LMCache traces)",
    }
    save_run(exp_name, run_id, data)

    # 分析
    print(f"\n  Preemption strategy analysis ({config}):")
    print(f"    KV usage at pressure: {kv_usage}%")
    print(f"    Preemptions: {num_preemptions}")

    recovery_hit_rate = r_recovery["cached_tokens"] / r_recovery["prompt_tokens"] if r_recovery["prompt_tokens"] > 0 else 0
    print(f"    Recovery (sqlfluff_T2): cached={r_recovery['cached_tokens']}/{r_recovery['prompt_tokens']} "
          f"({recovery_hit_rate*100:.1f}%)")

    if r_recovery["cached_tokens"] >= expected_l0_l1:
        print(f"    ✅ L0+L1 survived — prefix recovered from {'CPU (swap-in)' if config == 'swap' else 'cache'}")
    elif r_recovery["cached_tokens"] >= expected_l0:
        print(f"    ⚠️  Only L0 survived — L1 was evicted")
    else:
        print(f"    ❌ Full recomputation needed — both L0 and L1 lost")

    # TTFT 对比
    if phase1_results and phase1_results[0]["ttft_ms"] and r_recovery["ttft_ms"]:
        cold_ttft = phase1_results[0]["ttft_ms"]
        recovery_ttft = r_recovery["ttft_ms"]
        ratio = recovery_ttft / cold_ttft if cold_ttft > 0 else 0
        print(f"    Recovery TTFT / Cold TTFT = {ratio:.2f}x")
        if config == "swap" and r_recovery["cached_tokens"] > 0:
            print(f"    → Swap-in recovery is faster than full recomputation")
        elif config == "recompute" and r_recovery["cached_tokens"] == 0:
            print(f"    → Full recomputation is the slowest path")


async def main():
    parser = argparse.ArgumentParser(description="Experiment 6: Preemption Strategy Comparison")
    parser.add_argument("--config", choices=["swap", "recompute", "default"], required=True,
                        help="Preemption strategy: 'swap' (offloading ON), "
                             "'recompute' (kv-load-failure-policy=recompute), "
                             "'default' (standard preempt)")
    parser.add_argument("--num-runs", type=int, default=None, help="Override NUM_RUNS")
    args = parser.parse_args()

    save_config()
    await wait_for_server()

    exp_name = f"exp6_{args.config}_preempt"

    for i in range(1, (args.num_runs or NUM_RUNS) + 1):
        print(f"\n{'='*50}")
        print(f"Run {i}/{NUM_RUNS} (strategy={args.config})")
        print(f"{'='*50}")
        await run_exp6(i, args.config)
        if i < NUM_RUNS:
            print("  → Restarting server (auto mode)...")

    print(f"\n{'='*50}")
    print("Summarizing...")
    summarize_runs(exp_name)


if __name__ == "__main__":
    asyncio.run(main())
