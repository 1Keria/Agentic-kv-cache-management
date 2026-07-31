#!/usr/bin/env python3
"""Render a staggered-replay result JSON into a readable metrics report.

Reads docs/39 §6.4 + docs/42 §7 oriented fields from `metrics` (or rebuilds
them from `sessions` if an older JSON lacks `metrics`).

Examples:
  python3 scripts/python/report_staggered_replay.py \\
    --input experiments/sglang_kv_cache/staggered_native_replay/latest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    REPO_ROOT
    / "experiments/sglang_kv_cache/staggered_native_replay/latest.json"
)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_lmcache_staggered_native import (  # noqa: E402
    RequestRecord,
    SessionResult,
    compute_metrics,
)


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if abs(v) >= 100 or v == 0:
            return f"{v:.3f}"
        return f"{v:.4f}"
    return str(v)


def _pct(v: Any) -> str:
    if v is None:
        return "—"
    return f"{100.0 * float(v):.2f}%"


def rebuild_metrics(payload: dict[str, Any], shadow_path: Path | None = None) -> dict[str, Any]:
    if "metrics" in payload and payload["metrics"]:
        return payload["metrics"]

    results: list[SessionResult] = []
    for s in payload.get("sessions") or []:
        reqs = []
        for r in s.get("requests") or []:
            reqs.append(
                RequestRecord(
                    session_id=r["session_id"],
                    session_index=r["session_index"],
                    turn_index=r["turn_index"],
                    t_start_target_s=float(r.get("t_start_target_s", -1)),
                    pre_gap_s=float(r.get("pre_gap_s", 0)),
                    sleep_before_s=float(r.get("sleep_before_s", 0)),
                    wall_issue_s=float(r.get("wall_issue_s", 0)),
                    ttft_ms=r.get("ttft_ms"),
                    e2e_ms=r.get("e2e_ms"),
                    prompt_tokens=r.get("prompt_tokens"),
                    cached_tokens=r.get("cached_tokens"),
                    completion_tokens=r.get("completion_tokens"),
                    max_tokens=int(r.get("max_tokens") or 0),
                    error=r.get("error"),
                )
            )
        results.append(
            SessionResult(
                session_id=s["session_id"],
                session_index=s["session_index"],
                t_start_s=float(s.get("t_start_s", 0)),
                n_turns_planned=int(s.get("n_turns_planned", len(reqs))),
                n_turns_done=int(s.get("n_turns_done", 0)),
                requests=reqs,
            )
        )
    wall = float(payload.get("wall_clock_s") or 0)
    return compute_metrics(results, wall_clock_s=wall)


def render_markdown(payload: dict[str, Any], metrics: dict[str, Any]) -> str:
    integ = metrics["integrity"]
    start = metrics["session_start"]
    within = metrics["within_session"]
    glob = metrics["global"]
    sched = metrics["schedule"]
    lines: list[str] = []

    lines.append("# Staggered replay report")
    lines.append("")
    lines.append(f"- model: `{payload.get('model')}`")
    lines.append(f"- base_url: `{payload.get('base_url')}`")
    lines.append(f"- mode: `{payload.get('mode')}`")
    lines.append(f"- dry_run: `{payload.get('dry_run')}`")
    lines.append(f"- wall_clock_s: **{_fmt(integ['wall_clock_s'])}**")
    lines.append("")

    lines.append("## A. Integrity")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| n_sessions | {integ['n_sessions']} |")
    lines.append(f"| n_turns_planned | {integ['n_turns_planned']} |")
    lines.append(f"| n_requests_ok | {integ['n_requests_ok']} |")
    lines.append(f"| n_requests_err | {integ['n_requests_err']} |")
    lines.append(
        f"| error_breakdown | `{json.dumps(integ['error_breakdown'], ensure_ascii=False)}` |"
    )
    lines.append("")

    lines.append("## B. Session-start (turn0, primary)")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| ttft p50 / p90 / mean / max (ms) | {_fmt(start['ttft_ms']['p50'])} / {_fmt(start['ttft_ms']['p90'])} / {_fmt(start['ttft_ms']['mean'])} / {_fmt(start['ttft_ms']['max'])} |")
    lines.append(f"| token_weighted_cache_hit | {_pct(start['token_weighted_cache_hit'])} |")
    lines.append(f"| per_req_hit_rate p50 | {_pct(start['per_req_hit_rate']['p50'])} |")
    lines.append(f"| cold_miss_rate | {_pct(start['cold_miss_rate'])} |")
    lines.append(f"| SLO violation @100ms | {_pct(start.get('slo_violation_rate@100ms'))} |")
    lines.append(f"| SLO violation @200ms | {_pct(start.get('slo_violation_rate@200ms'))} |")
    lines.append(f"| SLO violation @500ms | {_pct(start.get('slo_violation_rate@500ms'))} |")
    lines.append(f"| cached / prompt tokens | {start['cached_tokens_sum']} / {start['prompt_tokens_sum']} |")
    lines.append("")

    lines.append("## C. Within-session (turn≥1)")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| ttft p50 / p90 / mean (ms) | {_fmt(within['ttft_ms']['p50'])} / {_fmt(within['ttft_ms']['p90'])} / {_fmt(within['ttft_ms']['mean'])} |")
    lines.append(f"| token_weighted_cache_hit | {_pct(within['token_weighted_cache_hit'])} |")
    lines.append(f"| per_req_hit_rate p50 | {_pct(within['per_req_hit_rate']['p50'])} |")
    lines.append(f"| ttft_speedup_vs_session_start | {_fmt(within['ttft_speedup_vs_session_start'])}× |")
    lines.append(f"| SLO violation @500ms | {_pct(within.get('slo_violation_rate@500ms'))} |")
    lines.append("")

    lines.append("## D. Global (all OK requests)")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| ttft p50 / p90 / mean (ms) | {_fmt(glob['ttft_ms']['p50'])} / {_fmt(glob['ttft_ms']['p90'])} / {_fmt(glob['ttft_ms']['mean'])} |")
    lines.append(f"| e2e p50 / p90 (ms) | {_fmt(glob['e2e_ms']['p50'])} / {_fmt(glob['e2e_ms']['p90'])} |")
    lines.append(f"| token_weighted_cache_hit | {_pct(glob['token_weighted_cache_hit'])} |")
    lines.append(f"| per_req_hit_rate p50 / p90 | {_pct(glob['per_req_hit_rate']['p50'])} / {_pct(glob['per_req_hit_rate']['p90'])} |")
    lines.append(f"| avoided_prefill_tokens | {glob['avoided_prefill_tokens']} |")
    lines.append(f"| completion_tokens_sum | {glob['completion_tokens_sum']} |")
    lines.append("")

    lines.append("## E. Schedule / concurrency")
    lines.append("")
    sj = sched["start_jitter_ms"]
    lines.append(
        f"- start_jitter_ms p50/p90/max: {_fmt(sj['p50'])} / {_fmt(sj['p90'])} / {_fmt(sj['max'])}"
    )
    lines.append("")
    lines.append("| idx | session | t_start | turn0 TTFT | turn0 hit | jitter_ms | ok/err | window |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in sched["per_session"]:
        win = row.get("wall_window_s") or {}
        win_s = (
            f"{_fmt(win.get('first'))}→{_fmt(win.get('last'))}"
            if win
            else "—"
        )
        sid = row["session_id"]
        if len(sid) > 36:
            sid = "…" + sid[-35:]
        lines.append(
            f"| {row['session_index']} | `{sid}` | {_fmt(row['t_start_s'])} | "
            f"{_fmt(row['turn0_ttft_ms'])} | {_pct(row['turn0_hit_rate'])} | "
            f"{_fmt(row['start_jitter_ms'])} | {row['n_ok']}/{row['n_err']} | {win_s} |"
        )
    lines.append("")

    errs = metrics.get("errors") or []
    lines.append("## Errors")
    lines.append("")
    if not errs:
        lines.append("_None._")
    else:
        lines.append("| session | turn | class | error |")
        lines.append("|---|---|---|---|")
        for e in errs:
            msg = (e.get("error") or "").replace("|", "\\|")
            if len(msg) > 120:
                msg = msg[:117] + "..."
            sid = e["session_id"]
            if len(sid) > 28:
                sid = "…" + sid[-27:]
            lines.append(
                f"| `{sid}` | {e['turn_index']} | `{e['class']}` | {msg} |"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Markdown report path (default: <input>_report.md)",
    )
    p.add_argument(
        "--no-stdout",
        action="store_true",
        help="Only write markdown file",
    )
    args = p.parse_args()

    in_path = args.input
    if not in_path.exists():
        # fall back to classic name
        alt = in_path.parent / "run_staggered_4sessions.json"
        if alt.exists():
            in_path = alt
        else:
            raise SystemExit(f"Input not found: {args.input}")

    payload = json.loads(in_path.read_text())
    metrics = rebuild_metrics(payload)
    md = render_markdown(payload, metrics)

    out_path = args.output
    if out_path is None:
        out_path = in_path.with_name(in_path.stem + "_report.md")
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path}", flush=True)
    if not args.no_stdout:
        print(md, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
