#!/usr/bin/env python3
"""
Analyze KV Cache Traces — 分析跨 session 的 KV Cache 复用特征。

优先使用 .traj.json 中 API 返回的精确 usage 数据，
仅在需要细粒度拆分（如共享前缀的静态/动态 token 数）时才使用 tiktoken 估计。

用法:
    python analyze_kv_cache_traces.py /path/to/results/
    python analyze_kv_cache_traces.py /path/to/instance.traj.json
    python analyze_kv_cache_traces.py /path/to/results/ -o /path/to/analysis_output/
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import tiktoken


# ============================================================
# Token 计数工具（仅用于 JSON 无法提供的细粒度拆分）
# ============================================================

_encoding = None


def get_encoding():
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def count_tokens(text: str) -> int:
    """tiktoken 估计。仅用于 JSON 无精确值的细粒度拆分。"""
    if not text:
        return 0
    return len(get_encoding().encode(str(text)))


# ============================================================
# 轨迹解析
# ============================================================

def load_trajectory(traj_path: str | Path) -> dict | None:
    try:
        data = json.loads(Path(traj_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError):
        return None
    if isinstance(data, list):
        return {"messages": data, "info": {}}
    return data


def extract_turn_data(messages: list[dict]) -> list[dict]:
    """
    提取每个 turn 的数据，核心指标全部来自 API 精确值。
    """
    turns = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue

        extra = msg.get("extra", {})
        usage = extra.get("response", {}).get("usage", {})

        turn = {
            "api_prompt_tokens": usage.get("prompt_tokens"),
            "api_completion_tokens": usage.get("completion_tokens"),
            "api_total_tokens": usage.get("total_tokens"),
            "api_cached_tokens": usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
            "api_reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
            "timestamp": extra.get("timestamp"),
        }

        # 增量（基于 API 精确值）
        if turns and turns[-1]["api_prompt_tokens"] is not None and turn["api_prompt_tokens"] is not None:
            turn["api_increment_tokens"] = turn["api_prompt_tokens"] - turns[-1]["api_prompt_tokens"]
        else:
            turn["api_increment_tokens"] = turn["api_prompt_tokens"]

        turns.append(turn)
    return turns


def extract_prefix_structure(messages: list[dict]) -> dict:
    """
    提取前缀结构，分离静态/动态部分。
    这部分 JSON 无精确值，使用 tiktoken 估计，并用 API 精确值校准。
    """
    system_msg = None
    instance_msg = None
    for msg in messages:
        if msg.get("role") == "system" and system_msg is None:
            system_msg = msg
        elif msg.get("role") == "user" and instance_msg is None:
            instance_msg = msg

    system_content = str(system_msg.get("content", "")) if system_msg else ""
    system_tokens_est = count_tokens(system_content)

    instance_content = str(instance_msg.get("content", "")) if instance_msg else ""

    TASK_PREFIX = "<pr_description>\nConsider the following PR description:\n"
    TASK_SUFFIX = "\n</pr_description>"

    instance_static_prefix_tokens_est = 0
    instance_static_suffix_tokens_est = 0
    instance_dynamic_tokens_est = 0
    task_content = ""

    if instance_content:
        prefix_pos = instance_content.find(TASK_PREFIX)
        if prefix_pos >= 0:
            task_start = prefix_pos + len(TASK_PREFIX)
            suffix_pos = instance_content.find(TASK_SUFFIX, task_start)
            if suffix_pos >= 0:
                task_content = instance_content[task_start:suffix_pos]
                instance_static_prefix_tokens_est = count_tokens(instance_content[:task_start])
                instance_static_suffix_tokens_est = count_tokens(instance_content[suffix_pos:])
                instance_dynamic_tokens_est = count_tokens(task_content)

    shared_prefix_tokens_est = system_tokens_est + instance_static_prefix_tokens_est + instance_static_suffix_tokens_est

    return {
        "system_content_length": len(system_content),
        "system_tokens_est": system_tokens_est,
        "instance_content_length": len(instance_content),
        "instance_static_prefix_tokens_est": instance_static_prefix_tokens_est,
        "instance_static_suffix_tokens_est": instance_static_suffix_tokens_est,
        "instance_dynamic_tokens_est": instance_dynamic_tokens_est,
        "task_content_length": len(task_content),
        "shared_prefix_tokens_est": shared_prefix_tokens_est,
    }


# ============================================================
# 单 Session 分析
# ============================================================

def analyze_single_session(data: dict, traj_path: str | Path = "") -> dict:
    """分析单个 session，优先使用 API 精确数据。"""
    messages = data.get("messages", [])
    info = data.get("info", {})

    # instance_id
    instance_id = data.get("instance_id", "")
    if not instance_id:
        p = Path(traj_path)
        instance_id = p.parent.name if p.parent.name != "." else p.stem.replace(".traj", "")
    if not instance_id or instance_id == ".":
        instance_id = "unknown"

    # Turn 数据（API 精确值）
    turns = extract_turn_data(messages)

    # 前缀结构（tiktoken 估计 + API 校准）
    prefix_info = extract_prefix_structure(messages)

    # ====== 基于 API 精确值的汇总 ======
    all_prompt = [t["api_prompt_tokens"] or 0 for t in turns]
    all_completion = [t["api_completion_tokens"] or 0 for t in turns]
    all_cached = [t["api_cached_tokens"] or 0 for t in turns]

    total_prompt_tokens = sum(all_prompt)
    total_completion_tokens = sum(all_completion)

    # Session 内复用（API 精确值）
    if all_prompt:
        first_turn_prompt = all_prompt[0]
        incremental_tokens = all_prompt[0] + sum(all_prompt[i] - all_prompt[i-1] for i in range(1, len(all_prompt)))
        reused_tokens = total_prompt_tokens - incremental_tokens
        session_reuse_ratio = reused_tokens / total_prompt_tokens if total_prompt_tokens > 0 else 0
    else:
        first_turn_prompt = 0
        incremental_tokens = 0
        reused_tokens = 0
        session_reuse_ratio = 0

    # 共享前缀校准：tiktoken 只用于计算 instance 内部的比例，
    # 然后用 API 精确值校准。校准逻辑：
    #   instance_content 中，tiktoken 算得 static_suffix 占 instance 的比例为 R
    #   则 API 精确的 static_suffix ≈ R × API 精确的 instance 部分总 token 数
    #   但 API 不拆分 instance 部分的 token 数，所以用另一种方式：
    #   共享前缀占首 turn 的比例（tiktoken）× 首 turn API 精确值
    if first_turn_prompt > 0 and prefix_info["shared_prefix_tokens_est"] > 0:
        # 共享前缀占首 turn 所有可测量内容的比例
        # 首 turn 由 system + instance_content 组成（不含 tool 定义和格式开销）
        measurable_tokens_est = prefix_info["system_tokens_est"] + prefix_info["instance_static_prefix_tokens_est"] + prefix_info["instance_static_suffix_tokens_est"] + prefix_info["instance_dynamic_tokens_est"]
        if measurable_tokens_est > 0:
            # 共享前缀在可测量内容中的占比
            shared_ratio = prefix_info["shared_prefix_tokens_est"] / measurable_tokens_est
            # 这个比例乘以 API 精确的首 turn prompt_tokens
            # 注意：首 turn prompt_tokens 包含 tool 定义和格式开销，
            # 共享前缀不含 tool 定义，所以需要先扣除 tool 开销
            # tool 开销在所有 session 中也是固定的，也算跨 session 共享
            # 因此直接用 shared_ratio × first_turn_prompt 是合理的上界
            shared_prefix_api_calibrated = shared_ratio * first_turn_prompt
        else:
            shared_prefix_api_calibrated = prefix_info["shared_prefix_tokens_est"]
            shared_ratio = 0
    else:
        shared_prefix_api_calibrated = prefix_info["shared_prefix_tokens_est"]
        shared_ratio = 0

    # 校准系数 = API首turn / tiktoken可测量内容（用于信息展示）
    measurable_tokens_est = prefix_info["system_tokens_est"] + prefix_info["instance_static_prefix_tokens_est"] + prefix_info["instance_static_suffix_tokens_est"] + prefix_info["instance_dynamic_tokens_est"]
    calib_ratio = first_turn_prompt / measurable_tokens_est if measurable_tokens_est > 0 else 1.0

    # 退出状态
    exit_status = info.get("exit_status", "unknown")

    # API cached tokens 汇总
    total_cached_tokens = sum(all_cached)

    return {
        "instance_id": instance_id,
        "n_turns": len(turns),
        "n_messages": len(messages),
        "exit_status": exit_status,

        # ====== API 精确数据 ======
        "first_turn_prompt_tokens": first_turn_prompt,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_cached_tokens": total_cached_tokens,
        "incremental_prompt_tokens": incremental_tokens,
        "reused_prompt_tokens": reused_tokens,
        "session_reuse_ratio": session_reuse_ratio,
        "api_calib_ratio": calib_ratio,

        # ====== 前缀结构（tiktoken 估计 + API 校准）======
        "system_tokens_est": prefix_info["system_tokens_est"],
        "system_content_length": prefix_info["system_content_length"],
        "instance_static_prefix_tokens_est": prefix_info["instance_static_prefix_tokens_est"],
        "instance_static_suffix_tokens_est": prefix_info["instance_static_suffix_tokens_est"],
        "instance_dynamic_tokens_est": prefix_info["instance_dynamic_tokens_est"],
        "task_content_length": prefix_info["task_content_length"],
        "shared_prefix_tokens_est": prefix_info["shared_prefix_tokens_est"],
        "shared_prefix_tokens_api_calibrated": shared_prefix_api_calibrated,

        # 逐 turn 详情
        "turn_details": turns,
    }


# ============================================================
# 跨 Session 分析
# ============================================================

def analyze_cross_session(sessions: list[dict]) -> dict:
    """分析跨 session 的 KV Cache 复用特征。"""
    if not sessions:
        return {}

    n_sessions = len(sessions)

    # ---- 1. 共享前缀长度分布 ----
    shared_prefix_calibrated = [s["shared_prefix_tokens_api_calibrated"] for s in sessions]
    first_turn_prompts = [s["first_turn_prompt_tokens"] for s in sessions]

    # ---- 2. 复用频率 ----
    system_content_groups = defaultdict(list)
    for s in sessions:
        # 用 system_tokens_est 作为 grouping key
        system_content_groups[s["system_tokens_est"]].append(s["instance_id"])

    # ---- 3. 同 repo 内额外共享 ----
    repo_groups = defaultdict(list)
    for s in sessions:
        iid = s["instance_id"]
        parts = iid.split("-")[0]
        repo_groups[parts].append(s)

    # ---- 4. KV Cache 节省量（基于 API 精确值）----
    total_prefill_no_cache = sum(s["total_prompt_tokens"] for s in sessions)
    total_prefill_session_cache = sum(
        s["first_turn_prompt_tokens"] + s["incremental_prompt_tokens"] for s in sessions
    )

    # 跨 session 节省（按组计算）
    cross_session_savings_by_group = 0
    for group_key, instance_ids in system_content_groups.items():
        group_sessions = [s for s in sessions if s["instance_id"] in instance_ids]
        if len(group_sessions) > 1:
            group_prefix = group_sessions[0]["shared_prefix_tokens_api_calibrated"]
            cross_session_savings_by_group += (len(group_sessions) - 1) * group_prefix

    # ---- 5. 同 repo 分析 ----
    repo_stats = {}
    for repo_name, repo_sessions in repo_groups.items():
        repo_total_prompt = sum(s["total_prompt_tokens"] for s in repo_sessions)
        repo_avg_prefix = sum(s["shared_prefix_tokens_api_calibrated"] for s in repo_sessions) / len(repo_sessions)
        repo_cross_savings = (len(repo_sessions) - 1) * repo_avg_prefix if len(repo_sessions) > 1 else 0

        repo_stats[repo_name] = {
            "n_instances": len(repo_sessions),
            "avg_shared_prefix_api_calibrated": repo_avg_prefix,
            "total_prompt_tokens": repo_total_prompt,
            "cross_session_savings": repo_cross_savings,
            "savings_ratio": repo_cross_savings / repo_total_prompt if repo_total_prompt > 0 else 0,
        }

    # ---- 6. 每 turn 增量分析（基于 API 精确值）----
    all_first_turns = [s["first_turn_prompt_tokens"] for s in sessions if s["first_turn_prompt_tokens"] > 0]
    all_avg_increments = []
    for s in sessions:
        if s["n_turns"] > 1:
            increments = []
            for i in range(1, s["n_turns"]):
                inc = (s["turn_details"][i]["api_prompt_tokens"] or 0) - (s["turn_details"][i-1]["api_prompt_tokens"] or 0)
                increments.append(inc)
            if increments:
                all_avg_increments.append(sum(increments) / len(increments))

    # ---- 7. API cached_tokens 汇总 ----
    total_cached = sum(s["total_cached_tokens"] for s in sessions)

    # ---- 8. 校准系数统计 ----
    calib_ratios = [s["api_calib_ratio"] for s in sessions if s["api_calib_ratio"] != 1.0]

    return {
        "n_sessions": n_sessions,
        # 共享前缀分布（API 校准后）
        "prefix_distribution": {
            "shared_prefix_tokens_api_calibrated": {
                "min": min(shared_prefix_calibrated) if shared_prefix_calibrated else 0,
                "max": max(shared_prefix_calibrated) if shared_prefix_calibrated else 0,
                "mean": sum(shared_prefix_calibrated) / len(shared_prefix_calibrated) if shared_prefix_calibrated else 0,
            },
            "first_turn_prompt_tokens": {
                "min": min(first_turn_prompts) if first_turn_prompts else 0,
                "max": max(first_turn_prompts) if first_turn_prompts else 0,
                "mean": sum(first_turn_prompts) / len(first_turn_prompts) if first_turn_prompts else 0,
            },
        },
        # 复用频率
        "reuse_frequency": {
            "n_groups_by_system": len(system_content_groups),
            "group_sizes": {str(k): len(v) for k, v in sorted(system_content_groups.items(), key=lambda x: -len(x[1]))},
        },
        # KV Cache 节省量（API 精确值）
        "kv_cache_savings": {
            "total_prefill_no_cache": total_prefill_no_cache,
            "total_prefill_session_cache": total_prefill_session_cache,
            "session_cache_savings": total_prefill_no_cache - total_prefill_session_cache,
            "session_cache_savings_ratio": (total_prefill_no_cache - total_prefill_session_cache) / total_prefill_no_cache if total_prefill_no_cache > 0 else 0,
            "cross_session_savings_by_group": cross_session_savings_by_group,
            "cross_session_savings_by_group_ratio": cross_session_savings_by_group / total_prefill_no_cache if total_prefill_no_cache > 0 else 0,
        },
        # 同 repo 分析
        "repo_stats": dict(sorted(repo_stats.items(), key=lambda x: -x[1]["n_instances"])),
        # 每 turn 增量
        "turn_increment_analysis": {
            "first_turn_prompt_tokens": {
                "min": min(all_first_turns) if all_first_turns else 0,
                "max": max(all_first_turns) if all_first_turns else 0,
                "mean": sum(all_first_turns) / len(all_first_turns) if all_first_turns else 0,
            },
            "avg_incremental_per_turn": {
                "min": min(all_avg_increments) if all_avg_increments else 0,
                "max": max(all_avg_increments) if all_avg_increments else 0,
                "mean": sum(all_avg_increments) / len(all_avg_increments) if all_avg_increments else 0,
            },
        },
        # API cached_tokens
        "api_cached_tokens_total": total_cached,
        # 校准系数
        "tiktoken_to_api_calib_ratio": {
            "mean": sum(calib_ratios) / len(calib_ratios) if calib_ratios else None,
            "min": min(calib_ratios) if calib_ratios else None,
            "max": max(calib_ratios) if calib_ratios else None,
        },
    }


# ============================================================
# 输出
# ============================================================

def find_trajectory_files(path: str | Path) -> list[Path]:
    path = Path(path)
    if path.is_file() and path.suffix == ".json":
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.traj.json"))
    return []


def print_summary(cross_analysis: dict, per_session: list[dict]) -> None:
    print(f"\n{'=' * 80}")
    print(f"  KV Cache Reuse Analysis — Cross-Session Characterization")
    print(f"  (核心数据基于 API 精确值，前缀拆分使用 tiktoken + 校准)")
    print(f"{'=' * 80}")

    n = cross_analysis["n_sessions"]

    # 1. 概览
    print(f"\n{'─' * 60}")
    print(f"📊 Overview")
    print(f"{'─' * 60}")
    print(f"  Total sessions analyzed: {n}")
    exit_statuses = defaultdict(int)
    for s in per_session:
        exit_statuses[s["exit_status"]] += 1
    print(f"  Exit statuses: {dict(exit_statuses)}")

    # 2. 共享前缀分布
    print(f"\n{'─' * 60}")
    print(f"🔍 Shared Prefix Distribution")
    print(f"{'─' * 60}")
    pd = cross_analysis["prefix_distribution"]
    for name, stats in pd.items():
        print(f"  {name}:")
        print(f"    min={stats['min']:.0f}, max={stats['max']:.0f}, mean={stats['mean']:.0f}")

    # 3. 复用频率
    print(f"\n{'─' * 60}")
    print(f"🔄 Reuse Frequency (by system prompt)")
    print(f"{'─' * 60}")
    rf = cross_analysis["reuse_frequency"]
    print(f"  Number of groups: {rf['n_groups_by_system']}")
    for key, size in list(rf["group_sizes"].items())[:10]:
        print(f"    System tokens={key}: {size} sessions share this prefix")

    # 4. KV Cache 节省量（API 精确值）
    print(f"\n{'─' * 60}")
    print(f"💰 KV Cache Savings (API 精确数据)")
    print(f"{'─' * 60}")
    ks = cross_analysis["kv_cache_savings"]
    print(f"  No cache (baseline):")
    print(f"    Total prompt_tokens: {ks['total_prefill_no_cache']:,}")
    print(f"  Session-internal caching:")
    print(f"    Total prompt_tokens: {ks['total_prefill_session_cache']:,}")
    print(f"    Savings: {ks['session_cache_savings']:,} tokens ({ks['session_cache_savings_ratio']:.1%})")
    print(f"  Cross-session caching:")
    print(f"    Additional savings: {ks['cross_session_savings_by_group']:,} tokens ({ks['cross_session_savings_by_group_ratio']:.1%} of baseline)")
    total_with_cross = ks['total_prefill_session_cache'] - ks['cross_session_savings_by_group']
    total_savings = ks['total_prefill_no_cache'] - total_with_cross
    print(f"    Total with cross-session: {total_with_cross:,} tokens")
    print(f"    Total savings: {total_savings:,} tokens ({total_savings / ks['total_prefill_no_cache']:.1%})" if ks['total_prefill_no_cache'] > 0 else "")

    # 5. 同 repo
    print(f"\n{'─' * 60}")
    print(f"📂 Per-Repository Analysis")
    print(f"{'─' * 60}")
    print(f"  {'Repo':<30} │ {'#Inst':>5} │ {'Avg Shared':>10} │ {'Cross Savings':>14} │ {'Savings%':>9}")
    print(f"  {'─' * 30}─┼─{'─' * 5}─┼─{'─' * 10}─┼─{'─' * 14}─┼─{'─' * 9}")
    for repo, stats in cross_analysis["repo_stats"].items():
        print(f"  {repo:<30} │ {stats['n_instances']:>5} │ {stats['avg_shared_prefix_api_calibrated']:>10.0f} │ {stats['cross_session_savings']:>14,.0f} │ {stats['savings_ratio']:>8.1%}")

    # 6. 每 turn 增量
    print(f"\n{'─' * 60}")
    print(f"📈 Turn Increment Analysis (API 精确数据)")
    print(f"{'─' * 60}")
    ti = cross_analysis["turn_increment_analysis"]
    print(f"  First turn prompt_tokens:")
    print(f"    min={ti['first_turn_prompt_tokens']['min']:.0f}, max={ti['first_turn_prompt_tokens']['max']:.0f}, mean={ti['first_turn_prompt_tokens']['mean']:.0f}")
    print(f"  Average incremental prompt_tokens per turn:")
    print(f"    min={ti['avg_incremental_per_turn']['min']:.0f}, max={ti['avg_incremental_per_turn']['max']:.0f}, mean={ti['avg_incremental_per_turn']['mean']:.0f}")

    # 7. 校准系数
    print(f"\n{'─' * 60}")
    print(f"🔧 tiktoken→API 校准系数")
    print(f"{'─' * 60}")
    cr = cross_analysis["tiktoken_to_api_calib_ratio"]
    if cr["mean"] is not None:
        print(f"  校准系数 (API/tiktoken): mean={cr['mean']:.2f}, min={cr['min']:.2f}, max={cr['max']:.2f}")
        print(f"  用法: API 精确值 ≈ tiktoken 估计值 × {cr['mean']:.2f}")
    else:
        print(f"  无校准数据（缺少 API usage）")

    # 8. Session 内 vs 跨 Session
    print(f"\n{'─' * 60}")
    print(f"⚖️  Intra-Session vs Cross-Session Reuse (API 精确数据)")
    print(f"{'─' * 60}")
    avg_session_reuse = sum(s["session_reuse_ratio"] for s in per_session) / n if n > 0 else 0
    avg_prefix_ratio = sum(
        s["shared_prefix_tokens_api_calibrated"] / s["first_turn_prompt_tokens"]
        for s in per_session if s["first_turn_prompt_tokens"] > 0
    ) / n if n > 0 else 0
    print(f"  Average intra-session reuse ratio: {avg_session_reuse:.1%}")
    print(f"  Average shared prefix / first-turn ratio: {avg_prefix_ratio:.1%}")

    print(f"\n{'=' * 80}")
    print(f"  Analysis Complete")
    print(f"{'=' * 80}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_kv_cache_traces.py <path_to_traj_dir_or_file> [-o output_dir]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_dir = Path(sys.argv[sys.argv.index("-o") + 1]) if "-o" in sys.argv else Path(input_path) / "analysis"

    traj_files = find_trajectory_files(input_path)
    if not traj_files:
        print(f"No .traj.json files found in {input_path}")
        sys.exit(1)

    print(f"Found {len(traj_files)} trajectory files")

    per_session = []
    for i, traj_path in enumerate(traj_files):
        data = load_trajectory(traj_path)
        if data is None:
            print(f"  [{i+1}/{len(traj_files)}] SKIP (invalid): {traj_path.name}")
            continue
        session_stats = analyze_single_session(data, traj_path)
        per_session.append(session_stats)
        if (i + 1) % 10 == 0 or i == len(traj_files) - 1:
            print(f"  [{i+1}/{len(traj_files)}] Analyzed: {session_stats['instance_id']} ({session_stats['n_turns']} turns)")

    if not per_session:
        print("No valid trajectories found!")
        sys.exit(1)

    cross_analysis = analyze_cross_session(per_session)
    print_summary(cross_analysis, per_session)

    # 保存结果
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "analysis_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(cross_analysis, f, indent=2, ensure_ascii=False)
    print(f"Saved summary to {summary_path}")

    per_session_lite = []
    for s in per_session:
        s_lite = {k: v for k, v in s.items() if k != "turn_details"}
        per_session_lite.append(s_lite)

    session_path = output_dir / "per_session_stats.json"
    with open(session_path, "w", encoding="utf-8") as f:
        json.dump(per_session_lite, f, indent=2, ensure_ascii=False)
    print(f"Saved per-session stats to {session_path}")


if __name__ == "__main__":
    main()
