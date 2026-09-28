#!/usr/bin/env python3
"""Compare unified-cache and fixed-partition replay outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_path(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def percent_change(
    baseline: float | int | None, candidate: float | int | None
) -> float | None:
    if baseline in (None, 0) or candidate is None:
        return None
    return (float(candidate) - float(baseline)) / float(baseline)


def extract_replay(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "requests_ok": get_path(summary, "integrity", "n_ok"),
        "requests_error": get_path(summary, "integrity", "n_err"),
        "wall_clock_s": get_path(summary, "integrity", "wall_clock_s"),
        "request_per_s": get_path(summary, "throughput", "req_per_s"),
        "output_token_per_s": get_path(summary, "throughput", "output_tok_per_s"),
        "token_weighted_hit": get_path(summary, "kv", "token_weighted_hit"),
        "cached_tokens": get_path(summary, "kv", "cached_tokens_sum"),
        "prompt_tokens": get_path(summary, "kv", "prompt_tokens_sum"),
        "completion_tokens": get_path(summary, "kv", "completion_tokens_sum"),
        "ttft_p50_ms": get_path(summary, "latency", "ttft_ms", "p50"),
        "ttft_p90_ms": get_path(summary, "latency", "ttft_ms", "p90"),
        "ttft_p99_ms": get_path(summary, "latency", "ttft_ms", "p99"),
        "agent_hit": get_path(summary, "agent", "token_weighted_hit"),
        "agent_ttft_p50_ms": get_path(summary, "agent", "ttft_ms", "p50"),
        "agent_ttft_p90_ms": get_path(summary, "agent", "ttft_ms", "p90"),
        "request_hit": get_path(summary, "request", "token_weighted_hit"),
        "request_ttft_p50_ms": get_path(summary, "request", "ttft_ms", "p50"),
        "request_ttft_p90_ms": get_path(summary, "request", "ttft_ms", "p90"),
    }


def extract_regions(server_info: dict[str, Any]) -> dict[str, Any] | None:
    states = server_info.get("internal_states") or []
    if not states:
        return None
    return states[0].get("request_cache_regions")


def fmt(value: Any, percentage: bool = False) -> str:
    if value is None:
        return "-"
    if percentage:
        return f"{float(value):.4%}"
    if isinstance(value, float):
        return f"{value:.4f}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    unified_summary_path = run_dir / "unified/run_mix_replay/summary.json"
    partitioned_summary_path = run_dir / "partitioned/run_mix_replay/summary.json"
    unified_info_path = run_dir / "unified/server_info_before.json"
    partitioned_info_before_path = run_dir / "partitioned/server_info_before.json"
    partitioned_info_path = run_dir / "partitioned/server_info_after.json"
    for path in (
        unified_summary_path,
        partitioned_summary_path,
        unified_info_path,
        partitioned_info_before_path,
        partitioned_info_path,
    ):
        if not path.is_file():
            raise SystemExit(f"missing experiment output: {path}")

    unified = extract_replay(read_json(unified_summary_path))
    partitioned = extract_replay(read_json(partitioned_summary_path))
    controlled_fields = (
        "requests_ok",
        "requests_error",
        "prompt_tokens",
        "completion_tokens",
    )
    mismatches = {
        key: (unified.get(key), partitioned.get(key))
        for key in controlled_fields
        if unified.get(key) != partitioned.get(key)
    }
    if mismatches:
        details = ", ".join(
            f"{key}: unified={values[0]} partitioned={values[1]}"
            for key, values in mismatches.items()
        )
        raise SystemExit(f"control-variable mismatch: {details}")
    unified_info = read_json(unified_info_path)
    partitioned_info_before = read_json(partitioned_info_before_path)
    server_control_fields = (
        "model_path",
        "served_model_name",
        "tp_size",
        "mem_fraction_static",
        "disable_cuda_graph",
        "cuda_graph_config",
        "random_seed",
        "max_total_num_tokens",
        "page_size",
        "swa_full_tokens_ratio",
        "radix_eviction_policy",
    )
    server_mismatches = {
        key: (unified_info.get(key), partitioned_info_before.get(key))
        for key in server_control_fields
        if unified_info.get(key) != partitioned_info_before.get(key)
    }
    if server_mismatches:
        details = ", ".join(
            f"{key}: unified={values[0]!r} partitioned={values[1]!r}"
            for key, values in server_mismatches.items()
        )
        raise SystemExit(f"server control-variable mismatch: {details}")
    regions = extract_regions(read_json(partitioned_info_path))
    changes = {
        key: percent_change(unified.get(key), partitioned.get(key))
        for key in unified
        if isinstance(unified.get(key), (int, float))
        and isinstance(partitioned.get(key), (int, float))
    }
    result = {
        "run_dir": str(run_dir),
        "unified": unified,
        "partitioned": partitioned,
        "relative_change_partitioned_vs_unified": changes,
        "server_control_variables": {
            key: unified_info.get(key) for key in server_control_fields
        },
        "partitioned_request_cache_regions": regions,
    }
    selected_ratio_path = run_dir / "selected_ratio.env"
    if selected_ratio_path.is_file():
        for line in selected_ratio_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("AGENT_CACHE_CAPACITY_RATIO="):
                result["agent_cache_capacity_ratio"] = float(line.split("=", 1)[1])
                break
    json_path = run_dir / "comparison.json"
    markdown_path = run_dir / "comparison.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = [
        ("总体 token 加权命中率", "token_weighted_hit", True),
        ("Agent token 加权命中率", "agent_hit", True),
        ("普通请求 token 加权命中率", "request_hit", True),
        ("总体 TTFT p50 (ms)", "ttft_p50_ms", False),
        ("总体 TTFT p90 (ms)", "ttft_p90_ms", False),
        ("总体 TTFT p99 (ms)", "ttft_p99_ms", False),
        ("Agent TTFT p50 (ms)", "agent_ttft_p50_ms", False),
        ("Agent TTFT p90 (ms)", "agent_ttft_p90_ms", False),
        ("普通请求 TTFT p50 (ms)", "request_ttft_p50_ms", False),
        ("普通请求 TTFT p90 (ms)", "request_ttft_p90_ms", False),
        ("每秒请求数", "request_per_s", False),
        ("每秒输出 token", "output_token_per_s", False),
        ("实验墙钟时间 (s)", "wall_clock_s", False),
    ]
    lines = [
        "# 固定分区配对实验结果",
        "",
        "| 指标 | 统一缓存 | 固定分区 | 相对变化 |",
        "|---|---:|---:|---:|",
    ]
    for label, key, percentage in rows:
        change = changes.get(key)
        lines.append(
            f"| {label} | {fmt(unified.get(key), percentage)} | "
            f"{fmt(partitioned.get(key), percentage)} | "
            f"{fmt(change, True)} |"
        )
    lines.extend(
        [
            "",
            "## 控制变量验收",
            "",
            "| 字段 | 统一缓存 | 固定分区 | 是否一致 |",
            "|---|---:|---:|---:|",
        ]
    )
    for key, label in (
        ("requests_ok", "成功请求数"),
        ("requests_error", "失败请求数"),
        ("prompt_tokens", "prompt token 总数"),
        ("completion_tokens", "completion token 总数"),
    ):
        lines.append(
            f"| {label} | {fmt(unified.get(key))} | "
            f"{fmt(partitioned.get(key))} | 是 |"
        )
    lines.extend(
        [
            "",
            "### 服务参数",
            "",
            "| 字段 | 两轮共同值 |",
            "|---|---:|",
        ]
    )
    for key in server_control_fields:
        lines.append(f"| {key} | {fmt(unified_info.get(key))} |")
    lines.extend(["", "## 固定分区结束状态", ""])
    if regions:
        lines.extend(
            [
                "| 区域 | Full 容量 | Full 占用 | SWA 容量 | SWA 占用 | Full 驱逐 | SWA 驱逐 |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for region in ("agent", "request"):
            block = regions.get(region, {})
            lines.append(
                f"| {region} | {fmt(block.get('full_capacity_tokens'))} | "
                f"{fmt(block.get('full_used_tokens'))} | "
                f"{fmt(block.get('swa_capacity_tokens'))} | "
                f"{fmt(block.get('swa_used_tokens'))} | "
                f"{fmt(block.get('full_evicted_tokens'))} | "
                f"{fmt(block.get('swa_evicted_tokens'))} |"
            )
    else:
        lines.append("未读取到 request_cache_regions。")
    lines.extend(
        [
            "",
            "> 命中率提高为正向；TTFT 和墙钟时间降低为正向，因此需要结合指标方向解读相对变化。",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[written] {json_path}")
    print(f"[written] {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
