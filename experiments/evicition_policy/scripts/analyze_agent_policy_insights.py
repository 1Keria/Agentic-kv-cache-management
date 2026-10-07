#!/usr/bin/env python3
"""Mine request-level evidence for future Agent-specific eviction policies.

This analysis deliberately separates observed cache hits from a content-level
previous-input-LCP shortfall proxy.  The proxy is not h_infinity, eviction
regret, or avoidable recomputation because the current suite lacks complete KV
events, legal-candidate snapshots, and an event-faithful historical index.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "results/runs/20260928T015431Z_a6d1c132"
DEFAULT_PROFILE = ROOT / "results/audit/encoded_profile_20260926/summary.json"
DEFAULT_OUTPUT = ROOT / "results/analysis/agent_policy_insights_20260928"
POLICIES = ("lru", "lfu", "slru")
PAGE_SIZE = 256


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def distribution(values: Iterable[float]) -> dict[str, Any]:
    materialized = list(values)
    if not materialized:
        return {"count": 0}
    return {
        "count": len(materialized),
        "sum": sum(materialized),
        "min": min(materialized),
        "p50": percentile(materialized, 0.50),
        "p95": percentile(materialized, 0.95),
        "p99": percentile(materialized, 0.99),
        "max": max(materialized),
    }


def gap_bin(value: float | None) -> str:
    if value is None:
        return "first_request"
    bounds = [
        (0.1, "[0,0.1)"),
        (1.0, "[0.1,1)"),
        (5.0, "[1,5)"),
        (20.0, "[5,20)"),
        (60.0, "[20,60)"),
        (300.0, "[60,300)"),
    ]
    for upper, label in bounds:
        if value < upper:
            return label
    return "[300,+inf)"


def growth_bin(value: int | None) -> str:
    if value is None:
        return "first_request"
    bounds = [
        (256, "[0,256)"),
        (1024, "[256,1024)"),
        (4096, "[1024,4096)"),
        (16384, "[4096,16384)"),
        (65536, "[16384,65536)"),
    ]
    for upper, label in bounds:
        if value < upper:
            return label
    return "[65536,+inf)"


def turn_bin(value: int) -> str:
    bounds = [
        (1, "turn_0"),
        (5, "turn_1_4"),
        (10, "turn_5_9"),
        (20, "turn_10_19"),
        (50, "turn_20_49"),
        (100, "turn_50_99"),
    ]
    for upper, label in bounds:
        if value < upper:
            return label
    return "turn_100_plus"


def lcp_bin(value: int | None) -> str:
    if value is None:
        return "first_request"
    bounds = [
        (8192, "[0,8K)"),
        (32768, "[8K,32K)"),
        (65536, "[32K,64K)"),
        (98304, "[64K,96K)"),
        (131072, "[96K,128K)"),
    ]
    for upper, label in bounds:
        if value < upper:
            return label
    return "[128K,+inf)"


def continuation_depth_bin(value: int) -> str:
    if value == 0:
        return "0"
    if value == 1:
        return "1"
    if value <= 3:
        return "2_3"
    if value <= 7:
        return "4_7"
    return "8_plus"


def competition_count_bin(value: int | None) -> str:
    if value is None:
        return "first_request"
    if value == 0:
        return "0"
    bounds = [(5, "[1,5)"), (20, "[5,20)"), (100, "[20,100)")]
    for upper, label in bounds:
        if value < upper:
            return label
    return "[100,+inf)"


def competition_prompt_bin(value: int | None) -> str:
    if value is None:
        return "first_request"
    if value == 0:
        return "0"
    bounds = [
        (256_000, "(0,256K)"),
        (1_000_000, "[256K,1M)"),
        (4_000_000, "[1M,4M)"),
        (16_000_000, "[4M,16M)"),
    ]
    for upper, label in bounds:
        if value < upper:
            return label
    return "[16M,+inf)"


def previous_input_lcp_shortfall_proxy(lcp_tokens: int | None, cached_tokens: int) -> int:
    """Content-only diagnostic; never interpret as exact eviction recomputation."""
    if lcp_tokens is None:
        return 0
    page_aligned_lcp = (lcp_tokens // PAGE_SIZE) * PAGE_SIZE
    return max(0, page_aligned_lcp - cached_tokens)


def discover_runs(suite: Path) -> dict[str, Path]:
    runs: dict[str, Path] = {}
    for state_path in sorted(suite.glob("*/state.json")):
        state = read_json(state_path)
        policy = state.get("policy")
        if policy in POLICIES:
            if state.get("status") != "completed":
                raise ValueError(f"Run is not completed: {state_path.parent}")
            runs[policy] = state_path.parent
    missing = sorted(set(POLICIES) - set(runs))
    if missing:
        raise ValueError(f"Missing completed policies: {missing}")
    return runs


def load_policy_records(runs: dict[str, Path]) -> dict[str, dict[tuple[str, int], dict[str, Any]]]:
    output: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}
    for policy, folder in runs.items():
        records = read_jsonl(folder / "measurement/requests.jsonl")
        keyed: dict[tuple[str, int], dict[str, Any]] = {}
        for row in records:
            key = (row["session_id"], int(row["turn_index"]))
            if key in keyed:
                raise ValueError(f"Duplicate request key for {policy}: {key}")
            if row.get("status") != "completed":
                raise ValueError(f"Incomplete request for {policy}: {key}")
            keyed[key] = row
        output[policy] = keyed
    key_sets = {policy: set(records) for policy, records in output.items()}
    first = key_sets[POLICIES[0]]
    for policy in POLICIES[1:]:
        if key_sets[policy] != first:
            raise ValueError(f"Request keys differ between policies: {policy}")
    return output


def intervening_submission_proxies(
    policy_records: dict[tuple[str, int], dict[str, Any]]
) -> dict[tuple[str, int], tuple[int | None, int | None]]:
    """Count submitted demand between one session turn completing and the next submitting.

    These values are client-side competition proxies. They do not represent
    distinct KV insertions, resident bytes, or runtime cache accesses.
    """
    ordered = sorted(policy_records.items(), key=lambda item: float(item[1]["submitted_seconds"]))
    submitted = [float(row["submitted_seconds"]) for _, row in ordered]
    prefix_prompt_tokens = [0]
    for _, row in ordered:
        prefix_prompt_tokens.append(prefix_prompt_tokens[-1] + int(row["prompt_tokens"]))

    output: dict[tuple[str, int], tuple[int | None, int | None]] = {}
    for key, row in policy_records.items():
        session_id, turn_index = key
        if turn_index == 0:
            output[key] = (None, None)
            continue
        previous = policy_records.get((session_id, turn_index - 1))
        if previous is None:
            output[key] = (None, None)
            continue
        start = float(previous["completed_seconds"])
        end = float(row["submitted_seconds"])
        left = bisect.bisect_right(submitted, start)
        right = bisect.bisect_left(submitted, end)
        output[key] = (
            max(0, right - left),
            max(0, prefix_prompt_tokens[right] - prefix_prompt_tokens[left]),
        )
    return output


def build_request_rows(
    records: dict[str, dict[tuple[str, int], dict[str, Any]]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    competition = {
        policy: intervening_submission_proxies(records[policy])
        for policy in POLICIES
    }
    continuation_depths: dict[tuple[str, int], int] = {}
    for key in sorted(records["lru"]):
        policy_rows = {policy: records[policy][key] for policy in POLICIES}
        baseline = policy_rows["lru"]
        for policy, row in policy_rows.items():
            if row["input_ids_sha256"] != baseline["input_ids_sha256"]:
                raise ValueError(f"Input hash drift for {policy}: {key}")
            if row["prompt_tokens"] != baseline["prompt_tokens"]:
                raise ValueError(f"Prompt length drift for {policy}: {key}")

        lcp = baseline.get("previous_input_lcp_tokens")
        growth = None if lcp is None else int(baseline["prompt_tokens"]) - int(lcp)
        previous = records["lru"].get((baseline["session_id"], int(baseline["turn_index"]) - 1))
        if previous is None or lcp is None:
            transition_shape = "first"
            previous_prompt_tokens = None
            continuation_depth = 0
        else:
            previous_prompt_tokens = int(previous["prompt_tokens"])
            ratio = int(lcp) / previous_prompt_tokens if previous_prompt_tokens else 0.0
            if int(lcp) == previous_prompt_tokens:
                transition_shape = "append"
            elif ratio >= 0.90:
                transition_shape = "tail_rewrite"
            elif ratio >= 0.50:
                transition_shape = "partial_rewrite"
            else:
                transition_shape = "major_reset"
            previous_depth = continuation_depths.get((baseline["session_id"], int(baseline["turn_index"]) - 1), 0)
            continuation_depth = previous_depth + 1 if transition_shape == "append" else 0
        continuation_depths[key] = continuation_depth
        output: dict[str, Any] = {
            "session_id": baseline["session_id"],
            "task_id": baseline["task_id"],
            "turn_index": int(baseline["turn_index"]),
            "input_ids_sha256": baseline["input_ids_sha256"],
            "prompt_tokens": int(baseline["prompt_tokens"]),
            "previous_input_lcp_tokens": lcp,
            "page_aligned_previous_input_lcp_tokens": None if lcp is None else (int(lcp) // PAGE_SIZE) * PAGE_SIZE,
            "previous_prompt_tokens": previous_prompt_tokens,
            "context_delta_after_previous_input_lcp_tokens": growth,
            "transition_shape": transition_shape,
            "strict_append_continuation_depth": continuation_depth,
            "continuation_depth_bin": continuation_depth_bin(continuation_depth),
            "source_gap_seconds": baseline.get("source_gap_seconds"),
            "effective_gap_seconds": baseline.get("effective_gap_seconds"),
            "actual_gap_seconds_lru": baseline.get("actual_gap_seconds"),
            "gap_bin": gap_bin(baseline.get("effective_gap_seconds")),
            "growth_bin": growth_bin(growth),
            "turn_bin": turn_bin(int(baseline["turn_index"])),
            "lcp_bin": lcp_bin(lcp),
        }
        for policy, row in policy_rows.items():
            if row.get("cached_tokens") is None:
                raise ValueError(f"Missing cached_tokens for {policy}: {key}")
            cached = int(row["cached_tokens"])
            output[f"cached_tokens_{policy}"] = cached
            output[f"uncached_input_tokens_{policy}"] = int(row["prompt_tokens"]) - cached
            output[f"previous_input_lcp_shortfall_proxy_tokens_{policy}"] = previous_input_lcp_shortfall_proxy(lcp, cached)
            reference = output["page_aligned_previous_input_lcp_tokens"]
            output[f"previous_input_lcp_availability_fraction_{policy}"] = (
                None if not reference else min(cached, reference) / reference
            )
            output[f"ttft_seconds_{policy}"] = row.get("ttft_seconds")
            output[f"latency_seconds_{policy}"] = row.get("latency_seconds")
            output[f"local_continuation_lcp_tokens_{policy}"] = row.get("previous_local_continuation_lcp_tokens")
            output[f"local_output_fully_matches_next_input_{policy}"] = row.get("previous_local_output_fully_matches_next_input")
            intervening_count, intervening_prompt = competition[policy][key]
            output[f"intervening_submitted_request_count_{policy}"] = intervening_count
            output[f"intervening_submitted_prompt_tokens_{policy}"] = intervening_prompt
        output["competition_request_count_bin_lru"] = competition_count_bin(
            output["intervening_submitted_request_count_lru"]
        )
        output["competition_prompt_tokens_bin_lru"] = competition_prompt_bin(
            output["intervening_submitted_prompt_tokens_lru"]
        )
        output["cached_delta_slru_minus_lru"] = output["cached_tokens_slru"] - output["cached_tokens_lru"]
        output["cached_delta_lfu_minus_lru"] = output["cached_tokens_lfu"] - output["cached_tokens_lru"]
        output["policy_sensitivity_cached_tokens"] = max(output[f"cached_tokens_{policy}"] for policy in POLICIES) - min(
            output[f"cached_tokens_{policy}"] for policy in POLICIES
        )
        output["best_of_three_observed_gap_lru"] = max(output[f"cached_tokens_{policy}"] for policy in POLICIES) - output["cached_tokens_lru"]
        output["best_of_three_observed_gap_lfu"] = max(output[f"cached_tokens_{policy}"] for policy in POLICIES) - output["cached_tokens_lfu"]
        output["best_of_three_observed_gap_slru"] = max(output[f"cached_tokens_{policy}"] for policy in POLICIES) - output["cached_tokens_slru"]
        output["ttft_delta_slru_minus_lru_seconds"] = output["ttft_seconds_slru"] - output["ttft_seconds_lru"]
        output["ttft_delta_lfu_minus_lru_seconds"] = output["ttft_seconds_lfu"] - output["ttft_seconds_lru"]
        reference = output["page_aligned_previous_input_lcp_tokens"] or 0
        tags: list[str] = []
        if output["cached_delta_slru_minus_lru"] >= 8192:
            tags.append("slru_large_win")
        if output["cached_delta_slru_minus_lru"] <= -8192:
            tags.append("lru_large_win")
        if reference >= 8192:
            lru_availability = output["previous_input_lcp_availability_fraction_lru"] or 0.0
            slru_availability = output["previous_input_lcp_availability_fraction_slru"] or 0.0
            if lru_availability <= 0.10 and slru_availability >= 0.90:
                tags.append("slru_policy_cliff_win")
            if slru_availability <= 0.10 and lru_availability >= 0.90:
                tags.append("lru_policy_cliff_win")
        if all(output[f"previous_input_lcp_shortfall_proxy_tokens_{policy}"] >= 8192 for policy in POLICIES):
            tags.append("common_failure_proxy")
        if output["cached_tokens_lfu"] + 8192 <= min(output["cached_tokens_lru"], output["cached_tokens_slru"]):
            tags.append("lfu_under_lru_and_slru")
        if (
            transition_shape == "append"
            and continuation_depth >= 4
            and reference >= 32768
            and output["previous_input_lcp_shortfall_proxy_tokens_lru"] >= 8192
        ):
            tags.append("long_chain_unavailable_lru_proxy")
        output["case_tags"] = ";".join(tags)
        rows.append(output)
    return rows


def aggregate_group(dimension: str, label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "dimension": dimension,
        "bin": label,
        "request_count": len(rows),
        "prompt_tokens_total": sum(row["prompt_tokens"] for row in rows),
        "cached_delta_slru_minus_lru": sum(row["cached_delta_slru_minus_lru"] for row in rows),
        "cached_delta_lfu_minus_lru": sum(row["cached_delta_lfu_minus_lru"] for row in rows),
        "slru_better_requests": sum(row["cached_delta_slru_minus_lru"] > 0 for row in rows),
        "slru_worse_requests": sum(row["cached_delta_slru_minus_lru"] < 0 for row in rows),
        "lfu_better_requests": sum(row["cached_delta_lfu_minus_lru"] > 0 for row in rows),
        "lfu_worse_requests": sum(row["cached_delta_lfu_minus_lru"] < 0 for row in rows),
    }
    for policy in POLICIES:
        output[f"cached_tokens_{policy}"] = sum(row[f"cached_tokens_{policy}"] for row in rows)
        output[f"previous_input_lcp_shortfall_proxy_tokens_{policy}"] = sum(
            row[f"previous_input_lcp_shortfall_proxy_tokens_{policy}"] for row in rows
        )
    return output


def build_behavior_bins(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dimensions = {
        "effective_gap_seconds": "gap_bin",
        "context_delta_after_previous_input_lcp_tokens": "growth_bin",
        "turn_index": "turn_bin",
        "previous_input_lcp_tokens": "lcp_bin",
        "transition_shape": "transition_shape",
        "strict_append_continuation_depth": "continuation_depth_bin",
        "intervening_submitted_request_count_lru": "competition_request_count_bin_lru",
        "intervening_submitted_prompt_tokens_lru": "competition_prompt_tokens_bin_lru",
    }
    output: list[dict[str, Any]] = []
    for dimension, field in dimensions.items():
        labels = sorted({str(row[field]) for row in rows})
        for label in labels:
            members = [row for row in rows if str(row[field]) == label]
            output.append(aggregate_group(dimension, label, members))
    return output


def build_session_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["session_id"], row["task_id"]), []).append(row)
    output: list[dict[str, Any]] = []
    for (session_id, task_id), members in grouped.items():
        result: dict[str, Any] = {
            "session_id": session_id,
            "task_id": task_id,
            "requests": len(members),
            "max_turn_index": max(row["turn_index"] for row in members),
            "prompt_tokens_total": sum(row["prompt_tokens"] for row in members),
            "context_delta_after_previous_input_lcp_tokens_total": sum(
                row["context_delta_after_previous_input_lcp_tokens"] or 0 for row in members
            ),
            "effective_gap_seconds_total": sum(row["effective_gap_seconds"] or 0 for row in members),
            "cached_delta_slru_minus_lru": sum(row["cached_delta_slru_minus_lru"] for row in members),
            "cached_delta_lfu_minus_lru": sum(row["cached_delta_lfu_minus_lru"] for row in members),
            "slru_gross_gain_tokens": sum(max(0, row["cached_delta_slru_minus_lru"]) for row in members),
            "slru_gross_loss_tokens": sum(max(0, -row["cached_delta_slru_minus_lru"]) for row in members),
            "lfu_gross_gain_tokens": sum(max(0, row["cached_delta_lfu_minus_lru"]) for row in members),
            "lfu_gross_loss_tokens": sum(max(0, -row["cached_delta_lfu_minus_lru"]) for row in members),
            "slru_better_requests": sum(row["cached_delta_slru_minus_lru"] > 0 for row in members),
            "slru_worse_requests": sum(row["cached_delta_slru_minus_lru"] < 0 for row in members),
            "lfu_better_requests": sum(row["cached_delta_lfu_minus_lru"] > 0 for row in members),
            "lfu_worse_requests": sum(row["cached_delta_lfu_minus_lru"] < 0 for row in members),
        }
        for policy in POLICIES:
            result[f"cached_tokens_{policy}"] = sum(row[f"cached_tokens_{policy}"] for row in members)
            result[f"previous_input_lcp_shortfall_proxy_tokens_{policy}"] = sum(
                row[f"previous_input_lcp_shortfall_proxy_tokens_{policy}"] for row in members
            )
            result[f"intervening_submitted_request_count_{policy}"] = sum(
                row[f"intervening_submitted_request_count_{policy}"] or 0 for row in members
            )
            result[f"intervening_submitted_prompt_tokens_{policy}"] = sum(
                row[f"intervening_submitted_prompt_tokens_{policy}"] or 0 for row in members
            )
        output.append(result)
    output.sort(
        key=lambda row: (
            abs(row["cached_delta_slru_minus_lru"]),
            abs(row["cached_delta_lfu_minus_lru"]),
        ),
        reverse=True,
    )
    return output


def case_type(row: dict[str, Any]) -> str:
    slru = row["cached_delta_slru_minus_lru"]
    lfu = row["cached_delta_lfu_minus_lru"]
    if slru > 0:
        return "slru_gain"
    if slru < 0:
        return "slru_loss"
    if lfu > 0:
        return "lfu_gain_only"
    if lfu < 0:
        return "lfu_loss_only"
    return "no_policy_delta"


def has_case_tag(row: dict[str, Any], tag: str) -> bool:
    return tag in {value for value in row.get("case_tags", "").split(";") if value}


def build_candidate_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        {**row, "case_type": case_type(row)}
        for row in rows
        if row["cached_delta_slru_minus_lru"] != 0 or row["cached_delta_lfu_minus_lru"] != 0 or row.get("case_tags")
    ]
    candidates.sort(
        key=lambda row: (
            max(abs(row["cached_delta_slru_minus_lru"]), abs(row["cached_delta_lfu_minus_lru"])),
            len(row.get("case_tags", "").split(";")) if row.get("case_tags") else 0,
            row["previous_input_lcp_shortfall_proxy_tokens_lru"],
            row["prompt_tokens"],
        ),
        reverse=True,
    )
    for rank, row in enumerate(candidates, 1):
        row["priority_rank"] = rank
        row["requires_kv_event_trace_for_causal_attribution"] = True
    return candidates


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def policy_summary(
    policy: str,
    rows: list[dict[str, Any]],
    run_folder: Path,
) -> dict[str, Any]:
    analysis = read_json(run_folder / "descriptive_analysis.json")
    pools = {
        entry["pool"]: entry["resident_fraction_sample_distribution"]
        for entry in analysis.get("pool_residency_by_series", [])
        if entry.get("labels", {}).get("tp_rank") == "0"
    }
    counters = {
        entry["name"]: entry["raw_delta"]
        for entry in analysis.get("raw_counter_deltas", [])
    }
    continuation = [
        row for row in rows
        if row.get(f"local_output_fully_matches_next_input_{policy}") is not None
    ]
    return {
        "requests": len(rows),
        "prompt_tokens": sum(row["prompt_tokens"] for row in rows),
        "cached_tokens": sum(row[f"cached_tokens_{policy}"] for row in rows),
        "token_weighted_hit_fraction": sum(row[f"cached_tokens_{policy}"] for row in rows) / sum(row["prompt_tokens"] for row in rows),
        "previous_input_lcp_shortfall_proxy_tokens": sum(row[f"previous_input_lcp_shortfall_proxy_tokens_{policy}"] for row in rows),
        "requests_with_positive_previous_input_lcp_shortfall_proxy": sum(row[f"previous_input_lcp_shortfall_proxy_tokens_{policy}"] > 0 for row in rows),
        "ttft_seconds": distribution(row[f"ttft_seconds_{policy}"] for row in rows),
        "latency_seconds": distribution(row[f"latency_seconds_{policy}"] for row in rows),
        "local_continuation_checks": len(continuation),
        "local_output_fully_matches_next_input": sum(bool(row[f"local_output_fully_matches_next_input_{policy}"]) for row in continuation),
        "intervening_submitted_request_count": distribution(
            row[f"intervening_submitted_request_count_{policy}"]
            for row in rows
            if row[f"intervening_submitted_request_count_{policy}"] is not None
        ),
        "intervening_submitted_prompt_tokens": distribution(
            row[f"intervening_submitted_prompt_tokens_{policy}"]
            for row in rows
            if row[f"intervening_submitted_prompt_tokens_{policy}"] is not None
        ),
        "pool_residency_sample_distributions_rank0": pools,
        "raw_native_counter_deltas": counters,
    }


def build_summary(
    suite: Path,
    profile_path: Path,
    runs: dict[str, Path],
    rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    profile = read_json(profile_path)
    policy_summaries = {policy: policy_summary(policy, rows, runs[policy]) for policy in POLICIES}
    slru_deltas = [row["cached_delta_slru_minus_lru"] for row in rows]
    lfu_deltas = [row["cached_delta_lfu_minus_lru"] for row in rows]
    non_first = [row for row in rows if row["page_aligned_previous_input_lcp_tokens"] is not None]
    reference_tokens = sum(row["page_aligned_previous_input_lcp_tokens"] for row in non_first)
    transition_counts = {
        shape: sum(row["transition_shape"] == shape for row in rows)
        for shape in ("first", "append", "tail_rewrite", "partial_rewrite", "major_reset")
    }
    slru_gross_gain = sum(max(0, delta) for delta in slru_deltas)
    slru_gross_loss = sum(max(0, -delta) for delta in slru_deltas)
    return {
        "analysis_id": "agent_policy_insights_20260928",
        "created_date": "2026-09-28",
        "purpose": "Evidence package for designing a future Agent-specific KV eviction policy",
        "source_suite": str(suite.relative_to(ROOT)),
        "source_profile": str(profile_path.relative_to(ROOT)),
        "page_size_tokens": PAGE_SIZE,
        "scope": {
            "requests": len(rows),
            "sessions": len({row["session_id"] for row in rows}),
            "task_ids": len({row["task_id"] for row in rows}),
            "policies": list(POLICIES),
            "single_frozen_capacity_point": True,
            "real_tool_execution": False,
            "complete_kv_event_coverage": False,
            "legal_candidate_snapshots": False,
        },
        "definitions": {
            "previous_input_lcp_shortfall_proxy_tokens": (
                "max(0, floor(previous_input_lcp_tokens / 256) * 256 - cached_tokens). "
                "This is a content-level diagnostic proxy, not h_infinity, exact eviction loss, "
                "avoidable recomputation, or an optimal-policy regret measure."
            ),
            "cached_delta_slru_minus_lru": "cached_tokens_slru - cached_tokens_lru for the same frozen request",
            "cached_delta_lfu_minus_lru": "cached_tokens_lfu - cached_tokens_lru for the same frozen request",
            "best_of_three_observed_gap": "Difference from the maximum cached_tokens observed among the three policy runs; not oracle regret.",
            "intervening_submitted_prompt_tokens": (
                "Client-side sum of prompt tokens submitted by other requests after the previous turn completed "
                "and before the current turn submitted. This is a demand/competition proxy, not newly inserted KV tokens."
            ),
        },
        "candidate_profile": {
            "all_sessions": profile["summaries"]["all"]["sessions"],
            "all_requests": profile["summaries"]["all"]["requests"],
            "prompt_tokens": profile["summaries"]["all"]["prompt_tokens"],
            "recorded_gap_seconds": profile["summaries"]["all"]["recorded_gap_seconds"],
            "tokens_after_previous_input_lcp": profile["summaries"]["all"]["tokens_after_previous_input_lcp"],
            "unique_complete_context_prefix_pages": profile["unique_complete_context_prefix_pages"],
            "prefix_pages_shared_across_sessions": profile["prefix_pages_shared_across_sessions"],
        },
        "policy_summaries": policy_summaries,
        "chain_structure": {
            "transition_shape_counts": transition_counts,
            "strict_append_fraction_of_non_first": transition_counts["append"] / len(non_first),
            "page_aligned_previous_input_reference_tokens": reference_tokens,
            "previous_input_lcp_shortfall_proxy_fraction": {
                policy: policy_summaries[policy]["previous_input_lcp_shortfall_proxy_tokens"] / reference_tokens
                for policy in POLICIES
            },
            "common_failure_proxy_requests_8192": sum(has_case_tag(row, "common_failure_proxy") for row in rows),
            "policy_sensitive_requests_8192": sum(row["policy_sensitivity_cached_tokens"] >= 8192 for row in rows),
            "long_chain_unavailable_lru_proxy_requests": sum(has_case_tag(row, "long_chain_unavailable_lru_proxy") for row in rows),
            "long_chain_unavailable_lru_proxy_tokens": sum(
                row["previous_input_lcp_shortfall_proxy_tokens_lru"]
                for row in rows
                if has_case_tag(row, "long_chain_unavailable_lru_proxy")
            ),
            "slru_policy_cliff_wins": sum(has_case_tag(row, "slru_policy_cliff_win") for row in rows),
            "lru_policy_cliff_wins": sum(has_case_tag(row, "lru_policy_cliff_win") for row in rows),
            "lfu_under_lru_and_slru_requests": sum(has_case_tag(row, "lfu_under_lru_and_slru") for row in rows),
        },
        "aligned_policy_differences": {
            "slru_minus_lru": {
                "cached_tokens_delta": sum(slru_deltas),
                "gross_gain_tokens": slru_gross_gain,
                "gross_loss_tokens": slru_gross_loss,
                "net_as_fraction_of_gross_gain": sum(slru_deltas) / slru_gross_gain,
                "better_requests": sum(delta > 0 for delta in slru_deltas),
                "worse_requests": sum(delta < 0 for delta in slru_deltas),
                "equal_requests": sum(delta == 0 for delta in slru_deltas),
                "delta_distribution": distribution(slru_deltas),
            },
            "lfu_minus_lru": {
                "cached_tokens_delta": sum(lfu_deltas),
                "gross_gain_tokens": sum(max(0, delta) for delta in lfu_deltas),
                "gross_loss_tokens": sum(max(0, -delta) for delta in lfu_deltas),
                "better_requests": sum(delta > 0 for delta in lfu_deltas),
                "worse_requests": sum(delta < 0 for delta in lfu_deltas),
                "equal_requests": sum(delta == 0 for delta in lfu_deltas),
                "delta_distribution": distribution(lfu_deltas),
            },
        },
        "candidate_case_count": len(candidates),
        "top_candidate_cases": [
            {
                key: row[key]
                for key in (
                    "priority_rank", "case_type", "session_id", "task_id", "turn_index",
                    "prompt_tokens", "previous_input_lcp_tokens", "effective_gap_seconds",
                    "context_delta_after_previous_input_lcp_tokens",
                    "cached_delta_slru_minus_lru", "cached_delta_lfu_minus_lru",
                    "previous_input_lcp_shortfall_proxy_tokens_lru",
                    "transition_shape", "strict_append_continuation_depth", "case_tags",
                )
            }
            for row in candidates[:20]
        ],
        "interpretation_limits": [
            "The suite contains one run per policy in fixed LRU-LFU-SLRU order; run-to-run variability is unknown.",
            "The next request waits for local completion but uses frozen historical input and does not execute tools.",
            "Local generated output almost never fully reproduces the historical next input, so generated-tail reuse is not faithfully observed.",
            "Native eviction counters may mix Full/SWA components and TP aggregation; they are engineering signals, not logical victim counts.",
            "No current artifact records the complete legal frontier, victim identity, split/merge/lock state, or counterfactual replacement cost.",
        ],
    }


def format_int(value: int | float | None) -> str:
    if value is None:
        return "未知"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{int(value):,}"


def build_markdown(summary: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    profile = summary["candidate_profile"]
    policies = summary["policy_summaries"]
    slru = summary["aligned_policy_differences"]["slru_minus_lru"]
    lfu = summary["aligned_policy_differences"]["lfu_minus_lru"]
    chain = summary["chain_structure"]
    shared = profile["prefix_pages_shared_across_sessions"]
    total_pages = profile["unique_complete_context_prefix_pages"]
    lines = [
        "# Agent 定制淘汰策略：中间过程证据与设计 Insight",
        "",
        "日期：2026-09-28。该报告由成功 suite 的逐请求日志和全量候选画像自动生成，服务于下一阶段机制设计。",
        "",
        "## 1. 结论边界",
        "",
        "当前证据能够说明请求内容结构、相邻轮延续、实际命中差异和聚合缓存压力；不能精确说明某次淘汰是否存在更优合法 victim。文中的 `previous_input_lcp_shortfall_proxy_tokens` 只是内容级参照缺口，不是严格的额外重算量。",
        "",
        "## 2. 核心观测",
        "",
        f"- 全量候选包含 {format_int(profile['all_sessions'])} 个会话、{format_int(profile['all_requests'])} 个请求。输入长度中位数为 {format_int(profile['prompt_tokens']['p50'])} token，相邻输入 LCP 后新增内容中位数为 {format_int(profile['tokens_after_previous_input_lcp']['p50'])} token。",
        f"- 共识别 {format_int(total_pages)} 个完整 256-token 上下文前缀页，仅 {format_int(shared)} 个跨 session 引用。除公共模板前缀外，主要复用机会来自同一 session 的私有长链。",
        f"- SLRU 相对 LRU 净多命中 {format_int(slru['cached_tokens_delta'])} token，但只在 {format_int(slru['better_requests'])} 个请求上更好、{format_int(slru['worse_requests'])} 个请求上更差，另有 {format_int(slru['equal_requests'])} 个请求完全相同。策略差异集中在少数竞争时刻。",
        f"- SLRU 正向差异合计 {format_int(slru['gross_gain_tokens'])} token、负向差异合计 {format_int(slru['gross_loss_tokens'])} token，净收益只保留了正向差异的 {slru['net_as_fraction_of_gross_gain'] * 100:.2f}%。现象是强烈抵消，而不是普遍改善。",
        f"- LFU 相对 LRU 净变化为 {format_int(lfu['cached_tokens_delta'])} token；更好/更差请求数分别为 {format_int(lfu['better_requests'])}/{format_int(lfu['worse_requests'])}。",
        f"- 非首轮转换中严格 append 为 {format_int(chain['transition_shape_counts']['append'])} 次，占 {chain['strict_append_fraction_of_non_first'] * 100:.2f}%；主要结构确实是同 session 长链续接。",
        f"- 三策略都存在至少 8K 相邻前缀缺口代理的请求有 {format_int(chain['common_failure_proxy_requests_8192'])} 个，而三策略最大命中差至少 8K 的请求只有 {format_int(chain['policy_sensitive_requests_8192'])} 个。仅改变排序可能无法覆盖大部分缺口。",
        f"- 长链目标组（严格 append、续接深度≥4、参照前缀≥32K、LRU 缺口代理≥8K）有 {format_int(chain['long_chain_unavailable_lru_proxy_requests'])} 个请求，缺口代理合计 {format_int(chain['long_chain_unavailable_lru_proxy_tokens'])} token。",
        f"- 三种策略的本地生成完整接入下一轮历史输入次数分别为 LRU {format_int(policies['lru']['local_output_fully_matches_next_input'])}/{format_int(policies['lru']['local_continuation_checks'])}、LFU {format_int(policies['lfu']['local_output_fully_matches_next_input'])}/{format_int(policies['lfu']['local_continuation_checks'])}、SLRU {format_int(policies['slru']['local_output_fully_matches_next_input'])}/{format_int(policies['slru']['local_continuation_checks'])}。因此当前数据不能直接验证新生成尾部的真实闭环复用价值。",
        "",
        "## 3. 对定制策略的启发",
        "",
        "1. **优先研究链级续接证据，而不是跨 session 语义共享。** 现有共享画像显示跨 session 完整前缀页极少；最小机制应先针对同一实际 token 链的多轮续接。",
        "2. **把新增尾部与已有长历史分开。** 长历史已经证明可复用，不代表刚产生的尾部也有相同价值。可检验的最小机制是有限的续接资格迁移：只把父链的一部分历史信用授予新尾部，并设置上限或衰减。",
        "3. **用竞争量补充绝对时间。** 工具等待秒数有长尾，但相同等待期间可能没有竞争，也可能插入大量新页。未来排序信号应记录自上次需求以来的新插入逻辑页/token、不同前缀访问数和池压力，而不是仅按 wall time。",
        "4. **收益需要按释放成本归一化。** 大节点保留价值高时也可能占用更多页。候选比较至少同时记录未来可复用 token、当前节点 token、路径 token 和达到相同释放预算时替代 victim 的损失。",
        "5. **先解释差异请求，再扩大策略矩阵。** `candidate_cases.csv` 已按策略命中差异排序；应先为这些请求补完整 KV 事件和合法 frontier，验证 SLRU 的收益是否来自预期的续接链保护。",
        "",
        "## 4. 优先验证的最小机制",
        "",
        "建议第一版只实现一个可关闭的 `bounded continuation credit`：当同一可确认 token 前缀链已发生多次续接时，新暴露尾部获得有限信用；信用不跨历史改写无条件继承，并随竞争量或时间衰减。它必须与原生 SLRU 对照，并满足相同释放 token 预算。",
        "",
        "在实现前需要通过事件诊断回答：",
        "",
        "- 发生大额命中差异时，完整合法候选有哪些，锁定和父节点暴露如何变化；",
        "- 被保留尾部之后是否真实再次需要，以及为保留它而替换的其他候选损失是多少；",
        "- 信用来自同一链的历史续接，还是公共祖先/模板命中；",
        "- 收益是否集中于某些等待竞争量、上下文增长或轮次区间。",
        "",
        "## 5. 首批典型案例",
        "",
        "| 排名 | 类型/标签 | task | turn | prompt | LCP | 有效等待(s) | SLRU-LRU命中差 | LFU-LRU命中差 |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in candidates[:15]:
        lines.append(
            f"| {row['priority_rank']} | {row['case_type']} / {row['case_tags'] or '-'} | {row['task_id']} | {row['turn_index']} | "
            f"{format_int(row['prompt_tokens'])} | {format_int(row['previous_input_lcp_tokens'])} | "
            f"{format_int(row['effective_gap_seconds'])} | {format_int(row['cached_delta_slru_minus_lru'])} | "
            f"{format_int(row['cached_delta_lfu_minus_lru'])} |"
        )
    lines.extend([
        "",
        "这些案例只是后续采集 KV 时间线的优先队列。没有完整 candidate/victim/lock/split 事件前，不将其标记为错误淘汰。",
        "",
        "## 6. 配套文件",
        "",
        "- `summary.json`：口径、总体统计、策略差异和解释限制。",
        "- `request_policy_deltas.csv`：1,206 个请求的对齐明细。",
        "- `behavior_bins.csv`：按等待、增长、轮次和 LCP 长度分桶的命中差异与代理缺口。",
        "- `session_summary.csv`：按会话汇总的策略差异与提交竞争代理。",
        "- `candidate_cases.csv`：所有发生策略命中差异的请求，按最大绝对差异排序。",
        "- `manifest.json`：输入和输出文件哈希。",
        "",
    ])
    return "\n".join(lines)


def build_manifest(
    suite: Path,
    profile_path: Path,
    runs: dict[str, Path],
    output: Path,
) -> dict[str, Any]:
    inputs = {"profile": profile_path}
    for policy, folder in runs.items():
        inputs[f"{policy}_requests"] = folder / "measurement/requests.jsonl"
        inputs[f"{policy}_analysis"] = folder / "descriptive_analysis.json"
        inputs[f"{policy}_state"] = folder / "state.json"
    inputs["suite"] = suite / "suite.json"
    outputs = [path for path in output.iterdir() if path.is_file() and path.name != "manifest.json"]
    return {
        "analysis_id": output.name,
        "script": str(Path(__file__).relative_to(ROOT)),
        "script_sha256": sha256_file(Path(__file__)),
        "inputs": {
            name: {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)}
            for name, path in sorted(inputs.items())
        },
        "outputs": {
            path.name: sha256_file(path)
            for path in sorted(outputs)
        },
    }


def run(suite: Path, profile_path: Path, output: Path) -> dict[str, Any]:
    suite = suite.resolve()
    profile_path = profile_path.resolve()
    output = output.resolve()
    if not suite.is_relative_to(ROOT) or not profile_path.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        raise ValueError("All paths must remain inside experiments/evicition_policy")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing analysis: {output}")
    output.mkdir(parents=True)

    runs = discover_runs(suite)
    records = load_policy_records(runs)
    request_rows = build_request_rows(records)
    behavior_bins = build_behavior_bins(request_rows)
    session_summaries = build_session_summaries(request_rows)
    candidates = build_candidate_cases(request_rows)
    summary = build_summary(suite, profile_path, runs, request_rows, candidates)

    write_csv(output / "request_policy_deltas.csv", request_rows)
    write_csv(output / "behavior_bins.csv", behavior_bins)
    write_csv(output / "session_summary.csv", session_summaries)
    write_csv(output / "candidate_cases.csv", candidates)
    save_json(output / "summary.json", summary)
    (output / "design_insights.md").write_text(build_markdown(summary, candidates))
    save_json(output / "manifest.json", build_manifest(suite, profile_path, runs, output))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    os.umask(0o077)
    summary = run(args.suite, args.profile, args.output)
    print(json.dumps({
        "analysis_id": summary["analysis_id"],
        "requests": summary["scope"]["requests"],
        "candidate_cases": summary["candidate_case_count"],
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
