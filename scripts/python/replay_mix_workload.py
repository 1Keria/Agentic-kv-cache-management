#!/usr/bin/env python3
"""Session-closed replay of a mix workload.

Reads workloads/<name>/workload.jsonl. Intra-session: wait for the previous
turn, then sleep pre_gap. Inter-session arrival is staggered or poisson.
LRU baseline does not send traffic_class to the server.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests
from openai import AsyncOpenAI

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKLOAD_DIR = REPO_ROOT / "workloads/mix_oh20_g1200_r1000"
AGENT_LIKE = {"agent", "openhands", "glm"}
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "experiments/sglang_kv_cache/mix_replay/v4flash_vanilla"
)


@dataclass
class Turn:
    traffic_class: str
    session_id: str
    turn_idx: int
    session_start_s: float
    pre_gap_s: float
    max_tokens: int
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None
    index: int = -1


@dataclass
class RequestResult:
    index: int
    trace_id: str
    start_time_orig: str
    t_sched_ms: float
    s_time_ms: float
    s_time_drift_ms: float
    traffic_class: str
    session_id: str
    turn_index: int
    pre_gap_s: float
    sleep_before_s: float
    max_tokens: int
    e_time_ms: float | None = None
    ttft_ms: float | None = None
    tpot_ms: float | None = None
    e2e_ms: float | None = None
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    completion_tokens: int | None = None
    cache_hit_ratio: float | None = None
    status: str | None = None
    error: str | None = None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(workload_dir: Path, workload_path: Path) -> None:
    manifest_path = workload_dir / "manifest.json"
    if not manifest_path.is_file():
        print("[warn] no manifest.json, skip hash check", flush=True)
        return
    manifest = json.loads(manifest_path.read_text())
    expected = manifest.get("workload_jsonl_sha256")
    if not expected:
        return
    got = sha256_file(workload_path)
    if got != expected:
        raise SystemExit(
            f"workload.jsonl hash mismatch: got {got} expected {expected}"
        )
    print(f"[ok] workload.jsonl sha256={got}", flush=True)


def api_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        item: dict[str, Any] = {"role": msg.get("role") or "user"}
        if "content" in msg:
            item["content"] = msg.get("content")
        if msg.get("tool_calls"):
            item["tool_calls"] = msg["tool_calls"]
        if msg.get("tool_call_id"):
            item["tool_call_id"] = msg["tool_call_id"]
        if item["role"] == "tool" and msg.get("name"):
            item["name"] = msg["name"]
        out.append(item)
    return out


def load_sessions(workload_path: Path) -> list[tuple[str, list[Turn]]]:
    buckets: dict[str, list[Turn]] = defaultdict(list)
    order: list[str] = []
    with workload_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            sid = str(row["session_id"])
            if sid not in buckets:
                order.append(sid)
            body = row.get("prompt_body") or {}
            buckets[sid].append(
                Turn(
                    traffic_class=str(row["traffic_class"]),
                    session_id=sid,
                    turn_idx=int(row["turn_idx"]),
                    session_start_s=float(row["session_start_s"]),
                    pre_gap_s=float(row["pre_gap_s"]),
                    max_tokens=max(1, int(row["max_tokens"])),
                    messages=list(body.get("messages") or []),
                    tools=list(body["tools"]) if body.get("tools") else None,
                )
            )
    sessions: list[tuple[str, list[Turn]]] = []
    index = 0
    for sid in order:
        turns = sorted(buckets[sid], key=lambda t: t.turn_idx)
        for turn in turns:
            turn.index = index
            index += 1
        sessions.append((sid, turns))
    if not sessions:
        raise ValueError(f"No turns in {workload_path}")
    return sessions


def load_spec_arrival(workload_dir: Path) -> dict[str, Any]:
    spec_path = workload_dir / "spec.json"
    if not spec_path.is_file():
        return {}
    spec = json.loads(spec_path.read_text())
    return dict(spec.get("arrival") or {})


def apply_arrival(
    sessions: list[tuple[str, list[Turn]]],
    *,
    mode: str,
    delta_agent_s: float,
    delta_request_s: float,
    mean_gap_agent_s: float,
    mean_gap_request_s: float,
    arrival_seed: int,
    arrival_horizon_s: float | None = None,
    arrival_waves: int = 6,
    arrival_wave_width_s: float = 10.0,
) -> dict[str, Any]:
    """Assign session_start_s from the arrival process. Content / pre_gap unchanged.

    staggered: each traffic_class starts at t=0 with its own Δ (short classes finish first).
    uniform: every class is spaced across the same horizon so the mix stays mixed.
    waves: every class is split across synchronized mixed bursts over the horizon.
    poisson: seeded exponential inter-arrival per class from t=0.
    frozen: keep session_start_s baked into the workload jsonl.
    """
    by_cls: dict[str, list[str]] = {}
    turns_of: dict[str, list[Turn]] = {}
    for sid, turns in sessions:
        if not turns:
            continue
        cls = turns[0].traffic_class
        by_cls.setdefault(cls, []).append(sid)
        turns_of[sid] = turns

    starts: dict[str, float] = {}
    if mode == "staggered":
        for cls, sids in by_cls.items():
            delta = delta_agent_s if cls in AGENT_LIKE else delta_request_s
            for i, sid in enumerate(sids):
                starts[sid] = round(i * delta, 6)
        info: dict[str, Any] = {
            "type": "staggered",
            "delta_agent_s": delta_agent_s,
            "delta_request_s": delta_request_s,
            "classes": sorted(by_cls),
            "session_start_s": starts,
        }
    elif mode == "uniform":
        rng = random.Random(arrival_seed)
        bags: dict[str, list[str]] = {}
        counts: dict[str, int] = {}
        for cls, sids in by_cls.items():
            bag = list(sids)
            rng.shuffle(bag)
            bags[cls] = bag
            counts[cls] = len(bag)
        n_total = sum(counts.values())
        class_horizon: dict[str, float] = {}
        for cls, sids in by_cls.items():
            delta = delta_agent_s if cls in AGENT_LIKE else delta_request_s
            class_horizon[cls] = 0.0 if len(sids) <= 1 else (len(sids) - 1) * delta
        horizon = float(
            arrival_horizon_s
            if arrival_horizon_s is not None
            else (max(class_horizon.values()) if class_horizon else 0.0)
        )
        issued = {cls: 0 for cls in bags}
        order: list[tuple[str, str]] = []
        for _ in range(n_total):
            leftover = [c for c, n in counts.items() if issued[c] < n]
            cls = min(leftover, key=lambda c: issued[c] / counts[c])
            order.append((cls, bags[cls][issued[cls]]))
            issued[cls] += 1
        dt = 0.0 if n_total <= 1 else horizon / (n_total - 1)
        for i, (_cls, sid) in enumerate(order):
            starts[sid] = round(i * dt, 6)
        info = {
            "type": "uniform",
            "horizon_s": round(horizon, 6),
            "global_dt_s": round(dt, 6),
            "n_sessions": n_total,
            "delta_agent_s": delta_agent_s,
            "delta_request_s": delta_request_s,
            "class_counts": counts,
            "arrival_seed": arrival_seed,
            "classes": sorted(by_cls),
            "session_start_s": starts,
        }
    elif mode == "waves":
        rng = random.Random(arrival_seed)
        n_waves = max(1, int(arrival_waves))
        width = max(0.0, float(arrival_wave_width_s))
        class_horizon: dict[str, float] = {}
        wave_bags: list[dict[str, list[str]]] = [
            {cls: [] for cls in by_cls} for _ in range(n_waves)
        ]
        for cls, original_sids in by_cls.items():
            delta = delta_agent_s if cls in AGENT_LIKE else delta_request_s
            class_horizon[cls] = (
                0.0 if len(original_sids) <= 1 else (len(original_sids) - 1) * delta
            )
            sids = list(original_sids)
            rng.shuffle(sids)
            for i, sid in enumerate(sids):
                wave_bags[i % n_waves][cls].append(sid)
        horizon = float(
            arrival_horizon_s
            if arrival_horizon_s is not None
            else (max(class_horizon.values()) if class_horizon else 0.0)
        )
        wave_class_counts: list[dict[str, int]] = []
        wave_times: list[float] = []
        for wave_idx, class_bags in enumerate(wave_bags):
            if n_waves == 1:
                anchor = 0.0
            else:
                anchor = wave_idx * horizon / (n_waves - 1)
            wave_start = min(anchor, max(0.0, horizon - width))
            counts = {cls: len(sids) for cls, sids in class_bags.items()}
            issued = {cls: 0 for cls in class_bags}
            n_wave = sum(counts.values())
            order: list[tuple[str, str]] = []
            for _ in range(n_wave):
                remaining = [
                    cls for cls, n in counts.items() if issued[cls] < n
                ]
                cls = min(remaining, key=lambda c: issued[c] / counts[c])
                order.append((cls, class_bags[cls][issued[cls]]))
                issued[cls] += 1
            dt = 0.0 if n_wave <= 1 else width / (n_wave - 1)
            for i, (_cls, sid) in enumerate(order):
                starts[sid] = round(wave_start + i * dt, 6)
            wave_times.append(round(wave_start, 6))
            wave_class_counts.append(counts)
        info = {
            "type": "waves",
            "horizon_s": round(horizon, 6),
            "n_waves": n_waves,
            "wave_width_s": round(width, 6),
            "wave_start_s": wave_times,
            "wave_class_counts": wave_class_counts,
            "arrival_seed": arrival_seed,
            "classes": sorted(by_cls),
            "session_start_s": starts,
        }
    elif mode == "poisson":
        rng = random.Random(arrival_seed)
        for cls, sids in by_cls.items():
            mean_gap = mean_gap_agent_s if cls in AGENT_LIKE else mean_gap_request_s
            t = 0.0
            for i, sid in enumerate(sids):
                if i > 0:
                    t += rng.expovariate(1.0 / max(mean_gap, 1e-6))
                starts[sid] = round(t, 6)
        info = {
            "type": "poisson",
            "mean_gap_agent_s": mean_gap_agent_s,
            "mean_gap_request_s": mean_gap_request_s,
            "arrival_seed": arrival_seed,
            "classes": sorted(by_cls),
            "session_start_s": starts,
        }
    elif mode == "frozen":
        starts = {sid: float(turns_of[sid][0].session_start_s) for sid in turns_of}
        info = {
            "type": "frozen",
            "note": "session_start_s taken from workload.jsonl",
            "classes": sorted(by_cls),
            "session_start_s": starts,
        }
    else:
        raise ValueError(f"Unknown arrival mode: {mode}")

    for sid, turns in turns_of.items():
        t0 = starts[sid]
        for turn in turns:
            turn.session_start_s = t0
    return info


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
    tools: list[dict[str, Any]] | None,
    custom_params: dict[str, Any] | None = None,
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
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "timeout": 600.0,
    }
    if tools:
        kwargs["tools"] = tools
    if custom_params:
        kwargs["extra_body"] = {"custom_params": custom_params}
    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and (
                delta.content or getattr(delta, "tool_calls", None)
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


async def run_session(
    *,
    client: AsyncOpenAI | None,
    model: str,
    session_index: int,
    turns: list[Turn],
    t0_perf: float,
    gap_scale: float,
    ablate_zero_gap: bool,
    request_gap_cap_s: float | None,
    dry_run: bool,
    write_result: Any,
) -> None:
    head = turns[0]
    delay = head.session_start_s - (time.perf_counter() - t0_perf)
    if delay > 0 and not dry_run:
        await asyncio.sleep(delay)

    for turn in turns:
        raw_gap = 0.0 if ablate_zero_gap else float(turn.pre_gap_s)
        if (
            request_gap_cap_s is not None
            and turn.traffic_class == "request"
            and turn.turn_idx > 0
        ):
            raw_gap = min(raw_gap, float(request_gap_cap_s))
        sleep_before = 0.0 if turn.turn_idx == 0 else max(0.0, raw_gap * gap_scale)
        if turn.turn_idx > 0 and sleep_before > 0 and not dry_run:
            await asyncio.sleep(sleep_before)

        s_time_ms = (time.perf_counter() - t0_perf) * 1000.0
        t_sched_ms = (
            head.session_start_s * 1000.0 if turn.turn_idx == 0 else -1.0
        )
        rec = RequestResult(
            index=int(turn.index),
            trace_id=f"{turn.session_id}#{turn.turn_idx}",
            start_time_orig=f"{head.session_start_s:.6f}",
            t_sched_ms=round(t_sched_ms, 3),
            s_time_ms=round(s_time_ms, 3),
            s_time_drift_ms=round(s_time_ms - t_sched_ms, 3) if t_sched_ms >= 0 else 0.0,
            traffic_class=turn.traffic_class,
            session_id=turn.session_id,
            turn_index=turn.turn_idx,
            pre_gap_s=raw_gap,
            sleep_before_s=round(sleep_before, 6),
            max_tokens=turn.max_tokens,
        )
        if dry_run:
            rec.status = "dry_run"
            print(
                f"[dry-run] {turn.traffic_class} s{session_index} turn{turn.turn_idx} "
                f"t_sched_ms={rec.t_sched_ms} sleep={sleep_before:.3f}s "
                f"max_tokens={turn.max_tokens}",
                flush=True,
            )
            await write_result(rec)
            continue
        assert client is not None
        try:
            metrics = await measure_chat(
                client,
                model,
                api_messages(turn.messages),
                turn.max_tokens,
                turn.tools,
                custom_params={
                    "session_id": turn.session_id,
                    "turn_idx": turn.turn_idx,
                    "traffic_class": turn.traffic_class,
                    "has_tools": bool(turn.tools),
                },
            )
            rec.e_time_ms = round(s_time_ms + float(metrics["e2e_ms"]), 3)
            rec.ttft_ms = metrics["ttft_ms"]
            rec.tpot_ms = metrics["tpot_ms"]
            rec.e2e_ms = metrics["e2e_ms"]
            rec.prompt_tokens = metrics["prompt_tokens"]
            rec.cached_tokens = metrics["cached_tokens"]
            rec.completion_tokens = metrics["completion_tokens"]
            rec.cache_hit_ratio = metrics["cache_hit_ratio"]
            rec.status = metrics["status"]
            print(
                f"[ok] {turn.traffic_class} s{session_index} turn{turn.turn_idx} "
                f"ttft={rec.ttft_ms}ms hit={rec.cache_hit_ratio} e2e={rec.e2e_ms}ms",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            rec.error = f"{type(exc).__name__}: {exc}"
            rec.status = "error"
            rec.e_time_ms = round((time.perf_counter() - t0_perf) * 1000.0, 3)
            print(
                f"[err] {turn.traffic_class} s{session_index} "
                f"turn{turn.turn_idx} {rec.error}",
                flush=True,
            )
            await write_result(rec)
            break
        await write_result(rec)


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


def _lat_block(vals: list[float | None]) -> dict[str, Any]:
    xs = [float(v) for v in vals if v is not None]
    return {
        "count": len(xs),
        "p50": percentile(xs, 0.5),
        "p90": percentile(xs, 0.9),
        "p99": percentile(xs, 0.99),
        "mean": (sum(xs) / len(xs)) if xs else None,
    }


def _kv_block(ok: list[RequestResult]) -> dict[str, Any]:
    prompt_sum = sum(r.prompt_tokens or 0 for r in ok)
    cached_sum = sum(r.cached_tokens or 0 for r in ok)
    completion_sum = sum(r.completion_tokens or 0 for r in ok)
    hits = [r.cache_hit_ratio for r in ok if r.cache_hit_ratio is not None]
    cold = sum(1 for r in ok if (r.cached_tokens or 0) == 0)
    return {
        "n": len(ok),
        "prompt_tokens_sum": prompt_sum,
        "cached_tokens_sum": cached_sum,
        "completion_tokens_sum": completion_sum,
        "token_weighted_hit": (
            None if prompt_sum == 0 else round(cached_sum / prompt_sum, 6)
        ),
        "per_req_hit_rate": _lat_block(hits),
        "cold_miss_rate": None if not ok else round(cold / len(ok), 6),
        "ttft_ms": _lat_block([r.ttft_ms for r in ok]),
        "tpot_ms": _lat_block([r.tpot_ms for r in ok]),
        "e2e_ms": _lat_block([r.e2e_ms for r in ok]),
    }


def _class_kv(rows: list[RequestResult]) -> dict[str, Any]:
    return {
        "all": _kv_block(rows),
        "turn0": _kv_block([r for r in rows if r.turn_index == 0]),
        "within_session": _kv_block([r for r in rows if r.turn_index >= 1]),
    }


def build_summary(results: list[RequestResult], wall_clock_s: float) -> dict[str, Any]:
    ok = [r for r in results if r.error is None and r.status == "200"]
    err = [r for r in results if r not in ok]
    err_break = Counter((r.error or r.status or "unknown") for r in err)
    by_cls: dict[str, list[RequestResult]] = defaultdict(list)
    for r in ok:
        by_cls[r.traffic_class].append(r)
    agent_rows = [r for r in ok if r.traffic_class in AGENT_LIKE]
    out: dict[str, Any] = {
        "integrity": {
            "n_issued": len(results),
            "n_ok": len(ok),
            "n_err": len(err),
            "error_breakdown": dict(err_break),
            "wall_clock_s": round(wall_clock_s, 3),
        },
        "latency": {
            "ttft_ms": _lat_block([r.ttft_ms for r in ok]),
            "tpot_ms": _lat_block([r.tpot_ms for r in ok]),
            "e2e_ms": _lat_block([r.e2e_ms for r in ok]),
        },
        "kv": _kv_block(ok),
        "schedule": {
            "s_time_drift_ms": _lat_block(
                [r.s_time_drift_ms for r in results if r.turn_index == 0]
            ),
        },
        "throughput": {
            "req_per_s": (
                None if wall_clock_s <= 0 else round(len(ok) / wall_clock_s, 4)
            ),
            "output_tok_per_s": (
                None
                if wall_clock_s <= 0
                else round(sum(r.completion_tokens or 0 for r in ok) / wall_clock_s, 4)
            ),
        },
        "by_class": {cls: _class_kv(rows) for cls, rows in sorted(by_cls.items())},
        "agent": _kv_block(agent_rows),
        "agent_within_session": _kv_block([r for r in agent_rows if r.turn_index >= 1]),
        "request": _kv_block(by_cls.get("request", [])),
    }
    for cls, rows in by_cls.items():
        out[cls] = _kv_block(rows)
        out[f"{cls}_turn0"] = _kv_block([r for r in rows if r.turn_index == 0])
        out[f"{cls}_within_session"] = _kv_block(
            [r for r in rows if r.turn_index >= 1]
        )
    return out


def render_report(meta: dict[str, Any], summary: dict[str, Any]) -> str:
    integ = summary["integrity"]
    lat = summary["latency"]
    kv = summary["kv"]
    sched = summary["schedule"]
    thr = summary["throughput"]
    arrival = meta.get("arrival") or {}

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

    def class_block(title: str, b: dict[str, Any]) -> list[str]:
        return [
            f"## {title}",
            "",
            f"| metric | value |",
            f"|---|---|",
            f"| n | {b.get('n')} |",
            f"| token_weighted_hit | {fmt(b.get('token_weighted_hit'))} |",
            f"| per_req_hit p50/p90 | {fmt((b.get('per_req_hit_rate') or {}).get('p50'))} / "
            f"{fmt((b.get('per_req_hit_rate') or {}).get('p90'))} |",
            f"| TTFT_ms p50/p90 | {fmt((b.get('ttft_ms') or {}).get('p50'))} / "
            f"{fmt((b.get('ttft_ms') or {}).get('p90'))} |",
            f"| TPOT_ms p50 | {fmt((b.get('tpot_ms') or {}).get('p50'))} |",
            f"| cached/prompt | {b.get('cached_tokens_sum')} / {b.get('prompt_tokens_sum')} |",
            "",
        ]

    lines = [
        "# Mix workload replay report",
        "",
        f"- model: `{meta.get('model')}`",
        f"- base_url: `{meta.get('base_url')}`",
        f"- workload: `{meta.get('workload_dir')}`",
        f"- arrival: `{arrival.get('type')}`",
        f"- request_gap_cap_s: {meta.get('request_gap_cap_s')}",
        f"- wall_clock_s: **{integ.get('wall_clock_s')}**",
        f"- dry_run: {meta.get('dry_run')}",
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
        f"| s_time_drift_ms p50/p90 (session start) | {fmt(sched['s_time_drift_ms'].get('p50'))} / {fmt(sched['s_time_drift_ms'].get('p90'))} |",
        f"| req/s | {fmt(thr.get('req_per_s'))} |",
        f"| output tok/s | {fmt(thr.get('output_tok_per_s'))} |",
        "",
    ]
    title = {
        "agent": "Agent (legacy / union)",
        "openhands": "OpenHands",
        "glm": "GLM-Agent (inferred sessions)",
        "request": "Request",
    }
    by_class = summary.get("by_class") or {}
    if by_class:
        for cls, blocks in by_class.items():
            label = title.get(cls, cls)
            lines.extend(class_block(label, blocks.get("all") or {}))
            lines.extend(class_block(f"{label} turn0", blocks.get("turn0") or {}))
            if cls in AGENT_LIKE:
                lines.extend(
                    class_block(
                        f"{label} within-session (turn>=1)",
                        blocks.get("within_session") or {},
                    )
                )
    else:
        lines.extend(class_block("Agent", summary.get("agent") or {}))
        lines.extend(
            class_block(
                "Agent within-session (turn>=1)",
                summary.get("agent_within_session") or {},
            )
        )
        lines.extend(class_block("Request", summary.get("request") or {}))
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> int:
    workload_dir = (
        args.workload_dir
        if args.workload_dir.is_absolute()
        else REPO_ROOT / args.workload_dir
    )
    workload_path = workload_dir / "workload.jsonl"
    if not workload_path.is_file():
        raise SystemExit(f"Missing {workload_path}; run scripts/shell/build_mix.sh first")
    verify_manifest(workload_dir, workload_path)
    sessions = load_sessions(workload_path)
    spec_arrival = load_spec_arrival(workload_dir)
    delta_agent = (
        args.delta_agent_s
        if args.delta_agent_s is not None
        else float(spec_arrival.get("delta_agent_s") or 15.0)
    )
    delta_request = (
        args.delta_request_s
        if args.delta_request_s is not None
        else float(spec_arrival.get("delta_request_s") or 5.0)
    )
    arrival = apply_arrival(
        sessions,
        mode=args.arrival,
        delta_agent_s=delta_agent,
        delta_request_s=delta_request,
        mean_gap_agent_s=float(args.mean_gap_agent_s),
        mean_gap_request_s=float(args.mean_gap_request_s),
        arrival_seed=int(args.arrival_seed),
        arrival_horizon_s=args.arrival_horizon_s,
        arrival_waves=int(args.arrival_waves),
        arrival_wave_width_s=float(args.arrival_wave_width_s),
    )
    n_turns = sum(len(t) for _, t in sessions)
    print(
        f"[index] {len(sessions)} sessions / {n_turns} turns from {workload_path}",
        flush=True,
    )
    print(
        "[arrival] "
        + json.dumps({k: v for k, v in arrival.items() if k != "session_start_s"}),
        flush=True,
    )
    if args.request_gap_cap_s is not None:
        print(
            f"[gap] request cap_s={args.request_gap_cap_s} "
            "(replay clamp; jsonl unchanged)",
            flush=True,
        )

    out_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path_jsonl = out_dir / "replay.jsonl"
    path_summary = out_dir / "summary.json"
    path_meta = out_dir / "meta.json"
    path_report = out_dir / "report.md"

    model = args.model
    if not args.dry_run:
        if not model:
            resp = requests.get(f"{args.base_url.rstrip('/')}/v1/models", timeout=30)
            resp.raise_for_status()
            model = resp.json()["data"][0]["id"]
        health_check(args.base_url)
        maybe_flush_cache(args.base_url, bool(args.flush_cache))
    else:
        model = model or "dry-run"

    meta = {
        "created_unix": time.time(),
        "mode": "mix_workload_session_closed",
        "base_url": args.base_url,
        "model": model,
        "workload_dir": str(workload_dir),
        "arrival": {k: v for k, v in arrival.items() if k != "session_start_s"},
        "gap_scale": args.gap_scale,
        "request_gap_cap_s": args.request_gap_cap_s,
        "ablate_zero_gap": bool(args.ablate_zero_gap),
        "flush_cache_before_run": bool(args.flush_cache),
        "dry_run": bool(args.dry_run),
        "n_sessions": len(sessions),
        "n_turns": n_turns,
    }
    path_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    client: AsyncOpenAI | None = None
    if not args.dry_run:
        client = AsyncOpenAI(
            base_url=f"{args.base_url.rstrip('/')}/v1",
            api_key="EMPTY",
            timeout=600.0,
        )

    results: list[RequestResult] = []
    results_lock = asyncio.Lock()
    jsonl_lock = asyncio.Lock()
    fout = path_jsonl.open("w", encoding="utf-8")

    async def write_result(rec: RequestResult) -> None:
        line = json.dumps(asdict(rec), ensure_ascii=False)
        async with jsonl_lock:
            fout.write(line + "\n")
            fout.flush()
        async with results_lock:
            results.append(rec)

    t0 = time.perf_counter()
    try:
        await asyncio.gather(
            *[
                run_session(
                    client=client,
                    model=model or "default",
                    session_index=i,
                    turns=turns,
                    t0_perf=t0,
                    gap_scale=float(args.gap_scale),
                    ablate_zero_gap=bool(args.ablate_zero_gap),
                    request_gap_cap_s=args.request_gap_cap_s,
                    dry_run=bool(args.dry_run),
                    write_result=write_result,
                )
                for i, (_sid, turns) in enumerate(sessions)
            ]
        )
    finally:
        fout.close()

    wall = time.perf_counter() - t0
    results_sorted = sorted(results, key=lambda r: r.index)
    if args.dry_run:
        summary = {
            "integrity": {
                "n_issued": len(results_sorted),
                "n_ok": 0,
                "n_err": 0,
                "error_breakdown": {},
                "wall_clock_s": round(wall, 3),
                "dry_run": True,
            },
            "latency": {"ttft_ms": {}, "tpot_ms": {}, "e2e_ms": {}},
            "kv": {"per_req_hit_rate": {}},
            "schedule": {"s_time_drift_ms": {}},
            "throughput": {},
            "by_class": {},
            "agent": {"n": 0, "per_req_hit_rate": {}, "ttft_ms": {}, "tpot_ms": {}},
            "agent_within_session": {
                "n": 0,
                "per_req_hit_rate": {},
                "ttft_ms": {},
                "tpot_ms": {},
            },
            "request": {"n": 0, "per_req_hit_rate": {}, "ttft_ms": {}, "tpot_ms": {}},
        }
    else:
        summary = build_summary(results_sorted, wall_clock_s=wall)
    path_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    path_report.write_text(render_report(meta, summary))
    meta["wall_clock_s"] = round(wall, 3)
    meta["n_issued"] = summary["integrity"]["n_issued"]
    path_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    print(
        f"[done] issued={summary['integrity']['n_issued']} "
        f"ok={summary['integrity'].get('n_ok')} err={summary['integrity'].get('n_err')} "
        f"wall={wall:.1f}s",
        flush=True,
    )
    print(f"[done] {path_jsonl}", flush=True)
    print(f"[done] {path_summary}", flush=True)
    print(f"[done] {path_report}", flush=True)
    if args.dry_run:
        return 0
    return 0 if summary["integrity"]["n_err"] == 0 else 2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:30000")
    p.add_argument("--model", default=None)
    p.add_argument("--workload-dir", type=Path, default=DEFAULT_WORKLOAD_DIR)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--out-prefix", default=None, help=argparse.SUPPRESS)
    p.add_argument("--gap-scale", type=float, default=1.0)
    p.add_argument(
        "--arrival",
        choices=("staggered", "uniform", "waves", "poisson", "frozen"),
        default="staggered",
        help="staggered=per-class Δ; uniform=shared horizon; waves=mixed bursts; poisson=exponential; frozen=jsonl session_start_s",
    )
    p.add_argument(
        "--arrival-horizon-s",
        type=float,
        default=None,
        help="uniform mode: shared timeline (default: max per-class (n-1)*Δ)",
    )
    p.add_argument(
        "--arrival-waves",
        type=int,
        default=6,
        help="waves mode: number of synchronized mixed bursts",
    )
    p.add_argument(
        "--arrival-wave-width-s",
        type=float,
        default=10.0,
        help="waves mode: spread each mixed burst over this many seconds",
    )
    p.add_argument("--delta-agent-s", type=float, default=None)
    p.add_argument("--delta-request-s", type=float, default=None)
    p.add_argument("--mean-gap-agent-s", type=float, default=15.0)
    p.add_argument("--mean-gap-request-s", type=float, default=5.0)
    p.add_argument("--arrival-seed", type=int, default=42)
    p.add_argument("--ablate-zero-gap", action="store_true")
    p.add_argument(
        "--request-gap-cap-s",
        type=float,
        default=None,
        help="clamp Request pre_gap at replay; jsonl stays frozen (e.g. 30 vs baked-in 900)",
    )
    p.add_argument(
        "--flush-cache",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    return asyncio.run(async_main(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
