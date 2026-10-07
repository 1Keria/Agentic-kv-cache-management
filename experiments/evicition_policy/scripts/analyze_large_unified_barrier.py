#!/usr/bin/env python3
"""Analyze the 20-session unified Exposure Barrier comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

from analyze_calibration import summarize_run
from analyze_results import audit_run
from prepare_data import ROOT, save_json


def load_records(run: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (run / "measurement/requests.jsonl").read_text().splitlines()
        if line
    ]


def percentile(values: list[float], q: float):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def rank_drift(base: list[dict], other: list[dict]) -> dict:
    def ranks(rows):
        ordered = sorted(rows, key=lambda row: float(row["submitted_seconds"]))
        return {
            (row["session_id"], row["turn_index"]): index
            for index, row in enumerate(ordered)
        }

    left, right = ranks(base), ranks(other)
    values = [abs(left[key] - right[key]) for key in left]
    return {
        "requests": len(values),
        "changed": sum(value > 0 for value in values),
        "median_absolute_rank_delta": statistics.median(values),
        "p95_absolute_rank_delta": percentile(values, 0.95),
        "maximum_absolute_rank_delta": max(values),
    }


def queue_summary(descriptive: dict) -> dict:
    valid = [
        row
        for row in descriptive["scheduler_queue_histogram_by_rank"]
        if row["measurement_coverage_validated"]
    ]
    means = [row["mean_seconds"] for row in valid]
    p95 = [
        row["quantile_bucket_bounds"].get("0.95", {}).get("upper_seconds")
        for row in valid
    ]
    p95 = [value for value in p95 if value is not None]
    return {
        "validated_ranks": len(valid),
        "mean_seconds_max_rank": max(means) if means else None,
        "p95_bucket_upper_seconds_max_rank": max(p95) if p95 else None,
    }


def analyze(suite: Path) -> dict:
    manifest = json.loads((suite / "suite.json").read_text())
    if manifest["status"] != "completed":
        raise ValueError("Large-scale suite is not complete")
    runs = {}
    records = {}
    for case in manifest["runs"]:
        run = suite / case["path"]
        strategy = case["strategy"]
        audit = audit_run(run)
        descriptive = summarize_run(run)
        rows = load_records(run)
        records[strategy] = rows
        runs[strategy] = {
            "path": str(run),
            "policy": case["policy"],
            "exposure_barrier": case["exposure_barrier"],
            "requests": audit["requests"],
            "prompt_tokens": audit["prompt_tokens_total"],
            "output_tokens": audit["output_tokens_total"],
            "cached_prompt_tokens": sum(row["cached_tokens"] for row in rows),
            "token_weighted_cache_hit_fraction": audit[
                "token_weighted_cache_hit_fraction"
            ],
            "ttft_seconds": audit["ttft_seconds"],
            "latency_seconds": audit["latency_seconds"],
            "measurement_seconds": descriptive.get("measurement", {}).get(
                "elapsed_seconds"
            ),
            "queue": queue_summary(descriptive),
            "retractions": descriptive["native_num_retractions"].get("sum"),
            "monitor_errors": descriptive["monitor_error_samples"],
            "integrity_passed": audit["protocol_integrity_passed"],
            "post_flush_empty": audit["post_flush_native_metrics_empty"],
            "gpu_released": descriptive.get("owned_gpu_allocations_released"),
        }

    baseline = runs["lru"]
    baseline_records = records["lru"]
    keyed_inputs = {
        strategy: {
            (row["session_id"], row["turn_index"]): (
                row["input_ids_sha256"],
                row["prompt_tokens"],
            )
            for row in rows
        }
        for strategy, rows in records.items()
    }
    inputs_aligned = all(
        keyed_inputs[strategy] == keyed_inputs["lru"] for strategy in keyed_inputs
    )
    comparisons = {}
    for strategy in ("slru", "unified_exposure_barrier"):
        current = runs[strategy]
        comparisons[strategy] = {
            "cached_prompt_token_delta_vs_lru": current["cached_prompt_tokens"]
            - baseline["cached_prompt_tokens"],
            "cache_hit_percentage_point_delta_vs_lru": 100
            * (
                current["token_weighted_cache_hit_fraction"]
                - baseline["token_weighted_cache_hit_fraction"]
            ),
            "ttft_p95_percent_vs_lru": 100
            * (current["ttft_seconds"]["p95"] - baseline["ttft_seconds"]["p95"])
            / baseline["ttft_seconds"]["p95"],
            "latency_p95_percent_vs_lru": 100
            * (
                current["latency_seconds"]["p95"]
                - baseline["latency_seconds"]["p95"]
            )
            / baseline["latency_seconds"]["p95"],
            "measurement_time_percent_vs_lru": 100
            * (current["measurement_seconds"] - baseline["measurement_seconds"])
            / baseline["measurement_seconds"],
            "submission_rank_drift_vs_lru": rank_drift(
                baseline_records, records[strategy]
            ),
        }
    return {
        "schema": "agentkv_large_unified_barrier_analysis_v1",
        "suite": str(suite),
        "status": "completed",
        "input_requests_aligned": inputs_aligned,
        "runs": runs,
        "comparisons": comparisons,
        "limitations": [
            "One run per strategy in fixed LRU-SLRU-Barrier order.",
            "Closed-loop completion changes global submission interleaving between strategies.",
            "Historical inputs are fixed, but generated output content is not fed into later requests.",
            "Latency and throughput differences remain descriptive until repeated and order-balanced.",
        ],
    }


def write_markdown(result: dict, output: Path) -> None:
    lines = [
        "# 20 会话 Unified Exposure Barrier 扩大实验",
        "",
        f"Suite：`{result['suite']}`",
        "",
        "| 策略 | cached token | 命中率 | TTFT p95 | 延迟 p95 | 测量分钟 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for strategy, run in result["runs"].items():
        lines.append(
            f"| {strategy} | {run['cached_prompt_tokens']:,} | "
            f"{run['token_weighted_cache_hit_fraction'] * 100:.4f}% | "
            f"{run['ttft_seconds']['p95']:.3f}s | "
            f"{run['latency_seconds']['p95']:.3f}s | "
            f"{run['measurement_seconds'] / 60:.2f} |"
        )
    lines.extend(["", "## 相对 LRU", ""])
    for strategy, comparison in result["comparisons"].items():
        lines.append(
            f"- **{strategy}**：cached token {comparison['cached_prompt_token_delta_vs_lru']:+,}；"
            f"命中率 {comparison['cache_hit_percentage_point_delta_vs_lru']:+.4f} 个百分点；"
            f"TTFT p95 {comparison['ttft_p95_percent_vs_lru']:+.2f}%；"
            f"延迟 p95 {comparison['latency_p95_percent_vs_lru']:+.2f}%。"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 每种策略只运行一次，顺序固定为 LRU、SLRU、Unified Barrier。",
            "- 会话依赖回放会因完成时间不同改变全局请求交错，逐请求差异不是固定缓存状态反事实。",
            "- 延迟与吞吐仍需重复运行和顺序互换后才能形成正式结论。",
            "",
        ]
    )
    output.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.suite.resolve())
    save_json(args.output, result)
    write_markdown(result, args.markdown)
    print(json.dumps({"status": result["status"], "suite": result["suite"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
