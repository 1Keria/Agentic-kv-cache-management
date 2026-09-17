#!/usr/bin/env python3
"""Build unseen OpenHands/Request workloads for an agent-call-fraction sweep.

The OpenHands pool is restricted to content-deduplicated DeepSeek-V4-Flash
trajectories that were not used by the existing oh59 model-data workload.
Context resets split a trajectory into independent segments. Only segments
whose prompts form an exact growing prefix chain are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_mix_workload import (  # noqa: E402
    DEFAULT_WILDCHAT_DIR,
    REPO_ROOT,
    SKILLSBENCH_V11,
    SessionMeta,
    Turn,
    build_request_session,
    iter_wildchat_index,
    list_openhands_unique,
    load_agent_session,
    load_wildchat_rows,
    summarize,
    write_jsonl,
)

DEFAULT_USED_WORKLOAD = REPO_ROOT / "workloads/mix_eval_longgap_oh59_g150_r1050"
DEFAULT_OUT_ROOT = REPO_ROOT / "workloads/ratio_sweep_v4flash_unseen"


def _messages(turn: Turn) -> list[dict[str, Any]]:
    return list(turn.prompt_body.get("messages") or [])


def _is_exact_growth(prev: Turn, nxt: Turn) -> bool:
    a = _messages(prev)
    b = _messages(nxt)
    return len(a) < len(b) and a == b[: len(a)]


def split_strict_segments(
    turns: list[Turn],
    meta: SessionMeta,
    *,
    min_turns: int,
) -> list[tuple[list[Turn], SessionMeta]]:
    """Split at context resets and retain exact-prefix segments."""
    if not turns:
        return []
    runs: list[list[Turn]] = []
    current = [turns[0]]
    for prev, nxt in zip(turns, turns[1:]):
        if _is_exact_growth(prev, nxt):
            current.append(nxt)
        else:
            runs.append(current)
            current = [nxt]
    runs.append(current)

    out: list[tuple[list[Turn], SessionMeta]] = []
    for segment_idx, run in enumerate(runs):
        if len(run) < min_turns:
            continue
        sid = f"{meta.session_id}:strict{segment_idx:03d}"
        rebased = [
            replace(
                turn,
                session_id=sid,
                turn_idx=i,
                session_start_s=0.0,
                pre_gap_s=0.0 if i == 0 else turn.pre_gap_s,
            )
            for i, turn in enumerate(run)
        ]
        source = dict(meta.source)
        source.update(
            {
                "parent_session_id": meta.session_id,
                "strict_segment_index": segment_idx,
                "original_turn_start": run[0].turn_idx,
                "original_turn_end": run[-1].turn_idx,
            }
        )
        out_meta = replace(
            meta,
            session_id=sid,
            session_start_s=0.0,
            n_turns=len(rebased),
            orig_span_s=round(sum(t.pre_gap_s for t in rebased), 6),
            max_tokens_sum=sum(t.max_tokens for t in rebased),
            source=source,
        )
        out.append((rebased, out_meta))
    return out


def load_used_openhands_hashes(workload_dir: Path) -> set[str]:
    hashes: set[str] = set()
    with (workload_dir / "sessions.jsonl").open() as f:
        for line in f:
            row = json.loads(line)
            if row.get("traffic_class") != "openhands":
                continue
            digest = (row.get("source") or {}).get("content_sha256")
            if digest:
                hashes.add(str(digest))
    return hashes


def load_used_request_hashes(workload_dir: Path) -> set[str]:
    hashes: set[str] = set()
    with (workload_dir / "sessions.jsonl").open() as f:
        for line in f:
            row = json.loads(line)
            if row.get("traffic_class") != "request":
                continue
            digest = (row.get("source") or {}).get("conversation_hash")
            if digest:
                hashes.add(str(digest))
    return hashes


def build_unseen_openhands(
    *,
    used_workload: Path,
    min_segment_turns: int,
) -> tuple[list[tuple[list[Turn], SessionMeta]], dict[str, Any]]:
    used = load_used_openhands_hashes(used_workload)
    unseen: list[tuple[str, Path]] = [
        (digest, path)
        for digest, path in list_openhands_unique(SKILLSBENCH_V11)
        if digest not in used
    ]
    segments: list[tuple[list[Turn], SessionMeta]] = []
    for digest, path in unseen:
        loaded = load_agent_session(
            path,
            rel_root=REPO_ROOT,
            traffic_class="openhands",
            content_sha256=digest,
        )
        if loaded is None:
            continue
        segments.extend(
            split_strict_segments(
                loaded[0],
                loaded[1],
                min_turns=min_segment_turns,
            )
        )
    info = {
        "all_unique_v4flash_trajectories": len(list_openhands_unique(SKILLSBENCH_V11)),
        "used_content_hashes": len(used),
        "unseen_trajectories": len(unseen),
        "strict_segments": len(segments),
        "strict_segment_calls": sum(meta.n_turns for _, meta in segments),
        "min_segment_turns": min_segment_turns,
    }
    return segments, info


def build_unseen_requests(
    *,
    used_workload: Path,
    wildchat_dir: Path,
    required_calls: int,
    seed: int,
    max_turns: int,
    gap_cap_s: float,
) -> tuple[list[tuple[list[Turn], SessionMeta]], dict[str, Any]]:
    used = load_used_request_hashes(used_workload)
    candidates: list[dict[str, Any]] = []
    seen = set(used)
    for pick in iter_wildchat_index(wildchat_dir, max_turns=max_turns):
        digest = str(pick.get("conversation_hash") or "")
        if not digest or digest in seen:
            continue
        seen.add(digest)
        candidates.append(pick)

    rng = random.Random(seed)
    rng.shuffle(candidates)
    sessions: list[tuple[list[Turn], SessionMeta]] = []
    total_calls = 0
    cursor = 0
    batch_size = 512
    target_pool_calls = max(required_calls + 500, int(required_calls * 1.25))
    while total_calls < target_pool_calls and cursor < len(candidates):
        picks = candidates[cursor : cursor + batch_size]
        cursor += len(picks)
        convs = load_wildchat_rows(wildchat_dir, picks)
        for pick, conv in zip(picks, convs):
            loaded = build_request_session(
                conv,
                pick,
                gap_cap_s=gap_cap_s,
                max_tokens_cap=4096,
            )
            if loaded is not None:
                sessions.append(loaded)
                total_calls += loaded[1].n_turns
    if total_calls < required_calls:
        raise SystemExit(
            f"unseen WildChat pool has only {total_calls} calls; need {required_calls}"
        )
    info = {
        "excluded_conversation_hashes": len(used),
        "selected_pool_sessions": len(sessions),
        "selected_pool_calls": total_calls,
        "request_max_turns": max_turns,
        "request_gap_cap_s": gap_cap_s,
    }
    return sessions, info


def choose_near_calls(
    sessions: list[tuple[list[Turn], SessionMeta]],
    target: int,
) -> list[tuple[list[Turn], SessionMeta]]:
    """Deterministic subset-sum selection nearest to the target call count."""
    if target <= 0:
        return []
    max_weight = max(meta.n_turns for _, meta in sessions)
    limit = target + max_weight
    previous: dict[int, tuple[int, int] | None] = {0: None}
    for idx, (_, meta) in enumerate(sessions):
        weight = meta.n_turns
        for total in sorted(list(previous), reverse=True):
            nxt = total + weight
            if nxt <= limit and nxt not in previous:
                previous[nxt] = (total, idx)
    best = min(previous, key=lambda total: (abs(total - target), total > target, total))
    chosen_indices: list[int] = []
    cursor = best
    while cursor:
        link = previous[cursor]
        assert link is not None
        cursor, idx = link
        chosen_indices.append(idx)
    return [sessions[i] for i in sorted(chosen_indices)]


def assign_wave_starts(
    sessions: list[tuple[list[Turn], SessionMeta]],
    *,
    horizon_s: float,
    n_waves: int,
    wave_width_s: float,
    seed: int,
) -> list[tuple[list[Turn], SessionMeta]]:
    """Spread session starts over deterministic mixed waves."""
    by_class: dict[str, list[int]] = {}
    for idx, (_, meta) in enumerate(sessions):
        by_class.setdefault(meta.traffic_class, []).append(idx)
    rng = random.Random(seed)
    waves: list[list[int]] = [[] for _ in range(n_waves)]
    for indices in by_class.values():
        indices = list(indices)
        rng.shuffle(indices)
        for i, idx in enumerate(indices):
            waves[i % n_waves].append(idx)

    starts: dict[int, float] = {}
    for wave_idx, indices in enumerate(waves):
        indices.sort(
            key=lambda idx: (
                sessions[idx][1].traffic_class,
                sessions[idx][1].session_id,
            )
        )
        anchor = 0.0 if n_waves == 1 else wave_idx * horizon_s / (n_waves - 1)
        wave_start = min(anchor, max(0.0, horizon_s - wave_width_s))
        dt = 0.0 if len(indices) <= 1 else wave_width_s / (len(indices) - 1)
        for i, idx in enumerate(indices):
            starts[idx] = round(wave_start + i * dt, 6)

    out: list[tuple[list[Turn], SessionMeta]] = []
    for idx, (turns, meta) in enumerate(sessions):
        start = starts[idx]
        out.append(
            (
                [replace(turn, session_start_s=start) for turn in turns],
                replace(meta, session_start_s=start),
            )
        )
    return out


def ratio_name(ratio: float) -> str:
    return f"agent_{int(round(ratio * 100)):03d}"


def write_workload(
    *,
    out_dir: Path,
    sessions: list[tuple[list[Turn], SessionMeta]],
    ratio_target: float,
    target_calls: int,
    horizon_s: float,
    n_waves: int,
    wave_width_s: float,
    seed: int,
    oh_info: dict[str, Any],
    request_info: dict[str, Any],
    used_workload: Path,
) -> dict[str, Any]:
    turns = [turn for group, _ in sessions for turn in group]
    metas = [meta for _, meta in sessions]
    turns.sort(key=lambda t: (t.session_start_s, t.session_id, t.turn_idx))
    metas.sort(key=lambda m: (m.session_start_s, m.session_id))
    out_dir.mkdir(parents=True, exist_ok=True)
    workload_sha = write_jsonl(out_dir / "workload.jsonl", [asdict(t) for t in turns])
    sessions_sha = write_jsonl(out_dir / "sessions.jsonl", [asdict(m) for m in metas])
    summary = summarize(metas, turns)
    n_agent_calls = int(summary["n_turns_by_class"].get("openhands", 0))
    n_request_calls = int(summary["n_turns_by_class"].get("request", 0))
    actual_total = n_agent_calls + n_request_calls
    spec = {
        "name": out_dir.name,
        "protocol": "v4flash-unseen-strict-segment-ratio-v1",
        "seed": seed,
        "target_calls": target_calls,
        "target_agent_call_fraction": ratio_target,
        "actual_agent_call_fraction": (
            n_agent_calls / actual_total if actual_total else 0.0
        ),
        "n_agent_calls": n_agent_calls,
        "n_request_calls": n_request_calls,
        "arrival": {
            "type": "frozen",
            "horizon_s": horizon_s,
            "n_waves": n_waves,
            "wave_width_s": wave_width_s,
            "note": "Replay with --arrival frozen; starts are baked into workload.jsonl.",
        },
        "sources": {
            "used_model_workload_excluded": str(used_workload.relative_to(REPO_ROOT)),
            "openhands": oh_info,
            "request": request_info,
        },
        "summary": summary,
    }
    spec_text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    (out_dir / "spec.json").write_text(spec_text, encoding="utf-8")
    manifest = {
        "name": out_dir.name,
        "workload_jsonl_sha256": workload_sha,
        "sessions_jsonl_sha256": sessions_sha,
        "spec_json_sha256": hashlib.sha256(spec_text.encode()).hexdigest(),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return spec


def parse_ratios(values: Iterable[str]) -> list[float]:
    ratios = [float(value) for value in values]
    for value in ratios:
        if not 0.0 <= value <= 1.0:
            raise SystemExit(f"ratio must be in [0,1], got {value}")
    return ratios


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    p.add_argument("--used-workload", type=Path, default=DEFAULT_USED_WORKLOAD)
    p.add_argument("--wildchat-dir", type=Path, default=DEFAULT_WILDCHAT_DIR)
    p.add_argument("--target-calls", type=int, default=2000)
    p.add_argument("--min-segment-turns", type=int, default=12)
    p.add_argument(
        "--ratios",
        nargs="+",
        default=[f"{i / 10:.1f}" for i in range(11)],
    )
    p.add_argument("--horizon-s", type=float, default=10800.0)
    p.add_argument("--arrival-waves", type=int, default=9)
    p.add_argument("--wave-width-s", type=float, default=10.0)
    p.add_argument("--request-max-turns", type=int, default=8)
    p.add_argument("--request-gap-cap-s", type=float, default=30.0)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    out_root = args.out_root if args.out_root.is_absolute() else REPO_ROOT / args.out_root
    used_workload = (
        args.used_workload
        if args.used_workload.is_absolute()
        else REPO_ROOT / args.used_workload
    )
    wildchat_dir = (
        args.wildchat_dir
        if args.wildchat_dir.is_absolute()
        else REPO_ROOT / args.wildchat_dir
    )
    ratios = parse_ratios(args.ratios)
    target_calls = int(args.target_calls)

    print("[openhands] build unseen strict-prefix segment pool", flush=True)
    oh_sessions, oh_info = build_unseen_openhands(
        used_workload=used_workload,
        min_segment_turns=int(args.min_segment_turns),
    )
    print(json.dumps(oh_info, indent=2), flush=True)
    if sum(meta.n_turns for _, meta in oh_sessions) < target_calls:
        raise SystemExit(
            "unseen strict OpenHands segments cannot satisfy ratio=1 target: "
            f"{sum(meta.n_turns for _, meta in oh_sessions)} < {target_calls}"
        )

    print("[request] build unseen WildChat pool", flush=True)
    request_sessions, request_info = build_unseen_requests(
        used_workload=used_workload,
        wildchat_dir=wildchat_dir,
        required_calls=target_calls,
        seed=int(args.seed),
        max_turns=int(args.request_max_turns),
        gap_cap_s=float(args.request_gap_cap_s),
    )
    print(json.dumps(request_info, indent=2), flush=True)

    specs = []
    for ratio in ratios:
        agent_target = int(round(target_calls * ratio))
        request_target = target_calls - agent_target
        selected_oh = choose_near_calls(oh_sessions, agent_target)
        selected_request = choose_near_calls(request_sessions, request_target)
        selected = assign_wave_starts(
            selected_oh + selected_request,
            horizon_s=float(args.horizon_s),
            n_waves=int(args.arrival_waves),
            wave_width_s=float(args.wave_width_s),
            seed=int(args.seed),
        )
        out_dir = out_root / ratio_name(ratio)
        spec = write_workload(
            out_dir=out_dir,
            sessions=selected,
            ratio_target=ratio,
            target_calls=target_calls,
            horizon_s=float(args.horizon_s),
            n_waves=int(args.arrival_waves),
            wave_width_s=float(args.wave_width_s),
            seed=int(args.seed),
            oh_info=oh_info,
            request_info=request_info,
            used_workload=used_workload,
        )
        specs.append(spec)
        print(
            f"[write] {out_dir.relative_to(REPO_ROOT)} "
            f"agent={spec['n_agent_calls']} request={spec['n_request_calls']} "
            f"fraction={spec['actual_agent_call_fraction']:.6f}",
            flush=True,
        )

    index = {
        "protocol": "v4flash-unseen-strict-segment-ratio-v1",
        "target_calls": target_calls,
        "ratios": [
            {
                "name": spec["name"],
                "target": spec["target_agent_call_fraction"],
                "actual": spec["actual_agent_call_fraction"],
                "agent_calls": spec["n_agent_calls"],
                "request_calls": spec["n_request_calls"],
            }
            for spec in specs
        ],
        "openhands_pool": oh_info,
        "request_pool": request_info,
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
