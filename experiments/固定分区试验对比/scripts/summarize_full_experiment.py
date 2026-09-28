#!/usr/bin/env python3
"""Aggregate balanced AB/BA fixed-partition experiment repetitions."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


METRICS = (
    ("总体 token 加权命中率", "token_weighted_hit", "higher"),
    ("Agent token 加权命中率", "agent_hit", "higher"),
    ("普通请求 token 加权命中率", "request_hit", "higher"),
    ("总体 TTFT p50", "ttft_p50_ms", "lower"),
    ("总体 TTFT p90", "ttft_p90_ms", "lower"),
    ("总体 TTFT p99", "ttft_p99_ms", "lower"),
    ("Agent TTFT p90", "agent_ttft_p90_ms", "lower"),
    ("普通请求 TTFT p90", "request_ttft_p90_ms", "lower"),
    ("每秒请求数", "request_per_s", "higher"),
    ("每秒输出 token", "output_token_per_s", "higher"),
    ("实验墙钟时间", "wall_clock_s", "lower"),
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def mean_ci95(values: list[float]) -> tuple[float, float, float]:
    mean = statistics.fmean(values)
    if len(values) < 2:
        return mean, mean, mean
    critical = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(len(values), 1.96)
    half_width = critical * statistics.stdev(values) / math.sqrt(len(values))
    return mean, mean - half_width, mean + half_width


def fmt(value: float, percentage: bool = False) -> str:
    return f"{value:.2%}" if percentage else f"{value:.4f}"


def order_summary(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for order in ("unified-first", "partitioned-first"):
        values = [
            float(record["changes"][key])
            for record in records
            if record["order"] == order
        ]
        result[order] = {
            "count": len(values),
            "mean": statistics.fmean(values) if values else None,
            "values": values,
        }
    first = result["unified-first"]["mean"]
    second = result["partitioned-first"]["mean"]
    result["mean_difference_unified_first_minus_partitioned_first"] = (
        first - second if first is not None and second is not None else None
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-run-dir", type=Path, required=True)
    args = parser.parse_args()
    full_run_dir = args.full_run_dir.resolve()
    pair_dirs = sorted((full_run_dir / "pairs").glob("*"))
    records: list[dict[str, Any]] = []
    for pair_dir in pair_dirs:
        comparison_path = pair_dir / "comparison.json"
        status_path = pair_dir / "run_status.env"
        config_path = pair_dir / "config.env"
        if not comparison_path.is_file() or not status_path.is_file() or not config_path.is_file():
            continue
        status = read_env(status_path)
        if status.get("STATUS") != "completed":
            continue
        comparison = read_json(comparison_path)
        config = read_env(config_path)
        records.append(
            {
                "pair": pair_dir.name,
                "order": config["EXPERIMENT_ORDER"],
                "ratio": comparison.get("agent_cache_capacity_ratio"),
                "controls": comparison["server_control_variables"],
                "unified": comparison["unified"],
                "partitioned": comparison["partitioned"],
                "changes": comparison["relative_change_partitioned_vs_unified"],
            }
        )
    if len(records) < 2:
        raise SystemExit("至少需要两组已完成的配对实验")

    orders = [record["order"] for record in records]
    if abs(orders.count("unified-first") - orders.count("partitioned-first")) > 1:
        raise SystemExit(f"实验顺序不平衡：{orders}")
    reference_controls = records[0]["controls"]
    reference_ratio = records[0]["ratio"]
    for record in records[1:]:
        if record["controls"] != reference_controls:
            raise SystemExit(f"服务控制变量不一致：{record['pair']}")
        if record["ratio"] != reference_ratio:
            raise SystemExit(f"固定分区比例不一致：{record['pair']}")

    aggregates: dict[str, Any] = {}
    for label, key, direction in METRICS:
        changes = [float(record["changes"][key]) for record in records]
        mean, ci_low, ci_high = mean_ci95(changes)
        aggregates[key] = {
            "label": label,
            "direction": direction,
            "unified_mean": statistics.fmean(float(record["unified"][key]) for record in records),
            "partitioned_mean": statistics.fmean(float(record["partitioned"][key]) for record in records),
            "relative_change_mean": mean,
            "relative_change_median": statistics.median(changes),
            "relative_change_min": min(changes),
            "relative_change_max": max(changes),
            "relative_change_ci95_low": ci_low,
            "relative_change_ci95_high": ci_high,
            "all_relative_changes": changes,
            "same_direction_count": max(
                sum(value > 0 for value in changes),
                sum(value < 0 for value in changes),
            ),
            "order_summary": order_summary(records, key),
        }

    result = {
        "full_run_dir": str(full_run_dir),
        "pair_count": len(records),
        "orders": orders,
        "agent_cache_capacity_ratio": reference_ratio,
        "server_control_variables": reference_controls,
        "pairs": records,
        "aggregates": aggregates,
    }
    (full_run_dir / "full_experiment.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# 固定分区完整实验汇总",
        "",
        f"- 配对重复：{len(records)} 组；",
        f"- 顺序：{' / '.join(orders)}；",
        f"- Agent 缓存容量比例：{reference_ratio:.0%}；",
        "- 置信区间：配对相对变化均值的 95% Student t 区间。",
        "",
        "| 指标 | 统一缓存均值 | 固定分区均值 | 相对变化均值 | 中位数 | 范围 | 95% 区间 | 各组相对变化 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    percentage_metrics = {"token_weighted_hit", "agent_hit", "request_hit"}
    for _, key, _ in METRICS:
        item = aggregates[key]
        values = ", ".join(fmt(value, True) for value in item["all_relative_changes"])
        lines.append(
            f"| {item['label']} | {fmt(item['unified_mean'], key in percentage_metrics)} | "
            f"{fmt(item['partitioned_mean'], key in percentage_metrics)} | "
            f"{fmt(item['relative_change_mean'], True)} | "
            f"{fmt(item['relative_change_median'], True)} | "
            f"[{fmt(item['relative_change_min'], True)}, {fmt(item['relative_change_max'], True)}] | "
            f"[{fmt(item['relative_change_ci95_low'], True)}, {fmt(item['relative_change_ci95_high'], True)}] | "
            f"{values} |"
        )
    lines.extend(
        [
            "",
            "> 表中的相对变化统一按 `(固定分区 - 统一缓存) / 统一缓存` 计算：命中率和吞吐为正表示提高；TTFT 与墙钟时间为负表示降低。",
            "",
            "## AB/BA 顺序效应",
            "",
            "| 指标 | 统一缓存先运行均值 | 固定分区先运行均值 | 两种顺序均值差 |",
            "|---|---:|---:|---:|",
        ]
    )
    for _, key, _ in METRICS:
        item = aggregates[key]
        order = item["order_summary"]
        first = order["unified-first"]["mean"]
        second = order["partitioned-first"]["mean"]
        difference = order["mean_difference_unified_first_minus_partitioned_first"]
        lines.append(
            f"| {item['label']} | {fmt(first, True)} | {fmt(second, True)} | "
            f"{fmt(difference, True)} |"
        )
    lines.extend(
        [
            "",
            "> 两种顺序的均值差越接近 0，说明结果越不受先后顺序影响。",
            "",
        ]
    )
    (full_run_dir / "full_experiment.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[written] {full_run_dir / 'full_experiment.json'}")
    print(f"[written] {full_run_dir / 'full_experiment.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
