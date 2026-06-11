#!/usr/bin/env python3
"""
Trace Single Session — 分析单个 agent session 内的消息流和 KV Cache 复用特征。

优先使用 .traj.json 中 API 返回的精确 usage 数据（prompt_tokens, completion_tokens），
仅在需要细粒度拆分（如共享前缀的静态/动态 token 数）时才使用 tiktoken 估计。

用法:
    python trace_single_session.py /path/to/instance.traj.json
"""

import json
import sys
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
    """tiktoken 估计 token 数。仅用于 JSON 无精确值的细粒度拆分。"""
    if not text:
        return 0
    return len(get_encoding().encode(str(text)))


# ============================================================
# 轨迹解析
# ============================================================

def load_trajectory(traj_path: str) -> dict:
    """加载 .traj.json 文件。"""
    data = json.loads(Path(traj_path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"messages": data, "info": {}}
    return data


def extract_turn_data(messages: list[dict]) -> list[dict]:
    """
    从 messages 列表提取每个 turn 的数据。

    每个 turn 对应一次 LLM API 调用。核心数据全部来自 JSON 中的
    assistant 消息的 extra.response.usage 字段，无需 tiktoken 估计。
    """
    turns = []

    for msg in messages:
        if msg.get("role") != "assistant":
            continue

        extra = msg.get("extra", {})
        response = extra.get("response", {})
        usage = response.get("usage", {})

        # ====== 核心数据：全部来自 JSON ======
        turn = {
            # API 精确 token 数
            "api_prompt_tokens": usage.get("prompt_tokens"),
            "api_completion_tokens": usage.get("completion_tokens"),
            "api_total_tokens": usage.get("total_tokens"),
            "api_cached_tokens": usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
            "api_reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
            # 时间戳
            "timestamp": extra.get("timestamp"),
            # 动作
            "actions": extra.get("actions", []),
        }

        # 增量计算（基于 API 精确值）
        if turns:
            prev_prompt = turns[-1]["api_prompt_tokens"] or 0
            curr_prompt = turn["api_prompt_tokens"] or 0
            turn["api_increment_tokens"] = curr_prompt - prev_prompt
        else:
            turn["api_increment_tokens"] = turn["api_prompt_tokens"]

        turns.append(turn)

    return turns


def extract_prefix_structure(messages: list[dict], config: dict) -> dict:
    """
    提取前缀结构，分离静态/动态部分。

    对于 turn 级别的 token 数，优先使用 API 精确值。
    对于消息内部的结构性拆分（静态前缀/后缀 vs 动态 task），
    JSON 无此信息，需用 tiktoken 估计。
    """
    system_msg = None
    instance_msg = None
    for msg in messages:
        if msg.get("role") == "system" and system_msg is None:
            system_msg = msg
        elif msg.get("role") == "user" and instance_msg is None:
            instance_msg = msg

    # System message（tiktoken 估计，JSON 无此拆分）
    system_content = str(system_msg.get("content", "")) if system_msg else ""
    system_tokens_est = count_tokens(system_content)

    # Instance message 的静态/动态分离
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

    # 共享前缀（tiktoken 估计）
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
        # 用 API 精确值反推共享前缀占比
        # shared_prefix / first_turn_prompt_tokens 即为跨 session 首次 prefill 的可复用比例
    }


# ============================================================
# 分析与输出
# ============================================================

def analyze_session(traj_path: str) -> None:
    """分析单个 session 的 trace。"""
    print(f"{'=' * 80}")
    print(f"  Trace Single Session Analysis")
    print(f"{'=' * 80}")
    print(f"\n📂 Loading trajectory: {traj_path}")

    data = load_trajectory(traj_path)
    messages = data.get("messages", [])
    info = data.get("info", {})
    config = info.get("config", {})

    # 基本信息
    print(f"\n{'─' * 60}")
    print(f"📊 Session Overview")
    print(f"{'─' * 60}")

    model_stats = info.get("model_stats", {})
    agent_config = config.get("agent", {})
    print(f"  Exit Status:  {info.get('exit_status', 'N/A')}")
    print(f"  API Calls:    {model_stats.get('api_calls', 'N/A')}")
    print(f"  Total Cost:   ${model_stats.get('instance_cost', 0):.4f}")
    print(f"  Total Messages: {len(messages)}")

    # 提取 turn 数据（核心：全部基于 API 精确值）
    turns = extract_turn_data(messages)
    print(f"  Total Turns:  {len(turns)}")

    # ====== Turn-by-Turn 分析（基于 API 精确值）======
    print(f"\n{'─' * 60}")
    print(f"📋 Turn-by-Turn Analysis (API 精确数据)")
    print(f"{'─' * 60}")

    print(f"\n{'Turn':>4} │ {'Prompt':>8} │ {'Completion':>10} │ {'Increment':>9} │ {'Reuse%':>7} │ {'Cached':>7} │ {'Reasoning':>9} │ {'Time':>8}")
    print(f"{'─' * 4}─┼─{'─' * 8}─┼─{'─' * 10}─┼─{'─' * 9}─┼─{'─' * 7}─┼─{'─' * 7}─┼─{'─' * 9}─┼─{'─' * 8}")

    for t in turns:
        prompt = t["api_prompt_tokens"] or 0
        completion = t["api_completion_tokens"] or 0
        inc = t["api_increment_tokens"] or 0
        cached = t["api_cached_tokens"] or 0
        reasoning = t["api_reasoning_tokens"] or 0
        ts = t["timestamp"] or 0

        # 复用率 = 上一 turn 的 prompt_tokens / 当前 prompt_tokens
        if t is not turns[0] and prompt > 0:
            reuse_pct = (turns[turns.index(t) - 1]["api_prompt_tokens"] or 0) / prompt
        else:
            reuse_pct = 0.0

        print(f"{turns.index(t):>4} │ {prompt:>8} │ {completion:>10} │ {inc:>9} │ {reuse_pct:>6.1%} │ {cached:>7} │ {reasoning:>9} │ {ts:>8.1f}")

    # ====== 前缀结构分析（tiktoken 估计，JSON 无此拆分）======
    prefix_info = extract_prefix_structure(messages, config)

    print(f"\n{'─' * 60}")
    print(f"🔍 Prefix Structure (tiktoken 估计，JSON 无此拆分)")
    print(f"{'─' * 60}")
    print(f"  System Message:")
    print(f"    Content Length:  {prefix_info['system_content_length']} chars")
    print(f"    Token Count:     {prefix_info['system_tokens_est']} (tiktoken)")
    print(f"  Instance Message:")
    print(f"    Content Length:  {prefix_info['instance_content_length']} chars")
    print(f"    Static Prefix:   {prefix_info['instance_static_prefix_tokens_est']} tokens (tiktoken)")
    print(f"    Static Suffix:   {prefix_info['instance_static_suffix_tokens_est']} tokens (tiktoken)")
    print(f"    Dynamic (task):  {prefix_info['instance_dynamic_tokens_est']} tokens (tiktoken)")
    print(f"    Task Length:      {prefix_info['task_content_length']} chars")
    print(f"  共享前缀 (tiktoken): {prefix_info['shared_prefix_tokens_est']} tokens")

    # 用 API 精确值校准共享前缀
    if turns and turns[0]["api_prompt_tokens"]:
        first_turn_api = turns[0]["api_prompt_tokens"]
        # 共享前缀在可测量内容中的占比（tiktoken 比例）
        measurable_est = prefix_info['system_tokens_est'] + prefix_info['instance_static_prefix_tokens_est'] + prefix_info['instance_static_suffix_tokens_est'] + prefix_info['instance_dynamic_tokens_est']
        if measurable_est > 0:
            shared_ratio = prefix_info['shared_prefix_tokens_est'] / measurable_est
        else:
            shared_ratio = 0
        # 比例 × API 精确首 turn 值 = 校准后的共享前缀
        shared_prefix_api_calibrated = shared_ratio * first_turn_api

        print(f"\n  共享前缀占比 (首 turn):")
        print(f"    首 turn API prompt_tokens:      {first_turn_api}")
        print(f"    共享前缀 / 可测量内容 (tiktoken): {shared_ratio:.1%}")
        print(f"    共享前缀 (校准后):               {shared_prefix_api_calibrated:.0f} tokens")
        print(f"    注：校准方法 = tiktoken比例 × API精确首turn值")
        print(f"    包含 tool 定义等 API 格式开销在内")

    # ====== Session 内 KV Cache 复用（基于 API 精确值）======
    print(f"\n{'─' * 60}")
    print(f"📈 Session-Internal KV Cache Reuse (API 精确数据)")
    print(f"{'─' * 60}")

    if turns:
        all_prompt = [t["api_prompt_tokens"] or 0 for t in turns]
        all_completion = [t["api_completion_tokens"] or 0 for t in turns]

        total_prompt = sum(all_prompt)
        total_completion = sum(all_completion)
        total_increment = all_prompt[0] + sum(all_prompt[i] - all_prompt[i-1] for i in range(1, len(all_prompt)))
        total_reused = total_prompt - total_increment

        print(f"  总 prompt_tokens (所有 turns):  {total_prompt:,}")
        print(f"  总 completion_tokens:            {total_completion:,}")
        print(f"  增量 prompt_tokens:              {total_increment:,}")
        print(f"  复用 prompt_tokens:              {total_reused:,}")
        print(f"  Session 内复用率:                {total_reused / total_prompt:.1%}")

        # KV Cache 增长曲线
        print(f"\n  KV Cache Growth (API 精确数据):")
        print(f"  {'Turn':>4} │ {'Prompt Tokens':>14} │ {'Increment':>10} │ {'Cumulative Completion':>22}")
        print(f"  {'─' * 4}─┼─{'─' * 14}─┼─{'─' * 10}─┼─{'─' * 22}")
        cum_completion = 0
        for i, t in enumerate(turns):
            cum_completion += t["api_completion_tokens"] or 0
            print(f"  {i:>4} │ {(t['api_prompt_tokens'] or 0):>14,} │ {(t['api_increment_tokens'] or 0):>10,} │ {cum_completion:>22,}")

    # ====== 跨 Session 复用潜力 ======
    print(f"\n{'─' * 60}")
    print(f"💰 Cross-Session Reuse Potential")
    print(f"{'─' * 60}")

    shared_prefix = prefix_info['shared_prefix_tokens_est']
    if turns and turns[0]["api_prompt_tokens"]:
        measurable_est = prefix_info['system_tokens_est'] + prefix_info['instance_static_prefix_tokens_est'] + prefix_info['instance_static_suffix_tokens_est'] + prefix_info['instance_dynamic_tokens_est']
        if measurable_est > 0:
            shared_ratio = prefix_info['shared_prefix_tokens_est'] / measurable_est
        else:
            shared_ratio = 0
        shared_prefix_calibrated = shared_ratio * turns[0]["api_prompt_tokens"]
    else:
        shared_prefix_calibrated = shared_prefix

    print(f"  共享前缀 (校准后): {shared_prefix_calibrated:.0f} tokens")
    print(f"  If N sessions share this prefix:")
    for n in [2, 5, 10, 50, 100, 300]:
        saved = shared_prefix_calibrated * (n - 1)
        print(f"    N={n:>3}: saved {saved:,.0f} tokens in first-turn prefill ({(n-1)/n:.0%} reduction)")

    print(f"\n{'=' * 80}")
    print(f"  Analysis Complete")
    print(f"{'=' * 80}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python trace_single_session.py <path_to_traj.json>")
        sys.exit(1)

    traj_path = sys.argv[1]
    if not Path(traj_path).exists():
        print(f"Error: File not found: {traj_path}")
        sys.exit(1)

    analyze_session(traj_path)


if __name__ == "__main__":
    main()
