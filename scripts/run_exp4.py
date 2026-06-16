"""实验 4：Agent 多 Session 复用模拟

模拟 SWE-bench agent 场景，测量跨 session 的 KV cache 复用率。
6 个子场景（与 spec v3 对齐）：

  4.1 同 Session 多轮复用：S1-T1 冷启动 → S1-T2 全命中
  4.2 同项目跨 Session 复用：S2 (sqlfluff, 不同 problem) 命中 L0+L1
  4.3 跨项目跨 Session 复用：S3 (astroid) 仅命中 L0
  4.4 多 Session 并行竞争：同时发 S_A/S_B/S_C，观测 L0 共享
  4.5 驱逐压力下 L0/L1 保护：5 sqlfluff + 2 astroid + recovery（需 --config on/off）
  4.6 Offloading 层级恢复速度：GPU 命中/CPU 恢复/完整重算 TTFT 对比（需 --config on/off）

Token 配置（与 spec 一致，每个 session ~6500 tokens）：
  L0 = 5000 (全局共享 system prompt + tools)
  L1_sqlfluff = 1000 (sqlfluff 项目级上下文)
  L1_astroid = 800 (astroid 项目级上下文)
  L2 = 500 (session 级 problem statement)

运行方式：
  # 子场景 4.1~4.4（默认 offloading）
  bash scripts/run_vllm_server.sh
  python scripts/run_exp4.py --subexp 4.1
  python scripts/run_exp4.py --subexp 4.2   # 重启 server
  python scripts/run_exp4.py --subexp 4.3   # 重启 server
  python scripts/run_exp4.py --subexp 4.4   # 重启 server

  # 子场景 4.5/4.6 有 offloading
  python scripts/run_exp4.py --subexp 4.5 --config on   # 重启 server
  python scripts/run_exp4.py --subexp 4.6 --config on   # 重启 server

  # 子场景 4.5/4.6 无 offloading（需重启 server）
  KV_OFFLOAD_GIB=0 bash scripts/run_vllm_server.sh
  python scripts/run_exp4.py --subexp 4.5 --config off
  python scripts/run_exp4.py --subexp 4.6 --config off
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

# L0/L1/L2 Token 配置（与 spec v3 一致）
L0_TOKENS = 5000
L1_SQLFLUFF_TOKENS = 1000
L1_ASTROID_TOKENS = 800
L2_TOKENS = 500
HISTORY_TOKENS = 500
NEW_MSG_TOKENS = 200

# sqlfluff session T1 = L0 + L1_sqlfluff + L2 = 6500 tokens
# astroid session T1 = L0 + L1_astroid + L2 = 6300 tokens

NUM_RUNS = 2
EXPERIMENT_DIR_NAME = "exp4_agent_session"


def build_layered_texts():
    """构造各层文本，所有子场景共用"""
    l0 = make_text_with_token_count(L0_TOKENS, seed=0)
    l1_sqlfluff = make_text_with_token_count(L1_SQLFLUFF_TOKENS, seed=10)
    l1_astroid = make_text_with_token_count(L1_ASTROID_TOKENS, seed=11)
    l2_problem1 = make_text_with_token_count(L2_TOKENS, seed=20)
    l2_problem2 = make_text_with_token_count(L2_TOKENS, seed=21)
    l2_problem3 = make_text_with_token_count(L2_TOKENS, seed=22)
    l2_problem_a = make_text_with_token_count(L2_TOKENS, seed=23)
    l2_problem_b = make_text_with_token_count(L2_TOKENS, seed=24)
    l2_problem_c = make_text_with_token_count(L2_TOKENS, seed=25)
    history1 = make_text_with_token_count(HISTORY_TOKENS, seed=30)
    new_msg1 = make_text_with_token_count(NEW_MSG_TOKENS, seed=31)
    return {
        "l0": l0,
        "l1_sqlfluff": l1_sqlfluff,
        "l1_astroid": l1_astroid,
        "l2_problem1": l2_problem1,
        "l2_problem2": l2_problem2,
        "l2_problem3": l2_problem3,
        "l2_problem_a": l2_problem_a,
        "l2_problem_b": l2_problem_b,
        "l2_problem_c": l2_problem_c,
        "history1": history1,
        "new_msg1": new_msg1,
    }


# ---------------------------------------------------------------------------
# 子场景 4.1：同 Session 多轮复用
# ---------------------------------------------------------------------------

async def run_4_1(run_id: int, texts: dict):
    """S1-T1 冷启动 → S1-T2 全命中"""
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    prom_before = get_prometheus_metrics()

    # S1-T1: [L0 + L1_sqlfluff + problem_1]
    s1_prefix = texts["l0"] + texts["l1_sqlfluff"]
    s1_t1 = await send_and_record(
        make_messages(s1_prefix, texts["l2_problem1"]), "S1-T1",
        timeline=timeline)
    print(f"  S1-T1: prompt={s1_t1['prompt_tokens']}, cached={s1_t1['cached_tokens']}, "
          f"ttft={s1_t1['ttft_ms']}ms")

    # S1-T2: [L0 + L1_sqlfluff + problem_1 + history + new_msg]
    s1_prefix_t2 = s1_prefix + texts["l2_problem1"] + texts["history1"]
    s1_t2 = await send_and_record(
        make_messages(s1_prefix_t2, texts["new_msg1"]), "S1-T2",
        timeline=timeline)
    print(f"  S1-T2: prompt={s1_t2['prompt_tokens']}, cached={s1_t2['cached_tokens']}, "
          f"ttft={s1_t2['ttft_ms']}ms")

    prom_after = get_prometheus_metrics()
    timeline_data = await timeline.stop()

    expected_cached_s1_t2 = (L0_TOKENS + L1_SQLFLUFF_TOKENS + L2_TOKENS) // BLOCK_SIZE * BLOCK_SIZE

    data = {
        "experiment": EXPERIMENT_DIR_NAME,
        "subexp": "4.1",
        "run_id": run_id,
        "description": "Same session multi-turn reuse",
        "l0_tokens": L0_TOKENS,
        "l1_sqlfluff_tokens": L1_SQLFLUFF_TOKENS,
        "l2_tokens": L2_TOKENS,
        "block_size": BLOCK_SIZE,
        "expected_cached": {"S1-T2": expected_cached_s1_t2},
        "requests": [s1_t1, s1_t2],
        "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        "timeline": timeline_data,
    }
    save_run(EXPERIMENT_DIR_NAME, run_id, data)

    hit_rate = s1_t2["cached_tokens"] / s1_t2["prompt_tokens"] if s1_t2["prompt_tokens"] > 0 else 0
    print(f"  S1-T2 hit rate: {hit_rate*100:.1f}% (expected ~100%)")


# ---------------------------------------------------------------------------
# 子场景 4.2：同项目跨 Session 复用
# ---------------------------------------------------------------------------

async def run_4_2(run_id: int, texts: dict):
    """S1-T1 → S2-T1 (同项目 sqlfluff, 不同 problem, 命中 L0+L1)"""
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    prom_before = get_prometheus_metrics()

    # S1-T1: [L0 + L1_sqlfluff + problem_1]
    s1_prefix = texts["l0"] + texts["l1_sqlfluff"]
    s1_t1 = await send_and_record(
        make_messages(s1_prefix, texts["l2_problem1"]), "S1-T1",
        timeline=timeline)
    print(f"  S1-T1: prompt={s1_t1['prompt_tokens']}, cached={s1_t1['cached_tokens']}, "
          f"ttft={s1_t1['ttft_ms']}ms")

    # S2-T1: [L0 + L1_sqlfluff + problem_2] — 同项目不同 problem
    s2_t1 = await send_and_record(
        make_messages(s1_prefix, texts["l2_problem2"]), "S2-T1",
        timeline=timeline)
    print(f"  S2-T1: prompt={s2_t1['prompt_tokens']}, cached={s2_t1['cached_tokens']}, "
          f"ttft={s2_t1['ttft_ms']}ms")

    prom_after = get_prometheus_metrics()
    timeline_data = await timeline.stop()

    expected_cached_s2 = (L0_TOKENS + L1_SQLFLUFF_TOKENS) // BLOCK_SIZE * BLOCK_SIZE

    data = {
        "experiment": EXPERIMENT_DIR_NAME,
        "subexp": "4.2",
        "run_id": run_id,
        "description": "Same project cross-session reuse (sqlfluff)",
        "l0_tokens": L0_TOKENS,
        "l1_sqlfluff_tokens": L1_SQLFLUFF_TOKENS,
        "l2_tokens": L2_TOKENS,
        "block_size": BLOCK_SIZE,
        "expected_cached": {"S2-T1": expected_cached_s2},
        "requests": [s1_t1, s2_t1],
        "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        "timeline": timeline_data,
    }
    save_run(EXPERIMENT_DIR_NAME, run_id, data)

    hit_rate = s2_t1["cached_tokens"] / s2_t1["prompt_tokens"] if s2_t1["prompt_tokens"] > 0 else 0
    expected_rate = expected_cached_s2 / (L0_TOKENS + L1_SQLFLUFF_TOKENS + L2_TOKENS) * 100
    print(f"  S2-T1 hit rate: {hit_rate*100:.1f}% (expected ~{expected_rate:.0f}%)")


# ---------------------------------------------------------------------------
# 子场景 4.3：跨项目跨 Session 复用
# ---------------------------------------------------------------------------

async def run_4_3(run_id: int, texts: dict):
    """S1-T1 (sqlfluff) → S3-T1 (astroid)，仅命中 L0"""
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    prom_before = get_prometheus_metrics()

    # S1-T1: [L0 + L1_sqlfluff + problem_1]
    s1_prefix = texts["l0"] + texts["l1_sqlfluff"]
    s1_t1 = await send_and_record(
        make_messages(s1_prefix, texts["l2_problem1"]), "S1-T1",
        timeline=timeline)
    print(f"  S1-T1: prompt={s1_t1['prompt_tokens']}, cached={s1_t1['cached_tokens']}, "
          f"ttft={s1_t1['ttft_ms']}ms")

    # S3-T1: [L0 + L1_astroid + problem_3] — 不同项目
    s3_prefix = texts["l0"] + texts["l1_astroid"]
    s3_t1 = await send_and_record(
        make_messages(s3_prefix, texts["l2_problem3"]), "S3-T1",
        timeline=timeline)
    print(f"  S3-T1: prompt={s3_t1['prompt_tokens']}, cached={s3_t1['cached_tokens']}, "
          f"ttft={s3_t1['ttft_ms']}ms")

    prom_after = get_prometheus_metrics()
    timeline_data = await timeline.stop()

    expected_cached_s3 = L0_TOKENS // BLOCK_SIZE * BLOCK_SIZE

    data = {
        "experiment": EXPERIMENT_DIR_NAME,
        "subexp": "4.3",
        "run_id": run_id,
        "description": "Cross-project cross-session reuse (sqlfluff→astroid)",
        "l0_tokens": L0_TOKENS,
        "l1_sqlfluff_tokens": L1_SQLFLUFF_TOKENS,
        "l1_astroid_tokens": L1_ASTROID_TOKENS,
        "l2_tokens": L2_TOKENS,
        "block_size": BLOCK_SIZE,
        "expected_cached": {"S3-T1": expected_cached_s3},
        "requests": [s1_t1, s3_t1],
        "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        "timeline": timeline_data,
    }
    save_run(EXPERIMENT_DIR_NAME, run_id, data)

    hit_rate = s3_t1["cached_tokens"] / s3_t1["prompt_tokens"] if s3_t1["prompt_tokens"] > 0 else 0
    expected_rate = expected_cached_s3 / (L0_TOKENS + L1_ASTROID_TOKENS + L2_TOKENS) * 100
    print(f"  S3-T1 hit rate: {hit_rate*100:.1f}% (expected ~{expected_rate:.0f}%)")


# ---------------------------------------------------------------------------
# 子场景 4.4：多 Session 并行竞争
# ---------------------------------------------------------------------------

async def run_4_4(run_id: int, texts: dict):
    """同时发 S_A/S_B/S_C，观测 L0 共享和 L1 共享"""
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    prom_before = get_prometheus_metrics()

    # 3 个并发请求
    sqlfluff_prefix = texts["l0"] + texts["l1_sqlfluff"]
    astroid_prefix = texts["l0"] + texts["l1_astroid"]

    tasks = [
        send_and_record(make_messages(sqlfluff_prefix, texts["l2_problem_a"]),
                        "S_A", timeline=timeline),
        send_and_record(make_messages(sqlfluff_prefix, texts["l2_problem_b"]),
                        "S_B", timeline=timeline),
        send_and_record(make_messages(astroid_prefix, texts["l2_problem_c"]),
                        "S_C", timeline=timeline),
    ]

    print(f"  Sending 3 concurrent requests (S_A, S_B, S_C)...")
    results = await asyncio.gather(*tasks)

    for r in results:
        print(f"    {r['label']}: prompt={r['prompt_tokens']}, "
              f"cached={r['cached_tokens']}, ttft={r['ttft_ms']}ms")

    prom_after = get_prometheus_metrics()
    timeline_data = await timeline.stop()

    expected_cached_sa = (L0_TOKENS + L1_SQLFLUFF_TOKENS) // BLOCK_SIZE * BLOCK_SIZE
    expected_cached_sc = L0_TOKENS // BLOCK_SIZE * BLOCK_SIZE

    data = {
        "experiment": EXPERIMENT_DIR_NAME,
        "subexp": "4.4",
        "run_id": run_id,
        "description": "Multi-session concurrent competition",
        "l0_tokens": L0_TOKENS,
        "l1_sqlfluff_tokens": L1_SQLFLUFF_TOKENS,
        "l1_astroid_tokens": L1_ASTROID_TOKENS,
        "l2_tokens": L2_TOKENS,
        "block_size": BLOCK_SIZE,
        "expected_cached": {
            "S_A": expected_cached_sa,
            "S_B": expected_cached_sa,
            "S_C": expected_cached_sc,
        },
        "requests": list(results),
        "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        "timeline": timeline_data,
    }
    save_run(EXPERIMENT_DIR_NAME, run_id, data)

    # 分析
    a_results = [r for r in results if r["label"] == "S_A"]
    b_results = [r for r in results if r["label"] == "S_B"]
    c_results = [r for r in results if r["label"] == "S_C"]

    print(f"\n  Concurrent analysis:")
    for r in results:
        hit_rate = r["cached_tokens"] / r["prompt_tokens"] if r["prompt_tokens"] > 0 else 0
        print(f"    {r['label']}: cached={r['cached_tokens']}/{r['prompt_tokens']} "
              f"({hit_rate*100:.1f}%)")

    # L0 是否被所有请求共享
    all_cached_l0 = all(r["cached_tokens"] >= L0_TOKENS // BLOCK_SIZE * BLOCK_SIZE
                        for r in results if r["cached_tokens"] > 0)
    # 同项目 S_A, S_B 是否共享 L1_sqlfluff
    ab_share_l1 = (any(r["cached_tokens"] >= (L0_TOKENS + L1_SQLFLUFF_TOKENS) // BLOCK_SIZE * BLOCK_SIZE
                       for r in a_results + b_results if r["cached_tokens"] > 0))

    print(f"    L0 shared by all: {all_cached_l0}")
    print(f"    L1_sqlfluff shared by S_A/S_B: {ab_share_l1}")


# ---------------------------------------------------------------------------
# 子场景 4.5：驱逐压力下 L0/L1 保护
# ---------------------------------------------------------------------------

async def run_4_5(run_id: int, texts: dict, config: str):
    """5 sqlfluff T1 + 2 astroid T1 → recovery sqlfluff T1

    Args:
        config: "on" (有 offloading) 或 "off" (无 offloading)
    """
    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    prom_before = get_prometheus_metrics()

    sqlfluff_prefix = texts["l0"] + texts["l1_sqlfluff"]
    astroid_prefix = texts["l0"] + texts["l1_astroid"]

    # Phase 1: 5 个 sqlfluff session T1 (每个 ~6500 tokens, 共 ~32.5K)
    timeline.record_event("phase_start", "phase1")
    phase1_results = []
    for i in range(5):
        l2 = make_text_with_token_count(L2_TOKENS, seed=100 + i)
        r = await send_and_record(make_messages(sqlfluff_prefix, l2),
                                   f"sqlfluff_T1_{i}",
                                   timeline=timeline)
        phase1_results.append(r)
        print(f"    Phase 1 sqlfluff[{i}]: prompt={r['prompt_tokens']}, "
              f"cached={r['cached_tokens']}, ttft={r['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase1")

    # Phase 2: 2 个 astroid session T1 (每个 ~6300 tokens, 共 ~12.6K) → 触发驱逐
    timeline.record_event("phase_start", "phase2")
    phase2_results = []
    for i in range(2):
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

    # Phase 3: 1 个 sqlfluff session T1 — 观察恢复
    timeline.record_event("phase_start", "phase3")
    l2_recovery = make_text_with_token_count(L2_TOKENS, seed=300)
    r_recovery = await send_and_record(
        make_messages(sqlfluff_prefix, l2_recovery), "recovery_sqlfluff",
        timeline=timeline)
    print(f"    Phase 3 recovery: prompt={r_recovery['prompt_tokens']}, "
          f"cached={r_recovery['cached_tokens']}, ttft={r_recovery['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase3")

    prom_after = get_prometheus_metrics()
    timeline_data = await timeline.stop()

    expected_l0_l1 = (L0_TOKENS + L1_SQLFLUFF_TOKENS) // BLOCK_SIZE * BLOCK_SIZE

    data = {
        "experiment": EXPERIMENT_DIR_NAME,
        "subexp": f"4.5_offload_{config}",
        "run_id": run_id,
        "description": "Eviction pressure L0/L1 protection",
        "offload_config": config,
        "l0_tokens": L0_TOKENS,
        "l1_sqlfluff_tokens": L1_SQLFLUFF_TOKENS,
        "l1_astroid_tokens": L1_ASTROID_TOKENS,
        "l2_tokens": L2_TOKENS,
        "block_size": BLOCK_SIZE,
        "expected_cached": {"recovery_sqlfluff": expected_l0_l1},
        "requests": phase1_results + phase2_results + [r_recovery],
        "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        "timeline": timeline_data,
    }
    save_run(EXPERIMENT_DIR_NAME, run_id, data)

    hit_rate = r_recovery["cached_tokens"] / r_recovery["prompt_tokens"] if r_recovery["prompt_tokens"] > 0 else 0
    print(f"\n  Recovery analysis (offload={config}):")
    print(f"    cached={r_recovery['cached_tokens']}/{r_recovery['prompt_tokens']} "
          f"({hit_rate*100:.1f}%), expected L0+L1≈{expected_l0_l1}")

    if r_recovery["cached_tokens"] >= expected_l0_l1:
        print(f"    ✅ L0+L1_sqlfluff survived eviction!")
    elif r_recovery["cached_tokens"] >= L0_TOKENS // BLOCK_SIZE * BLOCK_SIZE:
        print(f"    ⚠️  Only L0 survived, L1_sqlfluff was evicted")
    else:
        print(f"    ❌ Both L0 and L1 lost — full recomputation needed")


# ---------------------------------------------------------------------------
# 子场景 4.6：Offloading 层级恢复速度
# ---------------------------------------------------------------------------

async def run_4_6(run_id: int, config: str):
    """三种恢复路径 TTFT 对比：GPU 命中 / CPU 恢复 / 完整重算

    设计：
      Phase 0: req_A [prefix ~6000 tokens] — 加载到 GPU
      Phase 0.5: req_B [prefix_A + unique_B] — GPU 直接命中（无驱逐）
      Phase 1: req_A (重新加载)
      Phase 2: 大量不同请求，驱逐 prefix_A
      Phase 3: req_C [prefix_A + unique_C] — offload 恢复 或 完整重算

    三种路径 TTFT：
      - GPU 直接命中 = Phase 0.5 的 req_B TTFT
      - CPU 恢复 = Phase 3 (config=on) 的 req_C TTFT
      - 完整重算 = Phase 3 (config=off) 的 req_C TTFT
    """
    prefix_tokens = 6000
    unique_tokens = 500

    prefix_a = make_text_with_token_count(prefix_tokens, seed=0)
    unique_a = make_text_with_token_count(unique_tokens, seed=1)
    unique_b = make_text_with_token_count(unique_tokens, seed=2)
    unique_c = make_text_with_token_count(unique_tokens, seed=3)

    timeline = KVTimelineCollector(interval=0.5)
    await timeline.start()

    prom_before = get_prometheus_metrics()

    # Phase 0: 加载 prefix_A 到 GPU
    timeline.record_event("phase_start", "phase0")
    r0 = await send_and_record(make_messages(prefix_a, unique_a), "req_A",
                               timeline=timeline)
    print(f"    Phase 0 req_A: prompt={r0['prompt_tokens']}, cached={r0['cached_tokens']}, "
          f"ttft={r0['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase0")

    # Phase 0.5: GPU 直接命中（prefix_A 仍在 cache 中）
    timeline.record_event("phase_start", "phase0.5")
    r_gpu_hit = await send_and_record(make_messages(prefix_a, unique_b), "req_B_gpu_hit",
                                      timeline=timeline)
    print(f"    Phase 0.5 req_B (GPU hit): prompt={r_gpu_hit['prompt_tokens']}, "
          f"cached={r_gpu_hit['cached_tokens']}, ttft={r_gpu_hit['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase0.5")

    # Phase 1: 重新加载 prefix_A
    timeline.record_event("phase_start", "phase1")
    r1 = await send_and_record(make_messages(prefix_a, unique_a), "req_A_reload",
                               timeline=timeline)
    print(f"    Phase 1 req_A reload: prompt={r1['prompt_tokens']}, "
          f"cached={r1['cached_tokens']}, ttft={r1['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase1")

    # Phase 2: 发送大量不同请求，驱逐 prefix_A
    # GPU KV 容量 ~44K tokens，当前占用 ~6K，需填充 ~40K tokens
    # 每个填充请求 ~8000 tokens，需 ~5 个
    timeline.record_event("phase_start", "phase2")
    fill_results = []
    for i in range(5):
        fill_prefix = make_text_with_token_count(8000, seed=1000 + i)
        fill_unique = make_text_with_token_count(500, seed=2000 + i)
        r = await send_and_record(make_messages(fill_prefix, fill_unique),
                                   f"fill_{i}",
                                   timeline=timeline)
        fill_results.append(r)
        print(f"    Phase 2 fill[{i}]: prompt={r['prompt_tokens']}, "
              f"cached={r['cached_tokens']}, ttft={r['ttft_ms']}ms")

    prom_mid = get_prometheus_metrics()
    kv_usage = prom_mid.get("kv_cache_usage_perc", "N/A")
    print(f"    KV usage after Phase 2: {kv_usage}%")
    timeline.record_event("phase_end", "phase2", extra={"kv_usage": kv_usage})

    # Phase 3: req_C — 恢复或完整重算
    timeline.record_event("phase_start", "phase3")
    r3 = await send_and_record(make_messages(prefix_a, unique_c), "req_C",
                               timeline=timeline)
    print(f"    Phase 3 req_C: prompt={r3['prompt_tokens']}, cached={r3['cached_tokens']}, "
          f"ttft={r3['ttft_ms']}ms")
    timeline.record_event("phase_end", "phase3")

    prom_after = get_prometheus_metrics()
    timeline_data = await timeline.stop()

    # 分析三种路径 TTFT
    gpu_hit_ttft = r_gpu_hit["ttft_ms"]
    recovery_ttft = r3["ttft_ms"]
    cold_start_ttft = r0["ttft_ms"]

    data = {
        "experiment": EXPERIMENT_DIR_NAME,
        "subexp": f"4.6_offload_{config}",
        "run_id": run_id,
        "description": "Offloading tier recovery speed comparison",
        "offload_config": config,
        "prefix_tokens": prefix_tokens,
        "unique_tokens": unique_tokens,
        "block_size": BLOCK_SIZE,
        "recovery_paths": {
            "gpu_hit_ttft_ms": gpu_hit_ttft,
            "recovery_ttft_ms": recovery_ttft,
            "cold_start_ttft_ms": cold_start_ttft,
            "recovery_cached_tokens": r3["cached_tokens"],
            "gpu_hit_cached_tokens": r_gpu_hit["cached_tokens"],
        },
        "requests": [r0, r_gpu_hit, r1] + fill_results + [r3],
        "prometheus_delta": compute_prometheus_delta(prom_before, prom_after),
        "timeline": timeline_data,
    }
    save_run(EXPERIMENT_DIR_NAME, run_id, data)

    print(f"\n  Three-path TTFT comparison (offload={config}):")
    print(f"    GPU direct hit:    {gpu_hit_ttft:.0f}ms (cached={r_gpu_hit['cached_tokens']})")
    print(f"    {'CPU offload recovery' if config == 'on' else 'Full recomputation'}: "
          f"{recovery_ttft:.0f}ms (cached={r3['cached_tokens']})")
    print(f"    Cold start:        {cold_start_ttft:.0f}ms (cached={r0['cached_tokens']})")

    if cold_start_ttft > 0:
        if config == "on":
            ratio = recovery_ttft / cold_start_ttft
            print(f"    CPU recovery / cold start = {ratio:.2f}x")
        else:
            ratio = recovery_ttft / cold_start_ttft
            print(f"    Full recompute / cold start = {ratio:.2f}x")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Experiment 4: Agent Multi-Session KV Reuse")
    parser.add_argument("--subexp", choices=["4.1", "4.2", "4.3", "4.4", "4.5", "4.6"],
                        required=True, help="Sub-experiment to run")
    parser.add_argument("--config", choices=["on", "off"], default=None,
                        help="Offloading config (required for 4.5 and 4.6)")
    args = parser.parse_args()

    # 验证 4.5/4.6 需要 --config
    if args.subexp in ("4.5", "4.6") and args.config is None:
        parser.error(f"--config is required for sub-experiment {args.subexp}")

    save_config()
    await wait_for_server()

    for i in range(1, NUM_RUNS + 1):
        print(f"\n{'='*50}")
        print(f"Run {i}/{NUM_RUNS} (subexp={args.subexp})"
              + (f", config={args.config}" if args.config else ""))
        print(f"{'='*50}")

        if args.subexp == "4.1":
            texts = build_layered_texts()
            await run_4_1(i, texts)
        elif args.subexp == "4.2":
            texts = build_layered_texts()
            await run_4_2(i, texts)
        elif args.subexp == "4.3":
            texts = build_layered_texts()
            await run_4_3(i, texts)
        elif args.subexp == "4.4":
            texts = build_layered_texts()
            await run_4_4(i, texts)
        elif args.subexp == "4.5":
            texts = build_layered_texts()
            await run_4_5(i, texts, args.config)
        elif args.subexp == "4.6":
            await run_4_6(i, args.config)

        if i < NUM_RUNS:
            print("\n⚠️  请重启 vLLM server 后按 Enter 继续...")
            input()

    print(f"\n{'='*50}")
    print("Summarizing...")
    summarize_runs(EXPERIMENT_DIR_NAME)


if __name__ == "__main__":
    asyncio.run(main())
