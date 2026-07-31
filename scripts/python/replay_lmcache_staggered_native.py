#!/usr/bin/env python3
"""Staggered multi-session replay against *native* SGLang.

Philosophy: docs/47_realistic_workload_construction_philosophy.md

- Content + intra-session gaps: lmcache_traces (input + pre_gap)
- Cross-session arrival: fixed stagger t_start(i) = i * delta_s
- Native chat path only (no session/priority extras)

Example:
  bash scripts/shell/replay_staggered_native.sh
  # or with overrides:
  bash scripts/shell/replay_staggered_native.sh --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests
from datasets import load_from_disk
from openai import AsyncOpenAI

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_DIR = REPO_ROOT / "experiments/vllm_kv_cache/lmcache_traces"
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "experiments/sglang_kv_cache/staggered_native_replay"
)


@dataclass
class Turn:
    messages: list[dict[str, Any]]
    output_length: int
    pre_gap: float


@dataclass
class RequestRecord:
    session_id: str
    session_index: int
    turn_index: int
    t_start_target_s: float
    pre_gap_s: float
    sleep_before_s: float
    wall_issue_s: float
    ttft_ms: float | None
    e2e_ms: float | None
    prompt_tokens: int | None
    cached_tokens: int | None
    completion_tokens: int | None
    max_tokens: int
    error: str | None = None


@dataclass
class SessionResult:
    session_id: str
    session_index: int
    t_start_s: float
    n_turns_planned: int
    n_turns_done: int
    requests: list[RequestRecord] = field(default_factory=list)


def messages_to_openai_format(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten tool payloads into plain chat messages (native chat path)."""
    openai_msgs: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "") or ""
        tool_calls = msg.get("tool_calls") or []
        tool_call_id = msg.get("tool_call_id", "")
        name = msg.get("name", "")

        if role == "assistant" and tool_calls:
            if content:
                openai_msgs.append({"role": "assistant", "content": content})
            else:
                tc_names = [
                    (tc.get("function") or {}).get("name", "unknown")
                    for tc in tool_calls
                ]
                openai_msgs.append(
                    {
                        "role": "assistant",
                        "content": f"[Called tools: {', '.join(tc_names)}]",
                    }
                )
        elif role == "tool":
            tool_content = content if content else "[tool result]"
            # Keep more of the tool body for prefix realism; cap extreme tails.
            openai_msgs.append(
                {
                    "role": "user",
                    "content": (
                        f"[Tool result from {name or tool_call_id}]: "
                        f"{tool_content[:8000]}"
                    ),
                }
            )
        elif content:
            openai_msgs.append({"role": role, "content": content})
    return openai_msgs


def list_all_session_ids(trace_dir: Path) -> list[str]:
    """Return session_ids in first-seen order (stable / reproducible)."""
    ds = load_from_disk(str(trace_dir))
    ordered: list[str] = []
    seen: set[str] = set()
    for i in range(len(ds)):
        sid = ds["session_id"][i]
        if not sid or sid in seen:
            continue
        seen.add(sid)
        ordered.append(sid)
    if not ordered:
        raise ValueError(f"No sessions found in {trace_dir}")
    return ordered


def load_sessions(
    trace_dir: Path,
    session_ids: list[str],
    max_turns: int | None,
) -> dict[str, list[Turn]]:
    wanted = set(session_ids)
    buckets: dict[str, list[Turn]] = defaultdict(list)

    ds = load_from_disk(str(trace_dir))
    for i in range(len(ds)):
        sid = ds["session_id"][i]
        if sid not in wanted:
            continue
        buckets[sid].append(
            Turn(
                messages=ds["input"][i],
                output_length=int(ds["output_length"][i]),
                pre_gap=float(ds["pre_gap"][i]),
            )
        )

    missing = [sid for sid in session_ids if sid not in buckets]
    if missing:
        raise ValueError(f"Sessions not found in {trace_dir}: {missing}")

    out: dict[str, list[Turn]] = {}
    for sid in session_ids:
        turns = buckets[sid]
        if max_turns is not None:
            turns = turns[:max_turns]
        if not turns:
            raise ValueError(f"Session has no turns: {sid}")
        out[sid] = turns
    return out


def health_check(base_url: str, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            resp = requests.get(f"{base_url}/health", timeout=5)
            if resp.status_code == 200:
                return
            last_err = RuntimeError(f"health HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(1.0)
    raise RuntimeError(f"Server not healthy at {base_url}: {last_err}")


def maybe_flush_cache(base_url: str, enabled: bool) -> None:
    if not enabled:
        return
    resp = requests.post(f"{base_url}/flush_cache", timeout=60)
    resp.raise_for_status()


async def measure_chat(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    first_token_at: float | None = None
    prompt_tokens = 0
    cached_tokens = 0
    completion_tokens = 0

    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.0,
        stream=True,
        stream_options={"include_usage": True},
        timeout=600.0,
    )
    async for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and (delta.content or getattr(delta, "tool_calls", None)):
                if first_token_at is None:
                    first_token_at = time.perf_counter()
        if chunk.usage is not None:
            prompt_tokens = int(chunk.usage.prompt_tokens or 0)
            completion_tokens = int(chunk.usage.completion_tokens or 0)
            details = getattr(chunk.usage, "prompt_tokens_details", None)
            if details is not None:
                cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)

    ended = time.perf_counter()
    return {
        "ttft_ms": (
            None
            if first_token_at is None
            else round((first_token_at - started) * 1000.0, 3)
        ),
        "e2e_ms": round((ended - started) * 1000.0, 3),
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": completion_tokens,
    }


async def run_session(
    *,
    client: AsyncOpenAI | None,
    model: str,
    session_id: str,
    session_index: int,
    turns: list[Turn],
    t0_mono: float,
    t_start_s: float,
    gap_scale: float,
    ablate_zero_gap: bool,
    max_tokens_cap: int | None,
    use_trace_output_length: bool,
    dry_run: bool,
) -> SessionResult:
    result = SessionResult(
        session_id=session_id,
        session_index=session_index,
        t_start_s=t_start_s,
        n_turns_planned=len(turns),
        n_turns_done=0,
    )

    # Wait until absolute staggered start (skip real waits in dry-run).
    delay = t_start_s - (time.monotonic() - t0_mono)
    if delay > 0 and not dry_run:
        await asyncio.sleep(delay)

    for turn_index, turn in enumerate(turns):
        raw_gap = 0.0 if ablate_zero_gap else float(turn.pre_gap)
        sleep_before = 0.0 if turn_index == 0 else max(0.0, raw_gap * gap_scale)
        if turn_index > 0 and sleep_before > 0 and not dry_run:
            await asyncio.sleep(sleep_before)

        if use_trace_output_length:
            max_tokens = max(1, int(turn.output_length))
            if max_tokens_cap is not None:
                max_tokens = min(max_tokens, max_tokens_cap)
        else:
            if max_tokens_cap is None:
                raise ValueError(
                    "Need --max-tokens-cap when --use-trace-output-length is off"
                )
            max_tokens = max(1, int(max_tokens_cap))

        wall_issue = time.monotonic() - t0_mono
        api_messages = messages_to_openai_format(turn.messages)

        rec = RequestRecord(
            session_id=session_id,
            session_index=session_index,
            turn_index=turn_index,
            t_start_target_s=t_start_s if turn_index == 0 else -1.0,
            pre_gap_s=raw_gap,
            sleep_before_s=round(sleep_before, 6),
            wall_issue_s=round(wall_issue, 6),
            ttft_ms=None,
            e2e_ms=None,
            prompt_tokens=None,
            cached_tokens=None,
            completion_tokens=None,
            max_tokens=max_tokens,
        )

        if dry_run:
            print(
                f"[dry-run] s{session_index} turn{turn_index} "
                f"wall={wall_issue:.3f}s sleep_before={sleep_before:.3f}s "
                f"max_tokens={max_tokens} msgs={len(api_messages)}",
                flush=True,
            )
        else:
            assert client is not None
            try:
                metrics = await measure_chat(
                    client, model, api_messages, max_tokens
                )
                rec.ttft_ms = metrics["ttft_ms"]
                rec.e2e_ms = metrics["e2e_ms"]
                rec.prompt_tokens = metrics["prompt_tokens"]
                rec.cached_tokens = metrics["cached_tokens"]
                rec.completion_tokens = metrics["completion_tokens"]
                print(
                    f"[ok] s{session_index}/{session_id[-24:]} turn{turn_index} "
                    f"ttft={rec.ttft_ms}ms cached={rec.cached_tokens}/"
                    f"{rec.prompt_tokens} e2e={rec.e2e_ms}ms",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                rec.error = f"{type(exc).__name__}: {exc}"
                print(
                    f"[err] s{session_index} turn{turn_index} {rec.error}",
                    flush=True,
                )
                result.requests.append(rec)
                break

        result.requests.append(rec)
        result.n_turns_done += 1

    return result


def percentile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    ordered = sorted(xs)
    return round(ordered[int(round((len(ordered) - 1) * q))], 3)


def mean(xs: list[float]) -> float | None:
    if not xs:
        return None
    return round(sum(xs) / len(xs), 3)


def hit_rate(cached: int | None, prompt: int | None) -> float | None:
    if not prompt:
        return None
    return round((cached or 0) / prompt, 6)


def ttft_block(reqs: list[RequestRecord]) -> dict[str, Any]:
    ttfts = [r.ttft_ms for r in reqs if r.ttft_ms is not None]
    return {
        "count": len(ttfts),
        "p50": percentile(ttfts, 0.5),
        "p90": percentile(ttfts, 0.9),
        "mean": mean(ttfts),
        "max": round(max(ttfts), 3) if ttfts else None,
    }


def hit_block(reqs: list[RequestRecord]) -> dict[str, Any]:
    cached = [r.cached_tokens or 0 for r in reqs]
    prompts = [r.prompt_tokens or 0 for r in reqs]
    rates = [
        (r.cached_tokens or 0) / r.prompt_tokens
        for r in reqs
        if r.prompt_tokens and r.prompt_tokens > 0
    ]
    prompt_sum = int(sum(prompts))
    cached_sum = int(sum(cached))
    return {
        "cached_tokens_sum": cached_sum,
        "prompt_tokens_sum": prompt_sum,
        "token_weighted_cache_hit": (
            round(cached_sum / prompt_sum, 6) if prompt_sum else None
        ),
        "per_req_hit_rate": {
            "p50": percentile(rates, 0.5),
            "p90": percentile(rates, 0.9),
            "mean": mean(rates),
        },
        "cold_miss_rate": (
            round(
                sum(1 for r in reqs if (r.cached_tokens or 0) == 0) / len(reqs),
                6,
            )
            if reqs
            else None
        ),
    }


def slo_block(reqs: list[RequestRecord]) -> dict[str, Any]:
    ttfts = [r.ttft_ms for r in reqs if r.ttft_ms is not None]
    out: dict[str, Any] = {}
    for thr in (100, 200, 500):
        key = f"slo_violation_rate@{thr}ms"
        if not ttfts:
            out[key] = None
        else:
            out[key] = round(sum(1 for t in ttfts if t > thr) / len(ttfts), 6)
    return out


def classify_error(err: str) -> str:
    low = err.lower()
    if "longer than the model's" in low or "context" in low and "long" in low:
        return "context_too_long"
    if "connection" in low:
        return "connection"
    if "timeout" in low:
        return "timeout"
    if "400" in low or "badrequest" in low:
        return "bad_request"
    return "other"


def compute_metrics(
    results: list[SessionResult],
    *,
    wall_clock_s: float,
) -> dict[str, Any]:
    all_reqs = [r for s in results for r in s.requests]
    ok = [r for r in all_reqs if r.error is None]
    err = [r for r in all_reqs if r.error is not None]
    start_ok = [r for r in ok if r.turn_index == 0]
    within_ok = [r for r in ok if r.turn_index >= 1]

    err_breakdown: dict[str, int] = {}
    for r in err:
        key = classify_error(r.error or "")
        err_breakdown[key] = err_breakdown.get(key, 0) + 1

    start_ttft = ttft_block(start_ok)
    within_ttft = ttft_block(within_ok)
    speedup = None
    if (
        start_ttft["p50"] is not None
        and within_ttft["p50"] is not None
        and within_ttft["p50"] > 0
    ):
        speedup = round(start_ttft["p50"] / within_ttft["p50"], 3)

    e2es = [r.e2e_ms for r in ok if r.e2e_ms is not None]
    completions = [r.completion_tokens or 0 for r in ok]
    global_hit = hit_block(ok)

    jitters: list[float] = []
    per_session: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    for s in results:
        s_ok = [r for r in s.requests if r.error is None]
        s_err = [r for r in s.requests if r.error is not None]
        turn0 = next((r for r in s.requests if r.turn_index == 0), None)
        first_wall = min((r.wall_issue_s for r in s.requests), default=None)
        last_wall = max(
            (
                r.wall_issue_s + ((r.e2e_ms or 0) / 1000.0)
                for r in s_ok
            ),
            default=first_wall,
        )
        jitter_ms = None
        if turn0 is not None and turn0.t_start_target_s >= 0:
            jitter_ms = round(
                (turn0.wall_issue_s - turn0.t_start_target_s) * 1000.0, 3
            )
            jitters.append(jitter_ms)
        turn0_hit = None
        if turn0 and turn0.error is None:
            turn0_hit = hit_rate(turn0.cached_tokens, turn0.prompt_tokens)
        per_session.append(
            {
                "session_id": s.session_id,
                "session_index": s.session_index,
                "t_start_s": s.t_start_s,
                "n_turns_planned": s.n_turns_planned,
                "n_turns_done": s.n_turns_done,
                "n_ok": len(s_ok),
                "n_err": len(s_err),
                "turn0_wall_issue_s": turn0.wall_issue_s if turn0 else None,
                "turn0_ttft_ms": (
                    turn0.ttft_ms if turn0 and turn0.error is None else None
                ),
                "turn0_cached_tokens": (
                    turn0.cached_tokens if turn0 and turn0.error is None else None
                ),
                "turn0_prompt_tokens": (
                    turn0.prompt_tokens if turn0 and turn0.error is None else None
                ),
                "turn0_hit_rate": turn0_hit,
                "start_jitter_ms": jitter_ms,
                "wall_window_s": (
                    {"first": first_wall, "last": last_wall}
                    if first_wall is not None
                    else None
                ),
            }
        )
        if first_wall is not None:
            windows.append(
                {
                    "session_index": s.session_index,
                    "session_id": s.session_id,
                    "first": first_wall,
                    "last": last_wall,
                }
            )

    return {
        "integrity": {
            "n_sessions": len(results),
            "n_turns_planned": sum(s.n_turns_planned for s in results),
            "n_requests_ok": len(ok),
            "n_requests_err": len(err),
            "error_breakdown": err_breakdown,
            "wall_clock_s": round(wall_clock_s, 3),
        },
        "session_start": {
            **{"ttft_ms": start_ttft},
            **hit_block(start_ok),
            **slo_block(start_ok),
        },
        "within_session": {
            **{"ttft_ms": within_ttft},
            **hit_block(within_ok),
            **slo_block(within_ok),
            "ttft_speedup_vs_session_start": speedup,
        },
        "global": {
            **{"ttft_ms": ttft_block(ok)},
            **global_hit,
            "e2e_ms": {
                "p50": percentile(e2es, 0.5),
                "p90": percentile(e2es, 0.9),
                "mean": mean(e2es),
            },
            "completion_tokens_sum": int(sum(completions)),
            "avoided_prefill_tokens": global_hit["cached_tokens_sum"],
        },
        "schedule": {
            "start_jitter_ms": {
                "p50": percentile(jitters, 0.5),
                "p90": percentile(jitters, 0.9),
                "mean": mean(jitters),
                "max": round(max(jitters), 3) if jitters else None,
            },
            "overlap_hint": windows,
            "per_session": per_session,
        },
        "errors": [
            {
                "session_id": r.session_id,
                "session_index": r.session_index,
                "turn_index": r.turn_index,
                "class": classify_error(r.error or ""),
                "error": r.error,
            }
            for r in err
        ],
    }


def compact_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    """Short board for terminal / backwards-compatible `summary` field."""
    integ = metrics["integrity"]
    start = metrics["session_start"]
    within = metrics["within_session"]
    glob = metrics["global"]
    return {
        "n_sessions": integ["n_sessions"],
        "n_requests_ok": integ["n_requests_ok"],
        "n_requests_err": integ["n_requests_err"],
        "error_breakdown": integ["error_breakdown"],
        "wall_clock_s": integ["wall_clock_s"],
        "session_start_ttft_ms_p50": start["ttft_ms"]["p50"],
        "session_start_hit": start["token_weighted_cache_hit"],
        "within_ttft_ms_p50": within["ttft_ms"]["p50"],
        "within_hit": within["token_weighted_cache_hit"],
        "ttft_speedup_vs_session_start": within["ttft_speedup_vs_session_start"],
        "global_ttft_ms": glob["ttft_ms"],
        "token_weighted_cache_hit": glob["token_weighted_cache_hit"],
        "per_req_hit_rate_p50": glob["per_req_hit_rate"]["p50"],
        "slo_violation_rate@500ms_session_start": start.get(
            "slo_violation_rate@500ms"
        ),
    }


def summarize(results: list[SessionResult]) -> dict[str, Any]:
    """Back-compat thin wrapper; prefer compute_metrics."""
    return compact_summary(
        compute_metrics(results, wall_clock_s=0.0)
    )


async def async_main(args: argparse.Namespace) -> int:
    trace_dir = Path(args.trace_dir)
    if not trace_dir.is_absolute():
        trace_dir = REPO_ROOT / trace_dir

    session_ids: list[str] = list(args.session_id)
    if args.all_sessions:
        session_ids = list_all_session_ids(trace_dir)
        print(f"Discovered {len(session_ids)} sessions (first-seen order)", flush=True)
    elif not session_ids:
        raise SystemExit("Need --all-sessions or at least one --session-id")

    delta_s = float(args.delta_s)
    gap_scale = float(args.gap_scale)
    ablate_zero_gap = bool(args.ablate_zero_gap)
    max_turns = args.max_turns
    max_tokens_cap = args.max_tokens_cap
    use_trace_output_length = bool(args.use_trace_output_length)
    flush_before = bool(args.flush_cache)
    model = args.model or "default"

    sessions = load_sessions(trace_dir, session_ids, max_turns)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    n_turns = sum(len(t) for t in sessions.values())
    run_cfg = {
        "session_ids": session_ids,
        "all_sessions": bool(args.all_sessions),
        "n_sessions": len(session_ids),
        "n_turns_total": n_turns,
        "arrival": {"type": "staggered", "delta_s": delta_s},
        "gap_scale": gap_scale,
        "ablate_zero_gap": ablate_zero_gap,
        "max_turns": max_turns,
        "max_tokens_cap": max_tokens_cap,
        "use_trace_output_length": use_trace_output_length,
        "flush_cache_before_run": flush_before,
        "trace_dir": str(trace_dir),
        "model": model,
    }

    print(
        f"Loaded {len(sessions)} sessions / {n_turns} turns from {trace_dir}; "
        f"delta_s={delta_s} gap_scale={gap_scale} "
        f"max_turns={max_turns} max_tokens_cap={max_tokens_cap} "
        f"use_trace_output_length={use_trace_output_length} "
        f"ablate_zero_gap={ablate_zero_gap} dry_run={args.dry_run}",
        flush=True,
    )
    # Avoid flooding stdout on full corpus; print head/tail only.
    show = session_ids if len(session_ids) <= 20 else session_ids[:10] + session_ids[-5:]
    shown: set[str] = set()
    for i, sid in enumerate(session_ids):
        if sid not in show:
            if i == 10 and len(session_ids) > 20:
                print(f"  ... ({len(session_ids) - 15} sessions omitted) ...", flush=True)
            continue
        if sid in shown:
            continue
        shown.add(sid)
        print(
            f"  [{i}] t_start={i * delta_s:.3f}s  turns={len(sessions[sid])}  {sid}",
            flush=True,
        )

    client: AsyncOpenAI | None = None
    if not args.dry_run:
        health_check(args.base_url)
        maybe_flush_cache(args.base_url, flush_before)
        client = AsyncOpenAI(
            base_url=f"{args.base_url.rstrip('/')}/v1",
            api_key="EMPTY",
            timeout=600.0,
        )

    t0 = time.monotonic()
    wall_start = time.time()
    tasks = [
        run_session(
            client=client,
            model=model,
            session_id=sid,
            session_index=i,
            turns=sessions[sid],
            t0_mono=t0,
            t_start_s=i * delta_s,
            gap_scale=gap_scale,
            ablate_zero_gap=ablate_zero_gap,
            max_tokens_cap=max_tokens_cap,
            use_trace_output_length=use_trace_output_length,
            dry_run=args.dry_run,
        )
        for i, sid in enumerate(session_ids)
    ]
    results = await asyncio.gather(*tasks)
    wall_s = time.time() - wall_start

    metrics = compute_metrics(list(results), wall_clock_s=wall_s)
    summary = compact_summary(metrics)

    payload = {
        "created_unix": time.time(),
        "docs_ref": "docs/真实数据构造.md",
        "mode": "native_sglang_staggered",
        "dry_run": args.dry_run,
        "base_url": args.base_url,
        "model": model,
        "config": run_cfg,
        "arrival": {"type": "staggered", "delta_s": delta_s},
        "gap_scale": gap_scale,
        "ablate_zero_gap": ablate_zero_gap,
        "wall_clock_s": round(wall_s, 3),
        "summary": summary,
        "metrics": metrics,
        "sessions": [
            {
                **{k: v for k, v in asdict(s).items() if k != "requests"},
                "requests": [asdict(r) for r in s.requests],
            }
            for s in results
        ],
    }

    out_path = output_dir / args.output_name
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {out_path}", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8004")
    p.add_argument("--model", default=None)
    p.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-name", default="run_staggered_full.json")
    p.add_argument(
        "--session-id",
        action="append",
        default=[],
        help="Session to replay; repeat for multiple (order = stagger order)",
    )
    p.add_argument(
        "--all-sessions",
        action="store_true",
        help="Replay every session in trace_dir (first-seen order)",
    )
    p.add_argument("--delta-s", type=float, default=2.0)
    p.add_argument("--gap-scale", type=float, default=1.0)
    p.add_argument("--ablate-zero-gap", action="store_true")
    p.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Cap turns per session; default = all turns",
    )
    p.add_argument(
        "--max-tokens-cap",
        type=int,
        default=None,
        help="Cap completion tokens; default = no cap (use trace lengths if enabled)",
    )
    p.add_argument(
        "--use-trace-output-length",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use per-turn output_length from trace (default on)",
    )
    p.add_argument(
        "--flush-cache",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only schedule sleeps / print plan; do not call the server",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
