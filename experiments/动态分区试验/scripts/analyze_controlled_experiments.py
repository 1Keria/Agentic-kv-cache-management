#!/usr/bin/env python3
"""Summarize controlled dynamic-partition experiments."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def get_path(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def summary_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    prompt = get_path(summary, "kv", "prompt_tokens_sum")
    cached = get_path(summary, "kv", "cached_tokens_sum")
    return {
        "requests_ok": get_path(summary, "integrity", "n_ok"),
        "requests_err": get_path(summary, "integrity", "n_err"),
        "wall_clock_s": get_path(summary, "integrity", "wall_clock_s"),
        "request_per_s": get_path(summary, "throughput", "req_per_s"),
        "output_token_per_s": get_path(summary, "throughput", "output_tok_per_s"),
        "overall_hit": get_path(summary, "kv", "token_weighted_hit"),
        "cached_tokens": get_path(summary, "kv", "cached_tokens_sum"),
        "prompt_tokens": get_path(summary, "kv", "prompt_tokens_sum"),
        "uncached_prompt_tokens": prompt - cached if prompt is not None and cached is not None else None,
        "agent_hit": get_path(summary, "agent", "token_weighted_hit"),
        "request_hit": get_path(summary, "request", "token_weighted_hit"),
        "ttft_p50_ms": get_path(summary, "latency", "ttft_ms", "p50"),
        "ttft_p90_ms": get_path(summary, "latency", "ttft_ms", "p90"),
        "ttft_mean_ms": get_path(summary, "latency", "ttft_ms", "mean"),
        "agent_ttft_mean_ms": get_path(summary, "agent", "ttft_ms", "mean"),
        "request_ttft_mean_ms": get_path(summary, "request", "ttft_ms", "mean"),
    }


def extract_state(info: dict[str, Any]) -> dict[str, Any]:
    states = info.get("internal_states") or []
    return states[0] if states else {}


def region_metrics(info: dict[str, Any]) -> dict[str, Any] | None:
    return extract_state(info).get("request_cache_regions")


def region_totals(regions: dict[str, Any] | None) -> dict[str, Any] | None:
    if not regions:
        return None
    return {
        "full_evicted_tokens": sum(
            int(item.get("full_evicted_tokens") or 0) for item in regions.values()
        ),
        "swa_evicted_tokens": sum(
            int(item.get("swa_evicted_tokens") or 0) for item in regions.values()
        ),
        "max_full_effective_capacity_tokens": max(
            int(item.get("full_capacity_tokens") or 0) for item in regions.values()
        ),
        "max_swa_effective_capacity_tokens": max(
            int(item.get("swa_capacity_tokens") or 0) for item in regions.values()
        ),
    }


def region_pair(regions: dict[str, Any] | None, field: str) -> str:
    if not regions:
        return "-"
    return " / ".join(
        f"{region}={int(regions.get(region, {}).get(field) or 0)}"
        for region in ("agent", "request")
    )


def trajectory_metrics(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    samples = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    region_samples = [row for row in samples if row.get("regions")]
    region_peaks = {
        region: {
            field: max(int(row["regions"].get(region, {}).get(field) or 0) for row in region_samples)
            for field in (
                "full_used_tokens", "swa_used_tokens",
                "full_cached_borrowed_tokens", "swa_cached_borrowed_tokens",
                "full_over_quota_tokens", "swa_over_quota_tokens",
            )
        }
        for region in ("agent", "request")
    } if region_samples else None
    controllers = [row.get("controller") for row in samples if row.get("controller")]
    if not controllers:
        return {"sample_count": len(samples)}
    ratios = [float(item["current_agent_ratio"]) for item in controllers]
    updates: list[dict[str, Any]] = []
    seen = -1
    for row in samples:
        controller = row.get("controller")
        if not controller:
            continue
        count = int(controller.get("update_count") or 0)
        if count > seen:
            if count > 0:
                updates.append(
                    {
                        "elapsed_s": row["elapsed_s"],
                        "update_count": count,
                        "ratio": controller.get("current_agent_ratio"),
                        "last_agent_evicted_tokens": controller.get(
                            "last_feedback_agent_evicted_tokens"
                        ),
                        "last_request_evicted_tokens": controller.get(
                            "last_feedback_request_evicted_tokens"
                        ),
                        "last_agent_eviction_share": controller.get(
                            "last_feedback_agent_eviction_share"
                        ),
                    }
                )
            seen = count
    return {
        "sample_count": len(samples),
        "region_peaks": region_peaks,
        "ratio_initial": ratios[0],
        "ratio_final": ratios[-1],
        "ratio_min": min(ratios),
        "ratio_max": max(ratios),
        "update_count": int(controllers[-1].get("update_count") or 0),
        "updates_observed_by_sampler": updates,
    }


def phase_metrics(mode_dir: Path, assignment_path: Path) -> dict[str, Any] | None:
    if not assignment_path.is_file():
        return None
    assignment = read_json(assignment_path)
    session_phase = {
        session_id: phase["name"]
        for phase in assignment["phases"]
        for session_id in phase["session_ids"]
    }
    rows = [
        json.loads(line)
        for line in (mode_dir / "run_mix_replay/replay.jsonl").read_text().splitlines()
        if line.strip()
    ]
    result: dict[str, Any] = {}
    for phase in assignment["phases"]:
        selected = [row for row in rows if session_phase.get(row["session_id"]) == phase["name"]]
        prompt = sum(int(row.get("prompt_tokens") or 0) for row in selected)
        cached = sum(int(row.get("cached_tokens") or 0) for row in selected)
        ttfts = [float(row["ttft_ms"]) for row in selected if row.get("ttft_ms") is not None]
        first_turns = [row for row in selected if int(row["turn_index"]) == 0]
        first_prompt = sum(int(row.get("prompt_tokens") or 0) for row in first_turns)
        first_cached = sum(int(row.get("cached_tokens") or 0) for row in first_turns)
        result[phase["name"]] = {
            "requests": len(selected),
            "prompt_tokens": prompt,
            "cached_tokens": cached,
            "token_weighted_hit": cached / prompt if prompt else None,
            "ttft_mean_ms": statistics.fmean(ttfts) if ttfts else None,
            "first_turn_requests": len(first_turns),
            "first_turn_cached_tokens": first_cached,
            "first_turn_prompt_tokens": first_prompt,
            "first_turn_token_weighted_hit": first_cached / first_prompt if first_prompt else None,
            "actual_first_start_s": min(float(row["s_time_ms"]) for row in selected) / 1000 if selected else None,
            "actual_last_end_s": max(float(row["e_time_ms"]) for row in selected if row.get("e_time_ms") is not None) / 1000 if any(row.get("e_time_ms") is not None for row in selected) else None,
        }
    return result


def percent_change(base: float | int | None, candidate: float | int | None) -> float | None:
    if base in (None, 0) or candidate is None:
        return None
    return (float(candidate) - float(base)) / float(base)


def fmt(value: Any, percentage: bool = False) -> str:
    if value is None:
        return "-"
    if percentage:
        return f"{float(value):.4%}"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    run_root = args.run_root.resolve()
    all_results: dict[str, Any] = {}
    report = ["# 动态分区受控实验结果", ""]

    # Accept either the historical parent directory containing many scenarios
    # or one direct scenario directory produced by run_controlled_experiment.
    # The latter keeps each long-running comparison self-describing without
    # rewriting an unrelated aggregate report.
    scenario_dirs = (
        [run_root]
        if (run_root / "config.json").is_file()
        else sorted(path for path in run_root.iterdir() if path.is_dir())
    )
    for scenario_dir in scenario_dirs:
        config_path = scenario_dir / "config.json"
        if not config_path.is_file():
            continue
        config = read_json(config_path)
        phase_assignment_path = Path(config["workload_dir"]) / "phase_assignment.json"
        scenario: dict[str, Any] = {"config": config, "modes": {}}
        for mode in config["modes"]:
            mode_dir = scenario_dir / mode
            summary_path = mode_dir / "run_mix_replay/summary.json"
            if not summary_path.is_file():
                continue
            summary = summary_metrics(read_json(summary_path))
            after = read_json(mode_dir / "server_info_after.json")
            scenario["modes"][mode] = {
                "summary": summary,
                "regions_after": region_metrics(after),
                "region_totals_after": region_totals(region_metrics(after)),
                "controller_after": extract_state(after).get("request_cache_region_controller"),
                "trajectory": trajectory_metrics(mode_dir / "controller_trajectory.jsonl"),
                "phases": phase_metrics(mode_dir, phase_assignment_path),
            }
        modes = scenario["modes"]
        comparisons: dict[str, Any] = {}
        for base, candidate in (
            ("native", "fixed"),
            ("native", "borrow"),
            ("native", "unified"),
            ("unified", "fixed"),
            ("fixed", "dynamic"),
            ("unified", "dynamic"),
            ("fixed", "borrow"),
            ("unified", "borrow"),
        ):
            if base not in modes or candidate not in modes:
                continue
            comparisons[f"{candidate}_vs_{base}"] = {
                key: percent_change(modes[base]["summary"].get(key), modes[candidate]["summary"].get(key))
                for key in modes[base]["summary"]
                if isinstance(modes[base]["summary"].get(key), (int, float))
                and isinstance(modes[candidate]["summary"].get(key), (int, float))
            }
            comparisons[f"{candidate}_vs_{base}"].update({
                f"{key}_delta_pp": 100 * (
                    modes[candidate]["summary"][key] - modes[base]["summary"][key]
                )
                for key in ("overall_hit", "agent_hit", "request_hit")
                if modes[base]["summary"].get(key) is not None
                and modes[candidate]["summary"].get(key) is not None
            })
        scenario["comparisons"] = comparisons
        all_results[scenario_dir.name] = scenario

        report.extend([f"## {scenario_dir.name}", ""])
        report.extend(
            [
                "| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for mode, data in modes.items():
            item = data["summary"]
            report.append(
                f"| {mode} | {fmt(item['overall_hit'], True)} | {fmt(item['agent_hit'], True)} | "
                f"{fmt(item['request_hit'], True)} | {item['cached_tokens']} | "
                f"{fmt(item['wall_clock_s'])} | {fmt(item['ttft_p50_ms'])} |"
            )
        report.append("")
        for label, comparison in comparisons.items():
            report.append(
                f"- {label}: 总体命中率变化 {fmt(comparison.get('overall_hit_delta_pp'))} pp，"
                f"Agent 命中率变化 {fmt(comparison.get('agent_hit_delta_pp'))} pp，"
                f"普通请求命中率变化 {fmt(comparison.get('request_hit_delta_pp'))} pp。"
            )
        report.extend(
            [
                "",
                "| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for mode, data in modes.items():
            totals = data.get("region_totals_after") or {}
            regions = data.get("regions_after")
            report.append(
                f"| {mode} | {totals.get('full_evicted_tokens', '-')} | "
                f"{totals.get('swa_evicted_tokens', '-')} | "
                f"{region_pair(regions, 'full_borrowed_tokens')} | "
                f"{region_pair(regions, 'swa_borrowed_tokens')} |"
            )
        report.append("")
        report.extend([
            "到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。",
            "未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。",
            "可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。",
            "",
        ])
        dynamic = modes.get("dynamic")
        if dynamic and dynamic.get("trajectory"):
            trajectory = dynamic["trajectory"]
            report.append(
                f"- dynamic ratio: {trajectory.get('ratio_initial')} -> {trajectory.get('ratio_final')}，"
                f"范围 [{trajectory.get('ratio_min')}, {trajectory.get('ratio_max')}]，"
                f"更新 {trajectory.get('update_count')} 次。"
            )
        report.append("")

    (run_root / "analysis.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2) + "\n"
    )
    (run_root / "analysis.md").write_text("\n".join(report) + "\n")
    print(run_root / "analysis.json")
    print(run_root / "analysis.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
