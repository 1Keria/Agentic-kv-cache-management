#!/usr/bin/env python3
"""Synthesize an idle-prefix mix from mix_eval_longgap.

Goal: Belady−LRU room large enough to score eviction policy. Collapse OpenHands
tool-loop bursts (sub-threshold pre_gap) into one round each, keep only sessions
with at least one inter-round idle >= --min-idle-s, drop GLM, keep Request as
KV pressure.

Replay with the same 9-wave / 10800s recipe as the 3h mix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PARENT = REPO / "workloads/mix_eval_longgap_oh59_g150_r1050"
OUT = REPO / "workloads/mix_eval_idle_oh20_r1050"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            f.write(line)
            f.write("\n")
            h.update(line.encode("utf-8"))
            h.update(b"\n")
    return h.hexdigest()


def bursts(n: int, gaps: list[float], thresh: float) -> list[list[int]]:
    groups: list[list[int]] = []
    cur = [0]
    for i in range(1, n):
        if gaps[i] < thresh:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)
    return groups


def collapse_oh(
    turns: list[dict[str, Any]],
    *,
    burst_gap_s: float,
    min_idle_s: float,
) -> list[dict[str, Any]] | None:
    turns = sorted(turns, key=lambda r: int(r["turn_idx"]))
    gaps = [float(t.get("pre_gap_s") or 0.0) for t in turns]
    groups = bursts(len(turns), gaps, burst_gap_s)
    keep_idx = [g[-1] for g in groups]
    idles: list[float] = []
    for a, b in zip(keep_idx, keep_idx[1:]):
        idles.append(sum(gaps[j] for j in range(a + 1, b + 1)))
    if not any(g >= min_idle_s for g in idles):
        return None
    out: list[dict[str, Any]] = []
    for new_i, old_i in enumerate(keep_idx):
        row = dict(turns[old_i])
        if new_i == 0:
            idle = 0.0
        else:
            idle = idles[new_i - 1]
        src = dict(row.get("source") or {})
        src["orig_turn_idx"] = int(turns[old_i]["turn_idx"])
        src["burst_last"] = True
        src["n_collapsed"] = keep_idx[new_i] - (keep_idx[new_i - 1] + 1 if new_i else 0)
        row["turn_idx"] = new_i
        row["pre_gap_s"] = round(idle, 6)
        row["source"] = src
        out.append(row)
    return out


def assign_waves(
    sessions: list[tuple[str, str]],
    *,
    horizon_s: float,
    n_waves: int,
    wave_width_s: float,
    seed: int,
) -> dict[str, float]:
    by_cls: dict[str, list[str]] = {}
    for sid, cls in sessions:
        by_cls.setdefault(cls, []).append(sid)
    rng = random.Random(seed)
    n_waves = max(1, int(n_waves))
    width = max(0.0, float(wave_width_s))
    horizon = float(horizon_s)
    wave_bags: list[dict[str, list[str]]] = [
        {cls: [] for cls in by_cls} for _ in range(n_waves)
    ]
    for cls, sids in by_cls.items():
        shuffled = list(sids)
        rng.shuffle(shuffled)
        for i, sid in enumerate(shuffled):
            wave_bags[i % n_waves][cls].append(sid)
    starts: dict[str, float] = {}
    for wave_idx, class_bags in enumerate(wave_bags):
        anchor = 0.0 if n_waves == 1 else wave_idx * horizon / (n_waves - 1)
        wave_start = min(anchor, max(0.0, horizon - width))
        counts = {cls: len(sids) for cls, sids in class_bags.items()}
        issued = {cls: 0 for cls in class_bags}
        n_wave = sum(counts.values())
        order: list[tuple[str, str]] = []
        for _ in range(n_wave):
            remaining = [cls for cls, n in counts.items() if issued[cls] < n]
            cls = min(remaining, key=lambda c: issued[c] / counts[c])
            order.append((cls, class_bags[cls][issued[cls]]))
            issued[cls] += 1
        dt = 0.0 if n_wave <= 1 else width / (n_wave - 1)
        for i, (_cls, sid) in enumerate(order):
            starts[sid] = round(wave_start + i * dt, 6)
    return starts


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent", type=Path, default=PARENT)
    p.add_argument("--out-dir", type=Path, default=OUT)
    p.add_argument("--burst-gap-s", type=float, default=10.0)
    p.add_argument("--min-idle-s", type=float, default=60.0)
    p.add_argument("--n-request", type=int, default=1050)
    p.add_argument("--horizon-s", type=float, default=10800.0)
    p.add_argument("--arrival-waves", type=int, default=9)
    p.add_argument("--arrival-wave-width-s", type=float, default=10.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--idle-floor-s",
        type=float,
        default=0.0,
        help="Raise each inter-round OH idle to at least this many seconds (0=keep real gaps).",
    )
    p.add_argument(
        "--oh-start-window-s",
        type=float,
        default=None,
        help="Pack all OpenHands session starts into [0, window] so live prefixes overlap. "
        "Request still uses waves over --horizon-s. Default: same waves as Request.",
    )
    p.add_argument(
        "--n-openhands",
        type=int,
        default=None,
        help="Cap kept OH sessions (first-seen order after the idle filter). Default: keep all.",
    )
    p.add_argument(
        "--request-start-offset-s",
        type=float,
        default=0.0,
        help="Shift all Request session_start_s later so they hit during OH idle, not first prefill.",
    )
    args = p.parse_args()

    src = args.parent / "workload.jsonl"
    if not src.is_file():
        raise SystemExit(f"missing parent workload {src}")

    print(f"[load] {src}", flush=True)
    oh_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    req_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    oh_order: list[str] = []
    req_order: list[str] = []
    n_lines = 0
    with src.open() as f:
        for line in f:
            n_lines += 1
            row = json.loads(line)
            cls = row["traffic_class"]
            sid = str(row["session_id"])
            if cls == "openhands":
                if sid not in oh_by:
                    oh_order.append(sid)
                oh_by[sid].append(row)
            elif cls == "request":
                if sid not in req_by:
                    req_order.append(sid)
                req_by[sid].append(row)
            if n_lines % 1000 == 0:
                print(f"[load] {n_lines}", flush=True)
    print(
        f"[load] lines={n_lines} oh_sessions={len(oh_by)} request_sessions={len(req_by)}",
        flush=True,
    )

    collapsed: list[tuple[str, list[dict[str, Any]]]] = []
    dropped = 0
    for sid in oh_order:
        kept = collapse_oh(
            oh_by[sid], burst_gap_s=float(args.burst_gap_s), min_idle_s=float(args.min_idle_s)
        )
        if kept is None:
            dropped += 1
            continue
        floor = float(args.idle_floor_s)
        if floor > 0:
            for row in kept[1:]:
                row["pre_gap_s"] = round(max(float(row["pre_gap_s"]), floor), 6)
        collapsed.append((sid, kept))
    print(
        f"[oh] kept={len(collapsed)} dropped={dropped} "
        f"rounds={sum(len(t) for _, t in collapsed)} "
        f"burst_gap={args.burst_gap_s}s min_idle={args.min_idle_s}s",
        flush=True,
    )
    if not collapsed:
        raise SystemExit("no OpenHands sessions with a long inter-round idle")
    if args.n_openhands is not None:
        n_keep = max(0, int(args.n_openhands))
        collapsed = collapsed[:n_keep]
        print(f"[oh] cap n_openhands={n_keep} kept={len(collapsed)}", flush=True)
        if not collapsed:
            raise SystemExit("n-openhands cap left zero sessions")

    if len(req_order) < int(args.n_request):
        raise SystemExit(f"need {args.n_request} request sessions, have {len(req_order)}")
    rng = random.Random(args.seed)
    req_pick = list(req_order)
    rng.shuffle(req_pick)
    req_pick = req_pick[: int(args.n_request)]
    # stable first-seen order among picks
    req_keep = [sid for sid in req_order if sid in set(req_pick)]

    sess_ids: list[tuple[str, str]] = [(sid, "openhands") for sid, _ in collapsed]
    sess_ids.extend((sid, "request") for sid in req_keep)
    starts = assign_waves(
        sess_ids,
        horizon_s=float(args.horizon_s),
        n_waves=int(args.arrival_waves),
        wave_width_s=float(args.arrival_wave_width_s),
        seed=int(args.seed),
    )
    if args.oh_start_window_s is not None:
        window = max(0.0, float(args.oh_start_window_s))
        oh_sids = [sid for sid, _ in collapsed]
        n_oh = len(oh_sids)
        for i, sid in enumerate(oh_sids):
            starts[sid] = 0.0 if n_oh <= 1 or window <= 0 else round(i * window / (n_oh - 1), 6)
    req_offset = float(args.request_start_offset_s)
    if req_offset:
        for sid in req_keep:
            starts[sid] = round(float(starts[sid]) + req_offset, 6)

    turns: list[dict[str, Any]] = []
    metas: list[dict[str, Any]] = []
    for sid, rows in collapsed:
        t0 = float(starts[sid])
        for row in rows:
            row = dict(row)
            row["session_start_s"] = t0
            turns.append(row)
        idles = [float(r["pre_gap_s"]) for r in rows[1:]]
        metas.append(
            {
                "session_id": sid,
                "traffic_class": "openhands",
                "session_start_s": t0,
                "n_turns": len(rows),
                "orig_span_s": round(sum(idles), 6),
                "max_tokens_sum": sum(int(r.get("max_tokens") or 0) for r in rows),
                "n_idle_ge_min": sum(g >= float(args.min_idle_s) for g in idles),
                "source": dict(rows[0].get("source") or {}),
            }
        )
    for sid in req_keep:
        rows = sorted(req_by[sid], key=lambda r: int(r["turn_idx"]))
        t0 = float(starts[sid])
        for row in rows:
            row = dict(row)
            row["session_start_s"] = t0
            turns.append(row)
        metas.append(
            {
                "session_id": sid,
                "traffic_class": "request",
                "session_start_s": t0,
                "n_turns": len(rows),
                "orig_span_s": round(sum(float(r.get("pre_gap_s") or 0.0) for r in rows), 6),
                "max_tokens_sum": sum(int(r.get("max_tokens") or 0) for r in rows),
                "source": dict(rows[0].get("source") or {}),
            }
        )

    turns.sort(key=lambda r: (r["session_start_s"], r["session_id"], int(r["turn_idx"])))
    out_dir = args.out_dir if args.out_dir.is_absolute() else REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    w_sha = write_jsonl(out_dir / "workload.jsonl", turns)
    s_sha = write_jsonl(out_dir / "sessions.jsonl", metas)

    oh_turns = [t for t in turns if t["traffic_class"] == "openhands"]
    oh_idles = [float(t["pre_gap_s"]) for t in oh_turns if int(t["turn_idx"]) > 0]
    if args.oh_start_window_s is not None:
        arrival_type = "frozen"
        arrival_note = (
            "OH packed into [0, oh_start_window]; Request uses waves"
            + (
                f" shifted +{args.request_start_offset_s}s"
                if float(args.request_start_offset_s)
                else ""
            )
            + ". Replay MUST use --arrival frozen so starts are not overwritten."
        )
    else:
        arrival_type = "waves"
        arrival_note = (
            "Replay must pass the same waves/horizon; "
            "session_start_s is already baked in but waves override is OK."
        )
    spec = {
        "name": out_dir.name,
        "created_unix": t0,
        "parent_workload": str(args.parent),
        "parent_workload_sha256": sha256_file(src),
        "recipe": {
            "agent": "openhands only; GLM dropped",
            "collapse": (
                f"keep last turn of each tool-loop burst "
                f"(pre_gap < {args.burst_gap_s}s); inter-round idle = sum of skipped pre_gaps"
            ),
            "filter": f"keep OH sessions with at least one inter-round idle >= {args.min_idle_s}s",
            "idle_floor_s": args.idle_floor_s,
            "oh_start_window_s": args.oh_start_window_s,
            "n_openhands_cap": args.n_openhands,
            "request_start_offset_s": args.request_start_offset_s,
            "request": "WildChat from parent, same n, KV pressure only",
        },
        "burst_gap_s": args.burst_gap_s,
        "min_idle_s": args.min_idle_s,
        "idle_floor_s": args.idle_floor_s,
        "oh_start_window_s": args.oh_start_window_s,
        "request_start_offset_s": args.request_start_offset_s,
        "n_openhands": len(collapsed),
        "n_glm": 0,
        "n_request": len(req_keep),
        "n_turns": len(turns),
        "n_turns_openhands": len(oh_turns),
        "oh_idle_n": len(oh_idles),
        "oh_idle_ge_60": sum(g >= 60 for g in oh_idles),
        "oh_idle_ge_180": sum(g >= 180 for g in oh_idles),
        "arrival": {
            "type": arrival_type,
            "horizon_s": args.horizon_s,
            "n_waves": args.arrival_waves,
            "wave_width_s": args.arrival_wave_width_s,
            "oh_start_window_s": args.oh_start_window_s,
            "request_start_offset_s": args.request_start_offset_s,
            "seed": args.seed,
            "note": arrival_note,
        },
        "seed": args.seed,
    }
    spec_path = out_dir / "spec.json"
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    spec_sha = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    manifest = {
        "name": spec["name"],
        "created_unix": t0,
        "workload_jsonl_sha256": w_sha,
        "sessions_jsonl_sha256": s_sha,
        "spec_json_sha256": spec_sha,
        "n_turns": len(turns),
        "n_sessions_by_class": {
            "openhands": len(collapsed),
            "request": len(req_keep),
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"[write] {out_dir} turns={len(turns)} oh={len(oh_turns)} "
        f"idle>60={spec['oh_idle_ge_60']}/{len(oh_idles)} sha={w_sha[:16]}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
