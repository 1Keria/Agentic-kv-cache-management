#!/usr/bin/env python3
"""Deep-dive policy flips, closed-loop order drift, and in-flight competition.

The output is descriptive. Request-level policy differences are not same-state
counterfactual eviction outcomes because each policy changes completion times
and therefore changes the later global request interleaving.
"""

from __future__ import annotations

import argparse
import bisect
from collections import Counter, defaultdict
import csv
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_agent_policy_insights import (  # noqa: E402
    DEFAULT_SUITE,
    POLICIES,
    discover_runs,
    distribution,
    load_policy_records,
    read_json,
    save_json,
    sha256_file,
    write_csv,
)


DEFAULT_ALIGNED = ROOT / "results/analysis/agent_policy_insights_20260928/request_policy_deltas.csv"
DEFAULT_OUTPUT = ROOT / "results/analysis/agent_policy_deep_dive_20260928"

PRIORITY_WINDOWS = [
    {
        "window_id": "flip_drone_long",
        "session_id": "openhands_eb93634abc30eb8a8ec57b65cb8e09b977148deee8b970538fd4caeeadef880c",
        "turn_start": 56,
        "turn_end": 64,
        "purpose": "Same session contains a 117,504-token SLRU loss and a 121,088-token SLRU gain.",
    },
    {
        "window_id": "slru_protection_run",
        "session_id": "openhands_0bb81a9cf635697f01fa3087a1d7d0bd204da9724c5b225b727ed68c84a5e1cc",
        "turn_start": 36,
        "turn_end": 43,
        "purpose": "Longest concentrated SLRU-positive session window.",
    },
    {
        "window_id": "qualification_counterexample",
        "session_id": "openhands_0ca57752127116f752c0aef0507a32422771d909683b1b911f87808524c87905",
        "turn_start": 54,
        "turn_end": 69,
        "purpose": "Alternating LRU and SLRU cliff wins on one append chain.",
    },
    {
        "window_id": "lfu_clean_failures",
        "session_id": "openhands_d18eb09e77f3e071ba866ec9cea71215732c25fde65ce6471f8c1505213602ee",
        "turn_start": 88,
        "turn_end": 112,
        "purpose": "LRU and SLRU agree while LFU repeatedly loses long prefixes.",
    },
    {
        "window_id": "common_failure_control",
        "session_id": "openhands_16b53043119b542db95dd9a89651089b9d4e0f06dc89d9e926a3c0240646d674",
        "turn_start": 54,
        "turn_end": 62,
        "purpose": "All three policies show low observed hits; negative control for ranking-only mechanisms.",
    },
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def number(row: dict[str, Any], field: str) -> float | None:
    value = row.get(field)
    if value in (None, ""):
        return None
    return float(value)


def integer(row: dict[str, Any], field: str) -> int:
    value = number(row, field)
    return 0 if value is None else int(value)


def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def availability_state(reference_tokens: int, cached_tokens: int) -> str:
    if reference_tokens < 8192:
        return "small_reference"
    fraction = min(cached_tokens, reference_tokens) / reference_tokens
    if fraction >= 0.90:
        return "high"
    if fraction <= 0.10:
        return "low"
    return "mid"


def exact_tags(row: dict[str, Any]) -> set[str]:
    return {value for value in row.get("case_tags", "").split(";") if value}


def load_token_timeline(path: Path) -> tuple[list[float], list[int]]:
    events: list[tuple[float, int]] = []
    with path.open() as stream:
        for line in stream:
            event = json.loads(line)
            if event.get("event") != "tokens":
                continue
            events.append((float(event["observed_seconds"]), len(event.get("delta_ids") or [])))
    events.sort()
    times = [time for time, _ in events]
    prefix = [0]
    for _, tokens in events:
        prefix.append(prefix[-1] + tokens)
    return times, prefix


def interval_sum(times: list[float], prefix: list[int], start: float, end: float) -> int:
    left = bisect.bisect_right(times, start)
    right = bisect.bisect_left(times, end)
    return prefix[right] - prefix[left]


def rank_maps(records: dict[tuple[str, int], dict[str, Any]]) -> tuple[dict[tuple[str, int], int], dict[tuple[str, int], int]]:
    submitted = sorted(records.items(), key=lambda item: float(item[1]["submitted_seconds"]))
    completed = sorted(records.items(), key=lambda item: float(item[1]["completed_seconds"]))
    return (
        {key: rank for rank, (key, _) in enumerate(submitted)},
        {key: rank for rank, (key, _) in enumerate(completed)},
    )


def in_flight_proxies(
    records: dict[tuple[str, int], dict[str, Any]],
    token_timeline: tuple[list[float], list[int]],
    key: tuple[str, int],
) -> dict[str, Any]:
    current = records[key]
    previous = records.get((key[0], key[1] - 1))
    if previous is None:
        return {
            "active_other_requests_at_previous_completion": None,
            "active_other_prompt_tokens_at_previous_completion": None,
            "streamed_tokens_during_think_gap": None,
            "other_streamed_tokens_during_previous_execution_and_gap": None,
            "other_completions_during_think_gap": None,
            "other_completed_prompt_tokens_during_think_gap": None,
        }
    previous_completed = float(previous["completed_seconds"])
    current_submitted = float(current["submitted_seconds"])
    previous_submitted = float(previous["submitted_seconds"])
    times, prefix = token_timeline
    active = [
        row for other_key, row in records.items()
        if other_key[0] != key[0]
        and float(row["submitted_seconds"]) < previous_completed < float(row["completed_seconds"])
    ]
    completed_gap = [
        row for other_key, row in records.items()
        if other_key[0] != key[0]
        and previous_completed < float(row["completed_seconds"]) < current_submitted
    ]
    streamed_gap = interval_sum(times, prefix, previous_completed, current_submitted)
    streamed_reactivation = interval_sum(times, prefix, previous_submitted, current_submitted)
    other_reactivation = max(0, streamed_reactivation - int(previous["actual_output_tokens"]))
    return {
        "active_other_requests_at_previous_completion": len(active),
        "active_other_prompt_tokens_at_previous_completion": sum(int(row["prompt_tokens"]) for row in active),
        "streamed_tokens_during_think_gap": streamed_gap,
        "other_streamed_tokens_during_previous_execution_and_gap": other_reactivation,
        "other_completions_during_think_gap": len(completed_gap),
        "other_completed_prompt_tokens_during_think_gap": sum(int(row["prompt_tokens"]) for row in completed_gap),
    }


def build_deep_rows(
    aligned: list[dict[str, str]],
    records: dict[str, dict[tuple[str, int], dict[str, Any]]],
    token_timelines: dict[str, tuple[list[float], list[int]]],
) -> list[dict[str, Any]]:
    ranks = {policy: rank_maps(records[policy]) for policy in POLICIES}
    aligned_by_key = {
        (row["session_id"], int(row["turn_index"])): row
        for row in aligned
    }
    output: list[dict[str, Any]] = []
    for key in sorted(aligned_by_key):
        source = aligned_by_key[key]
        reference = integer(source, "page_aligned_previous_input_lcp_tokens")
        row: dict[str, Any] = dict(source)
        for policy in POLICIES:
            current = records[policy][key]
            previous_key = (key[0], key[1] - 1)
            previous_source = aligned_by_key.get(previous_key)
            row[f"availability_state_{policy}"] = availability_state(
                reference, int(current["cached_tokens"])
            )
            row[f"previous_availability_state_{policy}"] = (
                None if previous_source is None else availability_state(
                    integer(previous_source, "page_aligned_previous_input_lcp_tokens"),
                    int(records[policy][previous_key]["cached_tokens"]),
                )
            )
            row[f"submitted_seconds_{policy}"] = current["submitted_seconds"]
            row[f"completed_seconds_{policy}"] = current["completed_seconds"]
            row[f"submission_rank_{policy}"] = ranks[policy][0][key]
            row[f"completion_rank_{policy}"] = ranks[policy][1][key]
            for field, value in in_flight_proxies(records[policy], token_timelines[policy], key).items():
                row[f"{field}_{policy}"] = value
        row["submission_rank_delta_slru_minus_lru"] = row["submission_rank_slru"] - row["submission_rank_lru"]
        row["completion_rank_delta_slru_minus_lru"] = row["completion_rank_slru"] - row["completion_rank_lru"]
        row["submitted_seconds_delta_slru_minus_lru"] = row["submitted_seconds_slru"] - row["submitted_seconds_lru"]
        output.append(row)
    return output


def high_run_stats(rows: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_session[row["session_id"]].append(row)
    transitions: Counter[tuple[str, str]] = Counter()
    runs: list[int] = []
    for members in by_session.values():
        members.sort(key=lambda row: int(row["turn_index"]))
        previous_state = None
        run = 0
        for row in members:
            state = row[f"availability_state_{policy}"]
            if previous_state is not None:
                transitions[(previous_state, state)] += 1
            if state == "high":
                run += 1
            else:
                if run:
                    runs.append(run)
                run = 0
            previous_state = state
        if run:
            runs.append(run)
    high_to_high = transitions[("high", "high")]
    high_to_low = transitions[("high", "low")]
    eligible_high = high_to_high + high_to_low + transitions[("high", "mid")]
    return {
        "transitions": {f"{a}_to_{b}": count for (a, b), count in sorted(transitions.items())},
        "high_to_high_fraction_excluding_small_reference": high_to_high / eligible_high if eligible_high else None,
        "high_runs": {
            "count": len(runs),
            "max": max(runs) if runs else 0,
            "at_least_2": sum(run >= 2 for run in runs),
            "at_least_4": sum(run >= 4 for run in runs),
        },
    }


def grouped_policy_delta(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[field])].append(row)
    output = []
    for label, members in sorted(grouped.items()):
        deltas = [integer(row, "cached_delta_slru_minus_lru") for row in members]
        output.append({
            "dimension": field,
            "bin": label,
            "requests": len(members),
            "slru_better_requests": sum(delta > 0 for delta in deltas),
            "slru_worse_requests": sum(delta < 0 for delta in deltas),
            "gross_gain_tokens": sum(max(0, delta) for delta in deltas),
            "gross_loss_tokens": sum(max(0, -delta) for delta in deltas),
            "net_cached_tokens": sum(deltas),
        })
    return output


def build_priority_windows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for window in PRIORITY_WINDOWS:
        for row in rows:
            if (
                row["session_id"] == window["session_id"]
                and window["turn_start"] <= int(row["turn_index"]) <= window["turn_end"]
            ):
                output.append({"window_id": window["window_id"], "window_purpose": window["purpose"], **row})
    output.sort(key=lambda row: (row["window_id"], int(row["turn_index"])))
    return output


def cliff_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    slru = [row for row in rows if "slru_policy_cliff_win" in exact_tags(row)]
    lru = [row for row in rows if "lru_policy_cliff_win" in exact_tags(row)]
    sessions: dict[str, set[str]] = defaultdict(set)
    for row in slru:
        sessions[row["session_id"]].add("slru")
    for row in lru:
        sessions[row["session_id"]].add("lru")
    all_cliffs = slru + lru
    return {
        "slru_policy_cliff_wins": len(slru),
        "lru_policy_cliff_wins": len(lru),
        "sessions_with_any_cliff": len(sessions),
        "sessions_with_both_directions": sum(values == {"slru", "lru"} for values in sessions.values()),
        "slru_cliff_previous_state_pairs": dict(Counter(
            f"lru_{row['previous_availability_state_lru']}__slru_{row['previous_availability_state_slru']}"
            for row in slru
        )),
        "lru_cliff_previous_state_pairs": dict(Counter(
            f"lru_{row['previous_availability_state_lru']}__slru_{row['previous_availability_state_slru']}"
            for row in lru
        )),
        "execution_context": {
            "all": cliff_context_stats(all_cliffs),
            "slru_wins": cliff_context_stats(slru),
            "lru_wins": cliff_context_stats(lru),
        },
    }


def cliff_context_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rank_drift = [abs(integer(row, "submission_rank_delta_slru_minus_lru")) for row in rows]
    time_drift = [abs(float(row["submitted_seconds_delta_slru_minus_lru"])) for row in rows]
    zero_submissions = [
        row for row in rows
        if integer(row, "intervening_submitted_request_count_lru") == 0
        and integer(row, "intervening_submitted_request_count_slru") == 0
    ]
    zero_submissions_with_inflight = [
        row for row in zero_submissions
        if integer(row, "active_other_requests_at_previous_completion_lru") > 0
        and integer(row, "active_other_requests_at_previous_completion_slru") > 0
    ]
    return {
        "requests": len(rows),
        "submission_rank_absolute_delta": distribution(rank_drift),
        "submitted_seconds_absolute_delta": distribution(time_drift),
        "submission_rank_delta_equal_zero": sum(delta == 0 for delta in rank_drift),
        "submission_rank_absolute_delta_at_most_2": sum(delta <= 2 for delta in rank_drift),
        "submission_rank_absolute_delta_at_most_5": sum(delta <= 5 for delta in rank_drift),
        "zero_intervening_submissions_both_policies": len(zero_submissions),
        "zero_submissions_with_inflight_others_both_policies": len(zero_submissions_with_inflight),
        "active_other_requests_at_previous_completion_lru": distribution(
            integer(row, "active_other_requests_at_previous_completion_lru") for row in rows
        ),
        "active_other_requests_at_previous_completion_slru": distribution(
            integer(row, "active_other_requests_at_previous_completion_slru") for row in rows
        ),
        "effective_gap_under_100ms": sum(
            number(row, "effective_gap_seconds") is not None
            and float(row["effective_gap_seconds"]) < 0.1
            for row in rows
        ),
        "previous_state_high_under_both_policies": sum(
            row["previous_availability_state_lru"] == "high"
            and row["previous_availability_state_slru"] == "high"
            for row in rows
        ),
    }


def pearson_correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    mean_x = sum(x for x, _ in pairs) / len(pairs)
    mean_y = sum(y for _, y in pairs) / len(pairs)
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    spread_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    spread_y = sum((y - mean_y) ** 2 for _, y in pairs)
    denominator = math.sqrt(spread_x * spread_y)
    return covariance / denominator if denominator else None


def cache_ttft_association(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [
        (
            float(row["cached_delta_slru_minus_lru"]),
            float(row["ttft_delta_slru_minus_lru_seconds"]),
        )
        for row in rows
        if number(row, "cached_delta_slru_minus_lru") not in (None, 0)
        and number(row, "ttft_delta_slru_minus_lru_seconds") is not None
    ]
    positive = [(cached, ttft) for cached, ttft in pairs if cached > 0]
    negative = [(cached, ttft) for cached, ttft in pairs if cached < 0]
    return {
        "nonzero_cached_delta_requests": len(pairs),
        "pearson_cached_delta_vs_ttft_delta": pearson_correlation(pairs),
        "positive_cached_delta_requests": len(positive),
        "positive_cached_delta_with_lower_ttft": sum(ttft < 0 for _, ttft in positive),
        "negative_cached_delta_requests": len(negative),
        "negative_cached_delta_with_higher_ttft": sum(ttft > 0 for _, ttft in negative),
        "interpretation": "Descriptive closed-loop association only; ordering drift prevents a causal TTFT attribution.",
    }


def common_failure_context(rows: list[dict[str, Any]]) -> dict[str, Any]:
    common = [row for row in rows if "common_failure_proxy" in exact_tags(row)]
    zero_submissions_all = [
        row for row in common
        if all(integer(row, f"intervening_submitted_request_count_{policy}") == 0 for policy in POLICIES)
    ]
    return {
        "requests": len(common),
        "effective_gap_under_100ms": sum(
            number(row, "effective_gap_seconds") is not None
            and float(row["effective_gap_seconds"]) < 0.1
            for row in common
        ),
        "zero_intervening_submissions_all_policies": len(zero_submissions_all),
        "zero_submissions_with_inflight_others_all_policies": sum(
            all(integer(row, f"active_other_requests_at_previous_completion_{policy}") > 0 for policy in POLICIES)
            for row in zero_submissions_all
        ),
        "low_availability_under_all_policies": sum(
            all(row[f"availability_state_{policy}"] == "low" for policy in POLICIES)
            for row in common
        ),
    }


def ordering_drift(rows: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    submission_rank = [integer(row, f"submission_rank_{policy}") - integer(row, "submission_rank_lru") for row in rows]
    completion_rank = [integer(row, f"completion_rank_{policy}") - integer(row, "completion_rank_lru") for row in rows]
    submitted_seconds = [float(row[f"submitted_seconds_{policy}"]) - float(row["submitted_seconds_lru"]) for row in rows]
    return {
        "submission_rank_changed_requests": sum(delta != 0 for delta in submission_rank),
        "submission_rank_absolute_delta": distribution(abs(delta) for delta in submission_rank),
        "completion_rank_changed_requests": sum(delta != 0 for delta in completion_rank),
        "completion_rank_absolute_delta": distribution(abs(delta) for delta in completion_rank),
        "submitted_seconds_delta": distribution(submitted_seconds),
        "submitted_seconds_absolute_delta": distribution(abs(delta) for delta in submitted_seconds),
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    depth_bins = grouped_policy_delta(rows, "continuation_depth_bin")
    gap_bins = grouped_policy_delta(rows, "gap_bin")
    competition_bins = grouped_policy_delta(rows, "competition_request_count_bin_lru")
    cliffs = cliff_summary(rows)
    return {
        "analysis_id": "agent_policy_deep_dive_20260928",
        "created_date": "2026-09-28",
        "scope": {
            "requests": len(rows),
            "sessions": len({row["session_id"] for row in rows}),
            "source_suite": "results/runs/20260928T015431Z_a6d1c132",
        },
        "closed_loop_ordering_drift": {
            "lfu_vs_lru": ordering_drift(rows, "lfu"),
            "slru_vs_lru": ordering_drift(rows, "slru"),
            "interpretation": "Most request ranks drift across policies; aligned request deltas are end-to-end closed-loop associations, not same-state victim counterfactuals.",
        },
        "retention_state": {policy: high_run_stats(rows, policy) for policy in POLICIES},
        "policy_cliffs": cliffs,
        "common_failure_context": common_failure_context(rows),
        "cache_ttft_association": cache_ttft_association(rows),
        "non_monotonicity": {
            "continuation_depth_bins": depth_bins,
            "effective_gap_bins": gap_bins,
            "lru_intervening_submission_count_bins": competition_bins,
        },
        "hypothesis_assessment": [
            {
                "hypothesis": "Agent 流量主要由追加式长链续接构成。",
                "assessment": "supported",
                "evidence": "1,186 个非首轮转换中有 1,127 个是严格 append。",
            },
            {
                "hypothesis": "续接深度越大，SLRU 就越应该保护该请求。",
                "assessment": "not_supported_as_a_single_variable",
                "evidence": "深度 4–7 的 SLRU 净差为负，8+ 为正；相近深度同时存在正反案例。",
            },
            {
                "hypothesis": "等待越久或期间新提交请求越多，越能单调预测哪种策略更好。",
                "assessment": "not_supported_as_a_single_variable",
                "evidence": "等待和新提交竞争分桶中的 SLRU 净差正负交替，长等待桶样本也很少。",
            },
            {
                "hypothesis": "SLRU 会稳定延长热链的驻留。",
                "assessment": "weak_and_localized",
                "evidence": "SLRU 的最长高可用运行更长，但 high-to-high 保持率与 LRU 几乎相同，且存在 26 个反向 cliff。",
            },
            {
                "hypothesis": "无条件继承父链信用是安全的。",
                "assessment": "not_identified_by_current_proxy",
                "evidence": "当前只运行了 LRU/LFU/SLRU，且闭环顺序不同；8 个会话同时出现正反 cliff，只能说明父链热度不足以作为充分保护依据，不能直接检验信用继承。",
            },
            {
                "hypothesis": "只改变候选排序就能消除大多数已观测前缀缺口。",
                "assessment": "not_identified_by_current_proxy",
                "evidence": "356 个请求在三策略下都有至少 8K 相邻前缀缺口代理，但该代理没有候选 frontier、锁、SWA/Full 归因；只有 108 个请求的策略敏感差异达到至少 8K。",
            },
        ],
        "conclusion": "日志支持测试有界、衰减的续接信用，但不支持只按续接深度授予保护。机制需要保守上限、按竞争量失效，并在相同释放预算下做反事实验证。",
    }


def format_number(value: Any) -> str:
    if value is None:
        return "未知"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.3f}".rstrip("0").rstrip(".")
    return f"{int(value):,}"


def build_markdown(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    drift = summary["closed_loop_ordering_drift"]["slru_vs_lru"]
    cliffs = summary["policy_cliffs"]
    cliff_context = cliffs["execution_context"]["all"]
    common_context = summary["common_failure_context"]
    ttft = summary["cache_ttft_association"]
    retention = summary["retention_state"]
    assessment_labels = {
        "supported": "支持",
        "not_supported_as_a_single_variable": "不能作为单一变量支持",
        "weak_and_localized": "弱支持且仅局部成立",
        "not_identified_by_current_proxy": "当前代理无法判定",
    }
    lines = [
        "# Agent 定制淘汰策略：日志深挖与假设检验",
        "",
        "日期：2026-09-28。该报告继续分析同一批 LRU/LFU/SLRU 日志，重点检验有界父链信用是否有依据。",
        "",
        "## 1. 最重要的新发现",
        "",
        f"SLRU 与 LRU 的全局提交顺序在 {format_number(drift['submission_rank_changed_requests'])}/1,206 个请求上不同，提交排名绝对差中位数为 {format_number(drift['submission_rank_absolute_delta']['p50'])}、p95 为 {format_number(drift['submission_rank_absolute_delta']['p95'])}，提交时间最大绝对偏移为 {format_number(drift['submitted_seconds_absolute_delta']['max'])} 秒。",
        "",
        "因此当前逐请求命中差异包含两部分：淘汰策略本身的影响，以及策略改变完成时间后造成的全局交错变化。现有日志不能把两部分严格分离，不能把某条请求的 SLRU-LRU 差值直接解释成同一合法候选集上的 victim 优劣。",
        "",
        "## 2. 观察现象与父链信用假设",
        "",
        f"- 支持：{format_number(cliffs['slru_policy_cliff_wins'])} 个请求表现为 SLRU 保留接近完整的相邻长前缀、LRU 基本丢失。SLRU 的最长连续高可用运行是 {format_number(retention['slru']['high_runs']['max'])} 轮，LRU 为 {format_number(retention['lru']['high_runs']['max'])} 轮。",
        f"- 反向现象：另有 {format_number(cliffs['lru_policy_cliff_wins'])} 个完全相反的请求；{format_number(cliffs['sessions_with_both_directions'])} 个会话同时出现两个方向的 cliff。这不是信用继承机制的直接实验。",
        "- SLRU 与 LRU 的高前缀连续保持概率非常接近，说明收益来自少量长运行和大额翻转，并非所有热链都更稳定。",
        "- 续接深度不是单调信号：深度4–7总体对SLRU为负，8+转正；单独设一个续接次数阈值容易过拟合特定会话。",
        "",
        "父链历史仅可作为待检验信号；当前日志没有验证其预测力，也没有测试继承比例或衰减规则。有界信用与快速失效是候选设计约束，不是已证明的收益来源。",
        "",
        "## 3. 为什么短间隔仍会发生整条长前缀翻转",
        "",
        f"55 个双向 cliff 中，有 {format_number(cliff_context['zero_intervening_submissions_both_policies'])} 个在 LRU 和 SLRU 的前后轮之间都没有新请求提交，但这 {format_number(cliff_context['zero_submissions_with_inflight_others_both_policies'])} 个案例在上一轮完成时都仍有其他请求运行；两种策略的在途请求中位数均为 {format_number(cliff_context['active_other_requests_at_previous_completion_lru']['p50'])}。另有 {format_number(cliff_context['effective_gap_under_100ms'])}/55 的有效 think gap 小于 100ms。",
        "",
        "这意味着后续竞争量至少要同时记录：上一轮完成时的在途请求、期间实际生成token、完成请求引入的缓存、池可驱逐量，以及精确回收事件。",
        "",
        f"此外，{format_number(cliff_context['previous_state_high_under_both_policies'])}/55 个 cliff 在前一轮的 LRU 与 SLRU 下都处于高可用状态，下一轮却向相反方向翻转。这说明父链曾经完整驻留仍不足以决定新尾部是否应继续受保护。",
        "",
        "### 3.1 相近请求排名也不是同状态反事实",
        "",
        f"55 个 cliff 中有 {format_number(cliff_context['submission_rank_absolute_delta_at_most_2'])} 个提交排名差不超过 2，{format_number(cliff_context['submission_rank_delta_equal_zero'])} 个排名完全相同；但全部 cliff 的提交时间绝对偏移中位数仍为 {format_number(cliff_context['submitted_seconds_absolute_delta']['p50'])} 秒。即使排名接近，期间的完成顺序、KV 分配和候选集合仍可能不同，因此不能把这些案例当作严格同状态对照。",
        "",
        "### 3.2 三策略共同缺口的来源尚不能区分",
        "",
        f"共有 {format_number(common_context['requests'])} 个请求在三种策略下都存在至少 8K 的相邻前缀缺口代理。其中 {format_number(common_context['zero_intervening_submissions_all_policies'])} 个在三种策略的 think gap 内都没有新请求提交，但这些案例在三种策略下都仍有其他请求在途；{format_number(common_context['low_availability_under_all_policies'])} 个请求在三种策略下都只有低前缀可用性。缺少逐次 KV 事件，不能据此判断其他排序能否改善，应同时检查共同排序缺陷、活跃占用、Full/SWA、实际存储、节点暴露和回收粒度。",
        "",
        "### 3.3 命中翻转与 TTFT 有明显关联，但不能作因果解释",
        "",
        f"在 {format_number(ttft['positive_cached_delta_requests'])} 个 SLRU 多命中请求中，{format_number(ttft['positive_cached_delta_with_lower_ttft'])} 个同时具有更低 TTFT；在 {format_number(ttft['negative_cached_delta_requests'])} 个 SLRU 少命中请求中，{format_number(ttft['negative_cached_delta_with_higher_ttft'])} 个同时具有更高 TTFT。缓存差值与 TTFT 差值的 Pearson 相关系数为 {format_number(ttft['pearson_cached_delta_vs_ttft_delta'])}。这说明大额命中翻转具有性能意义，但闭环交错漂移使当前日志仍不能给出严格因果量。",
        "",
        "## 4. 典型窗口解释",
        "",
        "### drone-planning-control：turn 60 与 turn 63",
        "",
        "turn 60中LRU保留117,504 token而SLRU为0；三轮后的turn 63中LRU为0、SLRU保留121,088 token。同一个会话和相近续接深度产生相反结论。turn 63前有约63秒等待，但不同策略期间完成的其他请求数量也不同，不能仅用等待时间解释。",
        "",
        "### drone-planning-control：turn 38–41",
        "",
        "SLRU在这些请求上连续命中约67K–70K前缀，而LRU多次只命中0/3072。turn 38前think gap只有约42毫秒，却有8–9个其他客户端请求尚未完成。客户端时序无法确定 KV 的写入或淘汰时刻；短间隔和少量stream token也不排除一次大粒度回收。",
        "",
        "### syzkaller-ppdev-syzlang：turn 54–69",
        "",
        "同一严格append链中，turn 56由LRU保留、turn 59由SLRU保留、turn 65–67又由LRU连续保留。这是优先补采候选事件的对照窗口；因为没有测试资格迁移且全局交错不同，不能据此判定该机制有效或无效。",
        "",
        "## 5. 对第一版机制的约束",
        "",
        "建议机制仍是有界续接信用，但应满足：",
        "",
        "1. 新尾部只继承很小的初始信用，不复制父节点完整hit_count。",
        "2. 信用最多跨越有限次数的淘汰决策；没有真实命中就迅速归零。",
        "3. 衰减使用实际竞争工作量，包括在途生成和新分配页，而非只使用wall-clock等待。",
        "4. 历史改写、分叉或公共模板前缀不能无条件传递私有链信用。",
        "5. 评估必须在完整合法frontier上满足相同释放token/byte预算，并计算被替代victim的后续损失。",
        "",
        "一个可检验的初始形式是：`tail_credit = min(C_max, alpha * parent_credit)`，其中 `alpha` 取较小值；每经历一轮实际竞争工作量或一次淘汰决策，信用乘以衰减系数 `gamma < 1`。新尾部发生真实命中后再转为自身信用；发生历史改写、分叉或长期无命中时清零。这里的公式是实验候选，不是当前日志已经证明的最优形式。",
        "",
        "## 6. 当前可以确认的结论",
        "",
    ]
    for item in summary["hypothesis_assessment"]:
        label = assessment_labels.get(item["assessment"], item["assessment"])
        lines.append(f"- **{label}**：{item['hypothesis']} {item['evidence']}")
    lines.extend([
        "",
        "当前日志未确认有界父链信用的收益。单次淘汰反事实需要相同缓存状态、合法候选与释放预算；完整策略重放则需要相同初始状态、外生请求计划和容量，之后各策略缓存状态允许自然分化。两种评估不能混为一谈。",
        "",
    ])
    return "\n".join(lines)


def build_manifest(
    output: Path,
    suite: Path,
    aligned_path: Path,
    runs: dict[str, Path],
) -> dict[str, Any]:
    inputs = {"aligned_requests": aligned_path, "suite": suite / "suite.json"}
    for policy, folder in runs.items():
        inputs[f"{policy}_requests"] = folder / "measurement/requests.jsonl"
        inputs[f"{policy}_events"] = folder / "measurement/events.jsonl"
    outputs = [path for path in output.iterdir() if path.is_file() and path.name != "manifest.json"]
    return {
        "analysis_id": output.name,
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": sha256_file(Path(__file__)),
        "inputs": {
            name: {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)}
            for name, path in sorted(inputs.items())
        },
        "outputs": {path.name: sha256_file(path) for path in sorted(outputs)},
    }


def run(suite: Path, aligned_path: Path, output: Path) -> dict[str, Any]:
    suite = suite.resolve()
    aligned_path = aligned_path.resolve()
    output = output.resolve()
    if not suite.is_relative_to(ROOT) or not aligned_path.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        raise ValueError("All paths must remain inside experiments/evicition_policy")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing analysis: {output}")
    output.mkdir(parents=True)
    runs = discover_runs(suite)
    records = load_policy_records(runs)
    aligned = read_csv(aligned_path)
    token_timelines = {
        policy: load_token_timeline(folder / "measurement/events.jsonl")
        for policy, folder in runs.items()
    }
    rows = build_deep_rows(aligned, records, token_timelines)
    summary = build_summary(rows)
    cliffs = [
        row for row in rows
        if exact_tags(row) & {"slru_policy_cliff_win", "lru_policy_cliff_win", "lfu_under_lru_and_slru", "common_failure_proxy"}
    ]
    windows = build_priority_windows(rows)
    hypothesis_bins = []
    for field in ("continuation_depth_bin", "gap_bin", "competition_request_count_bin_lru", "growth_bin", "lcp_bin"):
        hypothesis_bins.extend(grouped_policy_delta(rows, field))
    write_csv(output / "cliff_cases_deep.csv", cliffs)
    write_csv(output / "priority_windows.csv", windows)
    write_csv(output / "hypothesis_bins.csv", hypothesis_bins)
    save_json(output / "summary.json", summary)
    (output / "deep_dive.md").write_text(build_markdown(summary, rows))
    save_json(output / "manifest.json", build_manifest(output, suite, aligned_path, runs))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--aligned", type=Path, default=DEFAULT_ALIGNED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    os.umask(0o077)
    summary = run(args.suite, args.aligned, args.output)
    print(json.dumps({
        "analysis_id": summary["analysis_id"],
        "requests": summary["scope"]["requests"],
        "slru_cliff_wins": summary["policy_cliffs"]["slru_policy_cliff_wins"],
        "lru_cliff_wins": summary["policy_cliffs"]["lru_policy_cliff_wins"],
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
