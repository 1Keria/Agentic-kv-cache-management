"""实验 3：KV Offloading 效果对比

对比有无 CPU offloading 时的驱逐恢复行为：
- 配置 A（有 offloading 8 GiB）：被驱逐的 prefix block 可从 CPU 恢复
- 配置 B（无 offloading）：被驱逐的 prefix block 彻底丢失，需完整重算

请求序列（两种配置相同）：
  Phase 1: req_A [prefix_A (8000) + unique (500)]  — 加载到 GPU
  Phase 2: 5 个不同 prefix 的填充请求 (每个 ~8000 tokens) — 触发驱逐
  Phase 3: req_C [prefix_A + unique_C] — 观察恢复

运行方式：
  # 配置 A：有 offloading
  1. bash scripts/run_vllm_server.sh
  2. python scripts/run_exp3.py --config on

  # 配置 B：无 offloading（需重启 server）
  3. KV_OFFLOAD_GIB=0 bash scripts/run_vllm_server.sh
  4. python scripts/run_exp3.py --config off
"""

import argparse
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exp_utils import (
    make_text_with_token_count, make_messages, make_layered_messages, send_and_record,
    save_run, save_config, summarize_runs, get_prometheus_metrics,
    compute_prometheus_delta, wait_for_server, BLOCK_SIZE,
    KVTimelineCollector,
    get_real_l0_text, get_real_l1_text,
)

PREFIX_A_TOKENS = 8000   # prefix_A 长度
FILL_TOKENS = 8000       # 填充请求 prefix 长度
UNIQUE_TOKENS = 500      # 唯一部分长度
FILL_COUNT = 5           # 填充请求数（固定 5 个，与 spec 一致）
NUM_RUNS = 2


async def run_exp3(run_id: int, config: str):
    """单次实验运行

    Args:
        run_id: 运行编号
        config: "on" (有 offloading) 或 "off" (无 offloading)
    """
    exp_name = f"exp3_offload_{config}"
    print(f"  Config: offloading={'ON (8 GiB)' if config == 'on' else 'OFF'}")

    # 优先使用真实 L0 作为 prefix（如果可用）
    real_l0 = get_real_l0_text()
    if real_l0:
        prefix_a = real_l0
        print(f"  Using REAL L0 as prefix_A from LMCache traces ({len(prefix_a)} chars)")
    else:
        prefix_a = make_text_with_token_count(PREFIX_A_TOKENS, seed=0)
        print(f"  Using SYNTHETIC prefix_A ({PREFIX_A_TOKENS} tokens)")
    unique_a = make_text_with_token_count(UNIQUE_TOKENS, seed=1)
    unique_c = make_text_with_token_count(UNIQUE_TOKENS, seed=2)

    # 启动 Timeline 采集
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    prom_before = get_prometheus_metrics()

    # Phase 1: 加载 prefix_A
    timeline.record_event("phase_start", "phase1")
    r1 = await send_and_record(make_messages(prefix_a, unique_a), "req_A",
                               timeline=timeline)
    print(f"    Phase 1 req_A: prompt={r1['prompt_tokens']}, cached={r1['cached_tokens']}, "
          f"ttft={r1['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase1")

    # Phase 2: 发送 5 个不同 prefix 的填充请求，触发驱逐
    timeline.record_event("phase_start", "phase2")
    fill_results = []
    for i in range(FILL_COUNT):
        fill_prefix = make_text_with_token_count(FILL_TOKENS, seed=100 + i)
        fill_unique = make_text_with_token_count(UNIQUE_TOKENS, seed=200 + i)
        r = await send_and_record(make_messages(fill_prefix, fill_unique),
                                   f"fill_{i}",
                                   timeline=timeline)
        fill_results.append(r)
        print(f"    Phase 2 fill[{i}]: prompt={r['prompt_tokens']}, "
              f"cached={r['cached_tokens']}, ttft={r['ttft_ms']}ms")

    # 采集 KV cache 使用率
    prom_mid = get_prometheus_metrics()
    kv_usage = prom_mid.get("kv_cache_usage_perc", "N/A")
    print(f"    KV usage after Phase 2: {kv_usage}%")
    timeline.record_event("phase_end", "phase2", extra={"kv_usage": kv_usage})

    # Phase 3: 再次请求 prefix_A（恢复请求）
    timeline.record_event("phase_start", "phase3")
    r3 = await send_and_record(make_messages(prefix_a, unique_c), "req_C",
                               timeline=timeline)
    print(f"    Phase 3 req_C: prompt={r3['prompt_tokens']}, cached={r3['cached_tokens']}, "
          f"ttft={r3['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase3")

    prom_after = get_prometheus_metrics()

    # 停止 Timeline
    timeline_data = await timeline.stop()

    prefix_a_survived = r3["cached_tokens"] > 0
    expected_cached = (PREFIX_A_TOKENS // BLOCK_SIZE) * BLOCK_SIZE

    data = {
        "experiment": exp_name,
        "run_id": run_id,
        "offload_config": config,
        "prefix_a_tokens": PREFIX_A_TOKENS,
        "fill_request_tokens": FILL_TOKENS,
        "fill_count": FILL_COUNT,
        "unique_tokens": UNIQUE_TOKENS,
        "block_size": BLOCK_SIZE,
        "expected_cached_tokens": expected_cached,
        "phase1_req": r1,
        "phase2_fill_results": fill_results,
        "phase3_req": r3,
        "prefix_a_survived": prefix_a_survived,
        "kv_usage_before_phase3": kv_usage,
        "phase3_cached_tokens": r3["cached_tokens"],
        "prometheus_before": prom_before,
        "prometheus_after": prom_after,
        "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        "timeline": timeline_data,
    }
    save_run(exp_name, run_id, data)

    # 分析
    status = "✅ SURVIVED (offload recovered)" if prefix_a_survived else "❌ EVICTED (full recomputation)"
    print(f"\n    {status}: cached={r3['cached_tokens']}/{r3['prompt_tokens']}, "
          f"kv_usage={kv_usage}%")

    if r3["ttft_ms"] and r1["ttft_ms"] and r1["ttft_ms"] > 0:
        ratio = r3["ttft_ms"] / r1["ttft_ms"]
        print(f"    req_C TTFT / req_A TTFT = {ratio:.2f}x")
        if prefix_a_survived:
            print(f"    → Offload recovery is {ratio:.1f}x the cold-start TTFT")
        else:
            print(f"    → Full recomputation is {ratio:.1f}x the cold-start TTFT")


async def main():
    parser = argparse.ArgumentParser(description="Experiment 3: KV Offloading Effect Comparison")
    parser.add_argument("--config", choices=["on", "off"], required=True,
                        help="Offloading config: 'on' (8 GiB) or 'off' (no offloading)")
    parser.add_argument("--num-runs", type=int, default=None, help="Override NUM_RUNS")
    args = parser.parse_args()

    save_config()
    await wait_for_server()

    exp_name = f"exp3_offload_{args.config}"

    for i in range(1, (args.num_runs or NUM_RUNS) + 1):
        print(f"\n{'='*50}")
        print(f"Run {i}/{NUM_RUNS} (offload={args.config})")
        print(f"{'='*50}")
        await run_exp3(i, args.config)
        if i < NUM_RUNS:
            print("  → Restarting server (auto mode)...")

    print(f"\n{'='*50}")
    print("Summarizing...")
    summarize_runs(exp_name)


if __name__ == "__main__":
    asyncio.run(main())
