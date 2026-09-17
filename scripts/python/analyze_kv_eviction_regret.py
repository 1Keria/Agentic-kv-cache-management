#!/usr/bin/env python3
"""Attribute KV misses to cold pages or prior LRU eviction."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    denom_y = sum((y - mean_y) ** 2 for y in ys)
    if denom_x == 0 or denom_y == 0:
        return None
    return numerator / (denom_x * denom_y) ** 0.5


def load_request_results(path: Path) -> dict[str, dict[str, Any]]:
    results = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            trace_id = row.get("trace_id")
            if trace_id is not None:
                results[str(trace_id)] = row
    return results


def select_process(
    path: Path,
    request_ids: set[str] | None,
    requested_pid: int | None,
) -> tuple[int, list[dict[str, int]]]:
    per_pid: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            event = json.loads(line)
            pid = event.get("pid")
            if pid is None:
                continue
            info = per_pid.setdefault(
                int(pid),
                {
                    "request_ids": set(),
                    "events": 0,
                    "request_matches": 0,
                    "target_request_matches": 0,
                    "non_target_request_matches": 0,
                },
            )
            info["events"] += 1
            if event.get("event") == "request_match":
                info["request_matches"] += 1
                request_id = str(event.get("request_id"))
                if request_ids is None or request_id in request_ids:
                    info["target_request_matches"] += 1
                    info["request_ids"].add(request_id)
                else:
                    info["non_target_request_matches"] += 1

    if not per_pid:
        raise ValueError(
            "trace has no pid field; restart the diagnostic server and rerun "
            "with sglang_kv_diag_v2"
        )
    if requested_pid is not None and requested_pid not in per_pid:
        raise ValueError(f"pid {requested_pid} does not exist in {path}")

    candidates = [
        {
            "pid": pid,
            "matched_unique_request_ids": len(info["request_ids"]),
            "request_matches": info["request_matches"],
            "target_request_matches": info["target_request_matches"],
            "non_target_request_matches": info["non_target_request_matches"],
            "duplicate_request_rows": (
                info["target_request_matches"] - len(info["request_ids"])
            ),
            "events": info["events"],
        }
        for pid, info in per_pid.items()
    ]
    candidates.sort(
        key=lambda row: (
            row["matched_unique_request_ids"],
            -row["duplicate_request_rows"],
            row["events"],
        ),
        reverse=True,
    )
    selected_pid = requested_pid if requested_pid is not None else candidates[0]["pid"]
    return selected_pid, candidates


def analyze(
    path: Path,
    selected_pid: int,
    request_ids: set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, list[float]]]:
    resident: set[str] = set()
    ever_stored: set[str] = set()
    last_eviction: dict[str, dict[str, Any]] = {}
    cumulative_stored_tokens = 0
    request_number = 0
    event_counts: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    reuse_ms: list[float] = []
    reuse_request_distance: list[int] = []
    reuse_token_distance: list[int] = []
    requests: list[dict[str, Any]] = []
    seen_request_ids: set[str] = set()
    raw_request_rows = 0
    rematch_rows = 0
    non_target_request_rows = 0

    with path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSON at {path}:{line_number}: {exc}"
                ) from exc
            if event.get("pid") != selected_pid:
                continue

            kind = event.get("event")
            event_counts[kind] += 1
            if kind == "cache_reset":
                resident.clear()
                ever_stored.clear()
                last_eviction.clear()
                cumulative_stored_tokens = 0
            elif kind == "cache_store" and event.get("medium") == "GPU":
                hashes = event.get("block_hashes") or []
                resident.update(hashes)
                ever_stored.update(hashes)
                cumulative_stored_tokens += int(event.get("stored_tokens") or 0)
                totals["stored_tokens"] += int(event.get("stored_tokens") or 0)
            elif kind == "cache_evict" and event.get("medium") == "GPU":
                page_size = int(event["page_size"])
                for block_hash in event.get("block_hashes") or []:
                    resident.discard(block_hash)
                    last_eviction[block_hash] = {
                        "time_monotonic_s": float(event["time_monotonic_s"]),
                        "request_number": request_number,
                        "cumulative_stored_tokens": cumulative_stored_tokens,
                    }
                totals["evicted_tokens"] += int(event.get("evicted_tokens") or 0)
                totals["evicted_pages"] += len(event.get("block_hashes") or [])
                totals["eviction_page_tokens"] += (
                    len(event.get("block_hashes") or []) * page_size
                )
            elif kind == "request_match":
                raw_request_rows += 1
                request_id = str(event.get("request_id"))
                if request_ids is not None and request_id not in request_ids:
                    non_target_request_rows += 1
                    continue
                if request_id in seen_request_ids:
                    rematch_rows += 1
                    continue

                seen_request_ids.add(request_id)
                request_number += 1
                page_size = int(event["page_size"])
                matched_pages = int(event["matched_tokens"]) // page_size
                missing = (event.get("block_hashes") or [])[matched_pages:]
                classes: Counter[str] = Counter()
                request_reuse_ms: list[float] = []

                for block_hash in missing:
                    if block_hash not in ever_stored:
                        miss_class = "cold"
                    elif block_hash not in resident and block_hash in last_eviction:
                        miss_class = "eviction"
                        prior = last_eviction[block_hash]
                        delta_ms = (
                            float(event["time_monotonic_s"]) - prior["time_monotonic_s"]
                        ) * 1000
                        request_reuse_ms.append(delta_ms)
                        reuse_ms.append(delta_ms)
                        reuse_request_distance.append(
                            request_number - prior["request_number"]
                        )
                        reuse_token_distance.append(
                            cumulative_stored_tokens - prior["cumulative_stored_tokens"]
                        )
                    else:
                        miss_class = "other"
                    classes[miss_class] += page_size
                    totals[f"{miss_class}_miss_tokens"] += page_size

                totals["prompt_tokens"] += int(event["prompt_tokens"])
                totals["matched_tokens"] += int(event["matched_tokens"])
                totals["miss_tokens"] += len(missing) * page_size
                requests.append(
                    {
                        "request_id": request_id,
                        "request_number": request_number,
                        "prompt_tokens": event["prompt_tokens"],
                        "matched_tokens": event["matched_tokens"],
                        "cold_miss_tokens": classes["cold"],
                        "eviction_miss_tokens": classes["eviction"],
                        "other_miss_tokens": classes["other"],
                        "eviction_reuse_ms_min": (
                            min(request_reuse_ms) if request_reuse_ms else None
                        ),
                        "kv_available_tokens": event.get("kv_available_tokens"),
                        "kv_evictable_tokens": event.get("kv_evictable_tokens"),
                        "kv_protected_tokens": event.get("kv_protected_tokens"),
                    }
                )

    miss_tokens = totals["miss_tokens"]
    summary = {
        "input": str(path),
        "selected_pid": selected_pid,
        "event_counts": dict(event_counts),
        "requests": request_number,
        "unique_requests": request_number,
        "rematch_rows": rematch_rows,
        "non_target_request_rows": non_target_request_rows,
        "request_rows": {
            "target": raw_request_rows - non_target_request_rows,
            "raw": raw_request_rows,
            "unique_requests": request_number,
            "rematch_rows": rematch_rows,
            "non_target_request_rows": non_target_request_rows,
        },
        "tokens": dict(totals),
        "ratios": {
            "observed_hit_ratio": (
                totals["matched_tokens"] / totals["prompt_tokens"]
                if totals["prompt_tokens"]
                else None
            ),
            "eviction_regret_ratio": (
                totals["eviction_miss_tokens"] / miss_tokens if miss_tokens else None
            ),
            "cold_miss_ratio": (
                totals["cold_miss_tokens"] / miss_tokens if miss_tokens else None
            ),
            "other_miss_ratio": (
                totals["other_miss_tokens"] / miss_tokens if miss_tokens else None
            ),
        },
        "eviction_reuse": {
            "page_observations": len(reuse_ms),
            "time_ms_p50": percentile(reuse_ms, 0.5),
            "time_ms_p90": percentile(reuse_ms, 0.9),
            "request_distance_p50": percentile(reuse_request_distance, 0.5),
            "request_distance_p90": percentile(reuse_request_distance, 0.9),
            "inserted_token_distance_p50": percentile(reuse_token_distance, 0.5),
            "inserted_token_distance_p90": percentile(reuse_token_distance, 0.9),
        },
    }
    plot_data = {
        "reuse_ms": reuse_ms,
        "reuse_request_distance": reuse_request_distance,
        "reuse_token_distance": reuse_token_distance,
    }
    return summary, requests, plot_data


def build_timeline(
    requests: list[dict[str, Any]], bins: int = 20
) -> list[dict[str, Any]]:
    timed = [row for row in requests if row.get("s_time_ms") is not None]
    if not timed:
        timed = [{**row, "s_time_ms": float(row["request_number"])} for row in requests]
    if not timed:
        return []
    end_ms = max(float(row["s_time_ms"]) for row in timed)
    width_ms = max(end_ms / bins, 1.0)
    output = [
        {
            "start_min": i * width_ms / 60000.0,
            "end_min": (i + 1) * width_ms / 60000.0,
            "requests": 0,
            "cold_miss_tokens": 0,
            "eviction_miss_tokens": 0,
            "other_miss_tokens": 0,
        }
        for i in range(bins)
    ]
    for row in timed:
        bucket = output[min(int(float(row["s_time_ms"]) / width_ms), bins - 1)]
        bucket["requests"] += 1
        for key in ("cold_miss_tokens", "eviction_miss_tokens", "other_miss_tokens"):
            bucket[key] += int(row.get(key) or 0)
    return output


def build_request_quarters(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(requests, key=lambda row: int(row["request_number"]))
    output = []
    for index in range(4):
        lo, hi = len(ordered) * index // 4, len(ordered) * (index + 1) // 4
        rows = ordered[lo:hi]
        cold = sum(int(row.get("cold_miss_tokens") or 0) for row in rows)
        eviction = sum(int(row.get("eviction_miss_tokens") or 0) for row in rows)
        other = sum(int(row.get("other_miss_tokens") or 0) for row in rows)
        miss = cold + eviction + other
        output.append(
            {
                "quarter": index + 1,
                "request_start": lo + 1,
                "request_end": hi,
                "requests": len(rows),
                "cold_miss_tokens": cold,
                "eviction_miss_tokens": eviction,
                "other_miss_tokens": other,
                "eviction_share_of_miss": eviction / miss if miss else None,
                "requests_with_eviction_miss": sum(
                    int(row.get("eviction_miss_tokens") or 0) > 0 for row in rows
                ),
            }
        )
    return output


def create_plots(
    summary: dict[str, Any],
    requests: list[dict[str, Any]],
    plot_data: dict[str, list[float]],
    prefix: Path,
) -> dict[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 140, "axes.grid": True, "grid.alpha": 0.25})
    colors = {"cold": "#26734d", "eviction": "#c53b32"}
    paths: dict[str, str] = {}

    def save(fig: Any, key: str, suffix: str):
        path = Path(f"{prefix}.{suffix}.png")
        fig.tight_layout()
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        paths[key] = path.name

    timeline = summary["timeline"]
    fig, ax = plt.subplots(figsize=(9.2, 4.2))
    x = [(row["start_min"] + row["end_min"]) / 2 for row in timeline]
    ax.plot(
        x,
        [row["cold_miss_tokens"] for row in timeline],
        marker="o",
        ms=3,
        color=colors["cold"],
        label="Cold miss",
    )
    ax.plot(
        x,
        [row["eviction_miss_tokens"] for row in timeline],
        marker="o",
        ms=3,
        color=colors["eviction"],
        label="Eviction miss",
    )
    ax.set(
        xlabel="Replay time (min)",
        ylabel="Miss tokens per time bin",
        title="Cold and eviction miss timeline",
    )
    ax.legend()
    save(fig, "miss_timeline", "miss_timeline")

    def cdf(
        values: list[float], key: str, suffix: str, xlabel: str, scale: float = 1.0
    ):
        xs = sorted(float(value) / scale for value in values)
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        if xs:
            ax.plot(
                xs,
                [(i + 1) / len(xs) for i in range(len(xs))],
                color="#2563a6",
                linewidth=1.8,
            )
            for y in (0.5, 0.9):
                ax.axhline(y, color="#6b7280", linestyle="--", linewidth=0.8)
        ax.set(
            xlabel=xlabel, ylabel="CDF", title=xlabel + " distribution", ylim=(0, 1.01)
        )
        save(fig, key, suffix)

    cdf(
        plot_data["reuse_ms"],
        "reuse_time_cdf",
        "reuse_time_cdf",
        "Eviction-to-reuse time (min)",
        60000.0,
    )
    cdf(
        plot_data["reuse_request_distance"],
        "request_distance_cdf",
        "request_distance_cdf",
        "Unique-request distance",
    )
    cdf(
        plot_data["reuse_token_distance"],
        "inserted_token_distance_cdf",
        "inserted_token_distance_cdf",
        "Inserted-token distance (million tokens)",
        1_000_000.0,
    )

    joined = [row for row in requests if row.get("ttft_ms") is not None]
    fig, ax = plt.subplots(figsize=(7.6, 4.5))
    ax.scatter(
        [row["cold_miss_tokens"] for row in joined],
        [row["ttft_ms"] for row in joined],
        s=12,
        alpha=0.45,
        color=colors["cold"],
        label="Cold miss",
    )
    ax.scatter(
        [row["eviction_miss_tokens"] for row in joined],
        [row["ttft_ms"] for row in joined],
        s=12,
        alpha=0.45,
        color=colors["eviction"],
        label="Eviction miss",
    )
    ax.set(
        xlabel="Miss tokens per request",
        ylabel="TTFT (ms)",
        title="TTFT versus miss tokens",
    )
    ax.legend()
    save(fig, "ttft_vs_miss", "ttft_vs_miss")
    return paths


def build_baseline_comparison(
    replay: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
    baseline_path: Path | None,
) -> dict[str, Any] | None:
    if replay is None or baseline is None:
        return None
    metrics = {
        "n_ok": (replay["integrity"]["n_ok"], baseline["integrity"]["n_ok"]),
        "ttft_p50_ms": (
            replay["latency"]["ttft_ms"]["p50"],
            baseline["latency"]["ttft_ms"]["p50"],
        ),
        "ttft_p90_ms": (
            replay["latency"]["ttft_ms"]["p90"],
            baseline["latency"]["ttft_ms"]["p90"],
        ),
        "ttft_p99_ms": (
            replay["latency"]["ttft_ms"]["p99"],
            baseline["latency"]["ttft_ms"]["p99"],
        ),
        "ttft_mean_ms": (
            replay["latency"]["ttft_ms"]["mean"],
            baseline["latency"]["ttft_ms"]["mean"],
        ),
        "token_weighted_hit": (
            replay["kv"]["token_weighted_hit"],
            baseline["kv"]["token_weighted_hit"],
        ),
        "req_per_s": (
            replay["throughput"]["req_per_s"],
            baseline["throughput"]["req_per_s"],
        ),
    }
    return {
        "baseline_input": str(baseline_path),
        "metrics": {
            key: {"diagnostic": current, "baseline": base, "delta": current - base}
            for key, (current, base) in metrics.items()
        },
    }


def write_report(summary: dict[str, Any], path: Path):
    ratios, tokens = summary["ratios"], summary["tokens"]
    reuse, replay = summary["eviction_reuse"], summary.get("replay_summary")
    comparison, plots = summary.get("baseline_comparison"), summary.get("plots") or {}

    def percent(value: float | None) -> str:
        return "n/a" if value is None else f"{value * 100:.2f}%"

    def number(value: float | None, digits: int = 2) -> str:
        return "n/a" if value is None else f"{value:.{digits}f}"

    requests_with_eviction = sum(
        row["requests_with_eviction_miss"] for row in summary["request_quarters"]
    )
    lines = [
        "# GLM KV diagnostic experiment report",
        "",
        "## Summary",
        "",
        f"- successful replay requests: **{replay['integrity']['n_ok'] if replay else summary['requests']} / {replay['integrity']['n_issued'] if replay else summary['requests']}**",
        f"- client token-weighted hit ratio: **{percent(replay['kv']['token_weighted_hit']) if replay else 'n/a'}**",
        f"- page-aligned diagnostic hit ratio: **{percent(ratios['observed_hit_ratio'])}**",
        f"- eviction miss: **{tokens.get('eviction_miss_tokens', 0):,} tokens**, **{percent(ratios['eviction_regret_ratio'])} of all miss tokens**",
        f"- cold miss: **{tokens.get('cold_miss_tokens', 0):,} tokens**, **{percent(ratios['cold_miss_ratio'])} of all miss tokens**",
        f"- requests with eviction miss: **{requests_with_eviction} / {summary['requests']}**",
        f"- eviction reuse time p50 / p90: **{number(reuse['time_ms_p50'] / 1000 if reuse['time_ms_p50'] is not None else None)} / {number(reuse['time_ms_p90'] / 1000 if reuse['time_ms_p90'] is not None else None)} s**",
        f"- reuse request distance p50 / p90: **{number(reuse['request_distance_p50'])} / {number(reuse['request_distance_p90'])}**",
        f"- inserted-token distance p50 / p90: **{number(reuse['inserted_token_distance_p50'])} / {number(reuse['inserted_token_distance_p90'])}**",
        "",
    ]
    if replay:
        lat = replay["latency"]
        lines += [
            "## Replay quality",
            "",
            f"- wall clock: **{replay['integrity']['wall_clock_s']} s**; errors: **{replay['integrity']['n_err']}**",
            "",
            "| latency | p50 (ms) | p90 (ms) | p99 (ms) | mean (ms) |",
            "|---|---:|---:|---:|---:|",
            f"| TTFT | {number(lat['ttft_ms']['p50'])} | {number(lat['ttft_ms']['p90'])} | {number(lat['ttft_ms']['p99'])} | {number(lat['ttft_ms']['mean'])} |",
            f"| TPOT | {number(lat['tpot_ms']['p50'])} | {number(lat['tpot_ms']['p90'])} | {number(lat['tpot_ms']['p99'])} | {number(lat['tpot_ms']['mean'])} |",
            f"| E2E | {number(lat['e2e_ms']['p50'])} | {number(lat['e2e_ms']['p90'])} | {number(lat['e2e_ms']['p99'])} | {number(lat['e2e_ms']['mean'])} |",
            "",
            f"- client cached / prompt tokens: **{replay['kv']['cached_tokens_sum']:,} / {replay['kv']['prompt_tokens_sum']:,}**",
            f"- scheduling drift p50 / p90: **{number(replay['schedule']['s_time_drift_ms']['p50'])} / {number(replay['schedule']['s_time_drift_ms']['p90'])} ms**",
            f"- throughput: **{number(replay['throughput']['req_per_s'], 4)} req/s**, **{number(replay['throughput']['output_tok_per_s'], 4)} output tok/s**",
            "",
        ]
    if comparison:
        lines += [
            "## Native baseline comparison",
            "",
            f"Baseline: {comparison['baseline_input']}",
            "",
            "| metric | diagnostic | native baseline | delta |",
            "|---|---:|---:|---:|",
        ]
        for key, values in comparison["metrics"].items():
            lines.append(
                f"| {key} | {number(values['diagnostic'], 6)} | {number(values['baseline'], 6)} | {number(values['delta'], 6)} |"
            )
        lines.append("")
    lines += [
        "## Miss attribution",
        "",
        "| miss class | tokens | share of miss |",
        "|---|---:|---:|",
        f"| cold | {tokens.get('cold_miss_tokens', 0):,} | {percent(ratios['cold_miss_ratio'])} |",
        f"| eviction | {tokens.get('eviction_miss_tokens', 0):,} | {percent(ratios['eviction_regret_ratio'])} |",
        f"| other | {tokens.get('other_miss_tokens', 0):,} | {percent(ratios['other_miss_ratio'])} |",
        "",
        f"![Cold and eviction miss timeline]({plots.get('miss_timeline', '')})",
        "",
        "| quarter | request range | cold tokens | eviction tokens | eviction share of miss | requests with eviction |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["request_quarters"]:
        lines.append(
            f"| Q{row['quarter']} | {row['request_start']}-{row['request_end']} | {row['cold_miss_tokens']:,} | {row['eviction_miss_tokens']:,} | {percent(row['eviction_share_of_miss'])} | {row['requests_with_eviction_miss']} / {row['requests']} |"
        )
    lines += [
        "",
        "## Eviction reuse distributions",
        "",
        f"- page observations: **{reuse['page_observations']:,}**",
        f"- time p50 / p90: **{number(reuse['time_ms_p50'] / 1000 if reuse['time_ms_p50'] is not None else None)} / {number(reuse['time_ms_p90'] / 1000 if reuse['time_ms_p90'] is not None else None)} s**",
        f"- request distance p50 / p90: **{number(reuse['request_distance_p50'])} / {number(reuse['request_distance_p90'])}**",
        f"- inserted-token distance p50 / p90: **{number(reuse['inserted_token_distance_p50'])} / {number(reuse['inserted_token_distance_p90'])} tokens**",
        "",
        f"![Eviction reuse time CDF]({plots.get('reuse_time_cdf', '')})",
        "",
        f"![Reuse request distance CDF]({plots.get('request_distance_cdf', '')})",
        "",
        f"![Inserted-token distance CDF]({plots.get('inserted_token_distance_cdf', '')})",
        "",
        "## Latency relationship",
        "",
        f"- TTFT vs eviction-miss-token correlation: **{number((summary.get('request_result_join') or {}).get('correlations', {}).get('ttft_vs_eviction_miss_tokens'), 4)}**",
        f"- TTFT vs total-miss-token correlation: **{number((summary.get('request_result_join') or {}).get('correlations', {}).get('ttft_vs_total_miss_tokens'), 4)}**",
        "",
        f"![TTFT versus miss tokens]({plots.get('ttft_vs_miss', '')})",
        "",
        "## Diagnostics integrity",
        "",
        f"- selected PID: **{summary['selected_pid']}**",
        f"- unique / raw request rows: **{summary['requests']} / {summary['request_rows']['raw']}**",
        f"- ignored rematches / non-target rows: **{summary['request_rows']['rematch_rows']} / {summary['request_rows']['non_target_request_rows']}**",
        f"- request-result join: **{(summary.get('request_result_join') or {}).get('matched', 0)} matched**",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output-prefix", type=Path)
    parser.add_argument(
        "--request-results",
        type=Path,
        help="Replay JSONL used to join eviction regret with TTFT by trace_id.",
    )
    parser.add_argument(
        "--replay-summary",
        type=Path,
        help="Replay summary JSON included in the unified experiment report.",
    )
    parser.add_argument(
        "--baseline-summary",
        type=Path,
        help="Optional native replay summary used for a comparison table.",
    )
    parser.add_argument(
        "--pid",
        type=int,
        help="Analyze one explicit PID instead of auto-selecting by trace_id coverage.",
    )
    args = parser.parse_args()
    prefix = args.output_prefix or args.trace.with_suffix("")
    results = load_request_results(args.request_results) if args.request_results else {}
    target_request_ids = set(results) if args.request_results is not None else None
    selected_pid, candidates = select_process(args.trace, target_request_ids, args.pid)
    summary, requests, plot_data = analyze(args.trace, selected_pid, target_request_ids)
    summary["process_selection"] = {
        "strategy": "explicit_pid" if args.pid is not None else "trace_id_coverage",
        "candidates": candidates,
    }

    if args.request_results:
        for request in requests:
            result = results.get(request["request_id"])
            if result is None:
                continue
            request["ttft_ms"] = result.get("ttft_ms")
            request["e2e_ms"] = result.get("e2e_ms")
            request["status"] = result.get("status")
            request["s_time_ms"] = result.get("s_time_ms")
            request["cached_tokens"] = result.get("cached_tokens")

        matched_request_ids = {
            row["request_id"] for row in requests if row["request_id"] in results
        }
        summary["request_result_join"] = {
            "input": str(args.request_results),
            "result_requests": len(results),
            "matched": len(matched_request_ids),
            "unmatched_trace_requests": len(requests) - len(matched_request_ids),
            "unmatched_result_requests": len(set(results) - matched_request_ids),
            "correlations": {
                "ttft_vs_eviction_miss_tokens": pearson(
                    [
                        (row["eviction_miss_tokens"], row["ttft_ms"])
                        for row in requests
                        if row.get("ttft_ms") is not None
                    ]
                ),
                "ttft_vs_total_miss_tokens": pearson(
                    [
                        (
                            row["cold_miss_tokens"]
                            + row["eviction_miss_tokens"]
                            + row["other_miss_tokens"],
                            row["ttft_ms"],
                        )
                        for row in requests
                        if row.get("ttft_ms") is not None
                    ]
                ),
            },
        }

    replay_summary_path = args.replay_summary or Path(f"{prefix}.summary.json")
    replay_summary = (
        json.loads(replay_summary_path.read_text(encoding="utf-8"))
        if replay_summary_path.exists()
        else None
    )
    baseline_summary = (
        json.loads(args.baseline_summary.read_text(encoding="utf-8"))
        if args.baseline_summary
        else None
    )
    summary["replay_summary_input"] = (
        str(replay_summary_path) if replay_summary is not None else None
    )
    summary["replay_summary"] = replay_summary
    summary["baseline_comparison"] = build_baseline_comparison(
        replay_summary, baseline_summary, args.baseline_summary
    )
    summary["timeline"] = build_timeline(requests)
    summary["request_quarters"] = build_request_quarters(requests)
    summary["plots"] = create_plots(summary, requests, plot_data, prefix)

    summary_path = Path(f"{prefix}.regret.summary.json")
    requests_path = Path(f"{prefix}.regret.requests.jsonl")
    report_path = Path(f"{prefix}_report.md")
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with requests_path.open("w", encoding="utf-8") as f:
        for row in requests:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_report(summary, report_path)
    print(report_path)


if __name__ == "__main__":
    main()
