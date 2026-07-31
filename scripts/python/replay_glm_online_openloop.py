#!/usr/bin/env python3
"""Open-loop GLM online-trace replay (trace-replayer style).

Mirrors third_party/trace-replayer:
  - schedule at (timestamp - t0) / scale_factor
  - fire without waiting for previous responses
  - stop after --time-in-secs

Docs: docs/V4Flash混合流量实验方案.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = (
    REPO_ROOT
    / "third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla"
)


@dataclass
class EventMeta:
    index: int
    offset: int
    trace_id: str
    start_time_orig: str
    start_epoch_s: float
    completion_tokens: int
    sched_ms: int = 0  # relative wall schedule after normalize / scale


@dataclass
class RequestResult:
    index: int
    trace_id: str
    start_time_orig: str
    t_sched_ms: float
    s_time_ms: float
    s_time_drift_ms: float
    e_time_ms: float | None = None
    ttft_ms: float | None = None
    tpot_ms: float | None = None
    e2e_ms: float | None = None
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    completion_tokens: int | None = None
    max_tokens: int = 0
    cache_hit_ratio: float | None = None
    status: str | None = None
    error: str | None = None


def parse_start_time(s: str) -> datetime:
    return datetime.fromisoformat(s)


def percentile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    if len(ys) == 1:
        return float(ys[0])
    pos = (len(ys) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    frac = pos - lo
    return float(ys[lo] * (1.0 - frac) + ys[hi] * frac)


def sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep OpenAI-compatible fields; drop GLM-only reasoning blobs."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role") or "user"
        item: dict[str, Any] = {"role": role}
        content = msg.get("content")
        if content is None:
            content = ""
        item["content"] = content

        if role == "assistant" and msg.get("tool_calls"):
            tcs = []
            for tc in msg["tool_calls"]:
                fn = tc.get("function") or {}
                tcs.append(
                    {
                        "id": tc.get("id") or f"call_{len(tcs)}",
                        "type": tc.get("type") or "function",
                        "function": {
                            "name": fn.get("name") or "unknown",
                            "arguments": fn.get("arguments") or "{}",
                        },
                    }
                )
            item["tool_calls"] = tcs
            # Some stacks reject null content with tool_calls.
            if not item["content"]:
                item["content"] = ""
        if role == "tool":
            item["tool_call_id"] = msg.get("tool_call_id") or "missing_tool_call_id"
            if msg.get("name"):
                item["name"] = msg["name"]
        out.append(item)
    return out


def flatten_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback path without native tool roles (like lmcache native replay)."""
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
            tc_names = [
                (tc.get("function") or {}).get("name", "unknown") for tc in tool_calls
            ]
            openai_msgs.append(
                {
                    "role": "assistant",
                    "content": f"[Called tools: {', '.join(tc_names)}]",
                }
            )
        elif role == "tool":
            tool_content = content if content else "[tool result]"
            openai_msgs.append(
                {
                    "role": "user",
                    "content": (
                        f"[Tool result from {name or tool_call_id}]: "
                        f"{tool_content[:8000]}"
                    ),
                }
            )
        elif content or role in ("system", "user"):
            openai_msgs.append({"role": role, "content": content})
    return openai_msgs


def load_event_index(path: Path) -> list[EventMeta]:
    """Pass-1: offsets + arrival + completion_tokens (no prompt bodies)."""
    events: list[EventMeta] = []
    with path.open("rb") as f:
        while True:
            offset = f.tell()
            raw = f.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                rb = row["response_body"]
                if isinstance(rb, str):
                    rb = json.loads(rb)
                usage = rb.get("usage") or {}
                ct = int(usage.get("completion_tokens") or 1)
                start = str(row["start_time"])
                dt = parse_start_time(start)
                events.append(
                    EventMeta(
                        index=len(events),
                        offset=offset,
                        trace_id=str(row.get("trace_id") or len(events)),
                        start_time_orig=start,
                        start_epoch_s=dt.timestamp(),
                        completion_tokens=max(1, ct),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # Keep going; one bad line should not kill indexing.
                print(f"[index] skip offset={offset}: {exc}", flush=True)
    if not events:
        raise ValueError(f"No events indexed from {path}")
    events.sort(key=lambda e: (e.start_epoch_s, e.index))
    for i, e in enumerate(events):
        e.index = i
    return events


def read_prompt_at(path: Path, offset: int) -> dict[str, Any]:
    with path.open("rb") as f:
        f.seek(offset)
        line = f.readline().decode("utf-8", errors="replace")
    row = json.loads(line)
    pb = row["prompt_body"]
    if isinstance(pb, str):
        pb = json.loads(pb)
    return pb


def apply_schedule(
    events: list[EventMeta],
    *,
    scale_factor: float,
    start_epoch_s: float | None,
) -> list[EventMeta]:
    if scale_factor <= 0:
        raise ValueError("scale_factor must be > 0")
    selected = events
    if start_epoch_s is not None:
        selected = [e for e in events if e.start_epoch_s >= start_epoch_s]
        if not selected:
            raise ValueError("No events after --start-time / --start-from-dense")
    t0 = selected[0].start_epoch_s
    for e in selected:
        # Same as trace-replayer: logical_ms / scale_factor -> wall schedule ms
        rel_ms = (e.start_epoch_s - t0) * 1000.0
        e.sched_ms = int(rel_ms / scale_factor)
    return selected


def find_dense_start_epoch(events: list[EventMeta], window_s: float = 3600.0) -> float:
    """Start of densest wall-clock window in the original timeline."""
    if not events:
        raise ValueError("empty events")
    best_n = -1
    best_t0 = events[0].start_epoch_s
    j = 0
    for i, e in enumerate(events):
        while j < len(events) and events[j].start_epoch_s < e.start_epoch_s + window_s:
            j += 1
        n = j - i
        if n > best_n:
            best_n = n
            best_t0 = e.start_epoch_s
    return best_t0


async def measure_chat(
    client: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    tools: list[dict[str, Any]] | None,
    temperature: float,
    timeout_s: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    first_token_at: float | None = None
    prompt_tokens = 0
    cached_tokens = 0
    completion_tokens = 0

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
        "timeout": timeout_s,
    }
    if tools:
        kwargs["tools"] = tools

    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and (
                delta.content
                or getattr(delta, "tool_calls", None)
                or getattr(delta, "reasoning_content", None)
            ):
                if first_token_at is None:
                    first_token_at = time.perf_counter()
        if chunk.usage is not None:
            prompt_tokens = int(chunk.usage.prompt_tokens or 0)
            completion_tokens = int(chunk.usage.completion_tokens or 0)
            details = getattr(chunk.usage, "prompt_tokens_details", None)
            if details is not None:
                cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)

    ended = time.perf_counter()
    e2e_ms = (ended - started) * 1000.0
    ttft_ms = (
        None if first_token_at is None else (first_token_at - started) * 1000.0
    )
    tpot_ms = None
    if (
        ttft_ms is not None
        and completion_tokens
        and completion_tokens > 0
        and e2e_ms > ttft_ms
    ):
        # decode span / tokens; align with trace-replayer total_time/output_length
        tpot_ms = (e2e_ms - ttft_ms) / completion_tokens

    hit = None
    if prompt_tokens > 0:
        hit = cached_tokens / prompt_tokens

    return {
        "ttft_ms": None if ttft_ms is None else round(ttft_ms, 3),
        "tpot_ms": None if tpot_ms is None else round(tpot_ms, 3),
        "e2e_ms": round(e2e_ms, 3),
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": completion_tokens,
        "cache_hit_ratio": None if hit is None else round(hit, 6),
        "status": "200",
    }


def build_summary(results: list[RequestResult], wall_clock_s: float) -> dict[str, Any]:
    ok = [r for r in results if r.error is None and r.status == "200"]
    err = [r for r in results if r not in ok]
    err_break = Counter((r.error or r.status or "unknown") for r in err)

    def block(vals: list[float | None]) -> dict[str, Any]:
        xs = [float(v) for v in vals if v is not None]
        return {
            "count": len(xs),
            "p50": percentile(xs, 0.5),
            "p90": percentile(xs, 0.9),
            "p99": percentile(xs, 0.99),
            "mean": (sum(xs) / len(xs)) if xs else None,
        }

    prompt_sum = sum(r.prompt_tokens or 0 for r in ok)
    cached_sum = sum(r.cached_tokens or 0 for r in ok)
    completion_sum = sum(r.completion_tokens or 0 for r in ok)
    hits = [
        r.cache_hit_ratio
        for r in ok
        if r.cache_hit_ratio is not None
    ]
    cold = sum(1 for r in ok if (r.cached_tokens or 0) == 0)

    return {
        "integrity": {
            "n_issued": len(results),
            "n_ok": len(ok),
            "n_err": len(err),
            "error_breakdown": dict(err_break),
            "wall_clock_s": round(wall_clock_s, 3),
        },
        "latency": {
            "ttft_ms": block([r.ttft_ms for r in ok]),
            "tpot_ms": block([r.tpot_ms for r in ok]),
            "e2e_ms": block([r.e2e_ms for r in ok]),
        },
        "kv": {
            "prompt_tokens_sum": prompt_sum,
            "cached_tokens_sum": cached_sum,
            "completion_tokens_sum": completion_sum,
            "token_weighted_hit": (
                None if prompt_sum == 0 else round(cached_sum / prompt_sum, 6)
            ),
            "per_req_hit_rate": block(hits),
            "cold_miss_rate": (None if not ok else round(cold / len(ok), 6)),
        },
        "schedule": {
            "s_time_drift_ms": block([r.s_time_drift_ms for r in results]),
        },
        "throughput": {
            "req_per_s": (
                None if wall_clock_s <= 0 else round(len(ok) / wall_clock_s, 4)
            ),
            "output_tok_per_s": (
                None
                if wall_clock_s <= 0
                else round(completion_sum / wall_clock_s, 4)
            ),
        },
    }


def render_report(meta: dict[str, Any], summary: dict[str, Any]) -> str:
    integ = summary["integrity"]
    lat = summary["latency"]
    kv = summary["kv"]
    sched = summary["schedule"]
    thr = summary["throughput"]

    def fmt(v: Any) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.3f}"
        return str(v)

    def lat_line(name: str, b: dict[str, Any]) -> str:
        return (
            f"| {name} | {fmt(b.get('p50'))} | {fmt(b.get('p90'))} | "
            f"{fmt(b.get('p99'))} | {fmt(b.get('mean'))} | {b.get('count')} |"
        )

    lines = [
        "# GLM online open-loop replay report",
        "",
        f"- model: `{meta.get('model')}`",
        f"- base_url: `{meta.get('base_url')}`",
        f"- scale_factor: **{meta.get('scale_factor')}**",
        f"- time_in_secs: **{meta.get('time_in_secs')}**",
        f"- wall_clock_s: **{integ.get('wall_clock_s')}**",
        f"- dataset: `{meta.get('dataset')}`",
        "",
        "## Integrity",
        "",
        f"| metric | value |",
        f"|---|---|",
        f"| n_issued | {integ.get('n_issued')} |",
        f"| n_ok | {integ.get('n_ok')} |",
        f"| n_err | {integ.get('n_err')} |",
        f"| error_breakdown | `{json.dumps(integ.get('error_breakdown') or {}, ensure_ascii=False)}` |",
        "",
        "## Latency (ok)",
        "",
        "| metric | p50 | p90 | p99 | mean | count |",
        "|---|---:|---:|---:|---:|---:|",
        lat_line("TTFT_ms", lat["ttft_ms"]),
        lat_line("TPOT_ms", lat["tpot_ms"]),
        lat_line("e2e_ms", lat["e2e_ms"]),
        "",
        "## KV",
        "",
        f"| metric | value |",
        f"|---|---|",
        f"| token_weighted_hit | {fmt(kv.get('token_weighted_hit'))} |",
        f"| per_req_hit p50/p90 | {fmt(kv['per_req_hit_rate'].get('p50'))} / {fmt(kv['per_req_hit_rate'].get('p90'))} |",
        f"| cold_miss_rate | {fmt(kv.get('cold_miss_rate'))} |",
        f"| cached/prompt | {kv.get('cached_tokens_sum')} / {kv.get('prompt_tokens_sum')} |",
        "",
        "## Schedule / throughput",
        "",
        f"| metric | value |",
        f"|---|---|",
        f"| s_time_drift_ms p50/p90 | {fmt(sched['s_time_drift_ms'].get('p50'))} / {fmt(sched['s_time_drift_ms'].get('p90'))} |",
        f"| req/s | {fmt(thr.get('req_per_s'))} |",
        f"| output tok/s | {fmt(thr.get('output_tok_per_s'))} |",
        "",
    ]
    return "\n".join(lines)


async def run_replay(args: argparse.Namespace) -> int:
    dataset = Path(args.dataset)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    prefix = args.out_prefix or f"run_glm_openloop_{ts}"
    path_jsonl = out_dir / f"{prefix}.jsonl"
    path_summary = out_dir / f"{prefix}.summary.json"
    path_meta = out_dir / f"{prefix}.meta.json"
    path_report = out_dir / f"{prefix}_report.md"

    print(f"[index] scanning {dataset} ...", flush=True)
    t_index = time.perf_counter()
    all_events = load_event_index(dataset)
    print(
        f"[index] {len(all_events)} events in {time.perf_counter() - t_index:.1f}s",
        flush=True,
    )

    start_epoch = None
    if args.start_time:
        start_epoch = parse_start_time(args.start_time).timestamp()
    elif args.start_from_dense:
        start_epoch = find_dense_start_epoch(all_events, window_s=args.dense_window_s)
        print(
            f"[schedule] dense start epoch={start_epoch} "
            f"({datetime.fromtimestamp(start_epoch).isoformat()})",
            flush=True,
        )

    events = apply_schedule(
        all_events,
        scale_factor=args.scale_factor,
        start_epoch_s=start_epoch,
    )
    print(
        f"[schedule] n={len(events)} scale={args.scale_factor} "
        f"span_sched_s={events[-1].sched_ms / 1000.0:.1f} "
        f"origin_rps={len(events) / max(1e-9, (events[-1].start_epoch_s - events[0].start_epoch_s)):.3f} "
        f"scaled_rps≈{len(events) / max(1e-9, (events[-1].start_epoch_s - events[0].start_epoch_s) / args.scale_factor):.3f}",
        flush=True,
    )

    model = args.model
    if not args.dry_run:
        if not model:
            import requests

            resp = requests.get(f"{args.base_url.rstrip('/')}/v1/models", timeout=30)
            resp.raise_for_status()
            model = resp.json()["data"][0]["id"]
    else:
        model = model or "dry-run"

    meta = {
        "created_unix": time.time(),
        "mode": "glm_online_openloop_trace_replayer_style",
        "base_url": args.base_url,
        "model": model,
        "dataset": str(dataset),
        "scale_factor": args.scale_factor,
        "time_in_secs": args.time_in_secs,
        "start_time": args.start_time,
        "start_from_dense": args.start_from_dense,
        "dense_window_s": args.dense_window_s,
        "max_tokens_slack": args.max_tokens_slack,
        "max_tokens_cap": args.max_tokens_cap,
        "flatten_tools": args.flatten_tools,
        "no_tools": args.no_tools,
        "max_inflight": args.max_inflight,
        "temperature": args.temperature,
        "dry_run": args.dry_run,
        "n_events_indexed": len(all_events),
        "n_events_scheduled": len(events),
        "first_start_time_orig": events[0].start_time_orig,
        "last_start_time_orig": events[-1].start_time_orig,
    }
    path_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    if args.dry_run:
        # Emit a short schedule preview then summary of planned fires.
        preview_n = min(args.dry_run_preview, len(events))
        with path_jsonl.open("w", encoding="utf-8") as fout:
            for e in events[:preview_n]:
                max_tokens = e.completion_tokens + args.max_tokens_slack
                if args.max_tokens_cap is not None:
                    max_tokens = min(max_tokens, args.max_tokens_cap)
                fout.write(
                    json.dumps(
                        {
                            "index": e.index,
                            "trace_id": e.trace_id,
                            "start_time_orig": e.start_time_orig,
                            "t_sched_ms": e.sched_ms,
                            "max_tokens": max(1, max_tokens),
                            "dry_run": True,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        summary = {
            "integrity": {
                "n_issued": preview_n,
                "n_ok": 0,
                "n_err": 0,
                "error_breakdown": {},
                "wall_clock_s": 0.0,
                "dry_run": True,
                "n_scheduled_total": len(events),
            },
            "latency": {},
            "kv": {},
            "schedule": {},
            "throughput": {},
        }
        path_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        path_report.write_text(
            f"# dry-run\n\nScheduled **{len(events)}** events; "
            f"preview wrote {preview_n} lines to `{path_jsonl.name}`.\n"
            f"First fire at 0 ms, last at {events[-1].sched_ms} ms "
            f"(scale={args.scale_factor}).\n"
        )
        print(f"[dry-run] wrote {path_jsonl} / {path_meta}", flush=True)
        return 0

    client = AsyncOpenAI(
        base_url=f"{args.base_url.rstrip('/')}/v1",
        api_key=args.api_key,
    )

    stop_flag = asyncio.Event()
    results: list[RequestResult] = []
    results_lock = asyncio.Lock()
    inflight: set[asyncio.Task[None]] = set()
    # max_inflight<=0：不限制，完全按时间戳发（trace-replayer 行为）
    sem: asyncio.Semaphore | None = None
    if args.max_inflight and args.max_inflight > 0:
        sem = asyncio.Semaphore(int(args.max_inflight))
    jsonl_lock = asyncio.Lock()
    fout = path_jsonl.open("w", encoding="utf-8")

    async def write_result(rec: RequestResult) -> None:
        line = json.dumps(asdict(rec), ensure_ascii=False)
        async with jsonl_lock:
            fout.write(line + "\n")
            fout.flush()
        async with results_lock:
            results.append(rec)

    async def one_request(ev: EventMeta, s_time_ms: float, drift_ms: float) -> None:
        max_tokens = ev.completion_tokens + args.max_tokens_slack
        if args.max_tokens_cap is not None:
            max_tokens = min(max_tokens, args.max_tokens_cap)
        max_tokens = max(1, int(max_tokens))
        rec = RequestResult(
            index=ev.index,
            trace_id=ev.trace_id,
            start_time_orig=ev.start_time_orig,
            t_sched_ms=float(ev.sched_ms),
            s_time_ms=s_time_ms,
            s_time_drift_ms=drift_ms,
            max_tokens=max_tokens,
        )
        try:
            pb = await asyncio.to_thread(read_prompt_at, dataset, ev.offset)
            raw_messages = pb.get("messages") or []
            if args.flatten_tools or args.no_tools:
                messages = flatten_messages(raw_messages)
                tools = None
            else:
                messages = sanitize_messages(raw_messages)
                tools = None if args.no_tools else (pb.get("tools") or None)

            metrics = await measure_chat(
                client,
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                tools=tools,
                temperature=args.temperature,
                timeout_s=args.request_timeout_s,
            )
            rec.e_time_ms = s_time_ms + float(metrics["e2e_ms"])
            rec.ttft_ms = metrics["ttft_ms"]
            rec.tpot_ms = metrics["tpot_ms"]
            rec.e2e_ms = metrics["e2e_ms"]
            rec.prompt_tokens = metrics["prompt_tokens"]
            rec.cached_tokens = metrics["cached_tokens"]
            rec.completion_tokens = metrics["completion_tokens"]
            rec.cache_hit_ratio = metrics["cache_hit_ratio"]
            rec.status = metrics["status"]
        except Exception as exc:  # noqa: BLE001
            rec.error = f"{type(exc).__name__}: {exc}"
            rec.status = "error"
            rec.e_time_ms = (time.perf_counter() - base_perf) * 1000.0
        finally:
            if sem is not None:
                sem.release()
        await write_result(rec)

    async def stopper() -> None:
        await asyncio.sleep(args.time_in_secs)
        stop_flag.set()
        print(f"[stop] time_in_secs={args.time_in_secs} reached", flush=True)

    stop_task = asyncio.create_task(stopper())
    base_perf = time.perf_counter()
    issued = 0

    try:
        for ev in events:
            if stop_flag.is_set():
                break
            now_ms = (time.perf_counter() - base_perf) * 1000.0
            wait_ms = ev.sched_ms - now_ms
            if wait_ms > 1:
                try:
                    await asyncio.wait_for(stop_flag.wait(), timeout=wait_ms / 1000.0)
                    break
                except asyncio.TimeoutError:
                    pass
            if stop_flag.is_set():
                break

            if sem is not None:
                await sem.acquire()
                if stop_flag.is_set():
                    sem.release()
                    break

            s_time_ms = (time.perf_counter() - base_perf) * 1000.0
            drift_ms = s_time_ms - float(ev.sched_ms)
            task = asyncio.create_task(one_request(ev, s_time_ms, drift_ms))
            inflight.add(task)
            task.add_done_callback(inflight.discard)
            issued += 1
            if issued % 50 == 0:
                print(
                    f"[progress] issued={issued} inflight={len(inflight)} "
                    f"drift_ms={drift_ms:.1f}",
                    flush=True,
                )
            if args.early_stop_error_threshold is not None:
                async with results_lock:
                    n_err = sum(1 for r in results if r.error)
                    n_done = len(results)
                if n_done >= 10 and n_err >= args.early_stop_error_threshold:
                    print(
                        f"[stop] early_stop_error_threshold={args.early_stop_error_threshold}",
                        flush=True,
                    )
                    stop_flag.set()
                    break

        print(f"[drain] waiting {len(inflight)} in-flight ...", flush=True)
        if inflight:
            await asyncio.wait(inflight)
    finally:
        stop_task.cancel()
        fout.close()

    wall = time.perf_counter() - base_perf
    # Stable order for summary
    results_sorted = sorted(results, key=lambda r: r.index)
    summary = build_summary(results_sorted, wall_clock_s=wall)
    path_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    path_report.write_text(render_report(meta, summary))
    meta["wall_clock_s"] = round(wall, 3)
    meta["n_issued"] = summary["integrity"]["n_issued"]
    path_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    if args.update_latest:
        for src, name in [
            (path_jsonl, "latest.jsonl"),
            (path_summary, "latest.summary.json"),
            (path_report, "latest_report.md"),
            (path_meta, "latest.meta.json"),
        ]:
            link = out_dir / name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(src.name)

    print(
        f"[done] issued={summary['integrity']['n_issued']} "
        f"ok={summary['integrity']['n_ok']} err={summary['integrity']['n_err']} "
        f"wall={wall:.1f}s",
        flush=True,
    )
    print(f"[done] {path_jsonl}", flush=True)
    print(f"[done] {path_summary}", flush=True)
    print(f"[done] {path_report}", flush=True)
    return 0 if summary["integrity"]["n_err"] == 0 else 2


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    p.add_argument("--base-url", default="http://127.0.0.1:30000")
    p.add_argument("--api-key", default="EMPTY")
    p.add_argument("--model", default=None, help="default: fetch /v1/models")
    p.add_argument(
        "--scale-factor",
        type=float,
        default=1.0,
        help="trace-replayer scale: wall = logical / scale_factor (>1 faster)",
    )
    p.add_argument(
        "--time-in-secs",
        "-t",
        type=float,
        default=3600.0,
        help="stop issuing after this many wall-clock seconds",
    )
    p.add_argument("--start-time", default=None, help="ISO8601; skip earlier events")
    p.add_argument(
        "--start-from-dense",
        action="store_true",
        help="start at densest 1h window (override --start-time)",
    )
    p.add_argument("--dense-window-s", type=float, default=3600.0)
    p.add_argument("--max-tokens-slack", type=int, default=0)
    p.add_argument("--max-tokens-cap", type=int, default=None)
    p.add_argument(
        "--flatten-tools",
        action="store_true",
        help="flatten tool roles into plain chat (safer / less faithful)",
    )
    p.add_argument(
        "--no-tools",
        action="store_true",
        help="do not send tools[]; implies flattened tool history",
    )
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--request-timeout-s", type=float, default=600.0)
    p.add_argument(
        "--max-inflight",
        type=int,
        default=0,
        help="client concurrency cap; 0 = unlimited (trace-replayer default)",
    )
    p.add_argument("--early-stop-error-threshold", type=int, default=None)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--out-prefix", default=None)
    p.add_argument("--update-latest", action="store_true", default=True)
    p.add_argument("--no-latest", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dry-run-preview", type=int, default=20)
    return p


def main() -> None:
    args = build_argparser().parse_args()
    if args.no_latest:
        args.update_latest = False
    raise SystemExit(asyncio.run(run_replay(args)))


if __name__ == "__main__":
    main()
