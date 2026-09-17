#!/usr/bin/env python3
"""Build 11 ratio-matched daily-training workloads.

OpenHands uses all 59 V4-Flash development trajectories; the 49 previously
unseen trajectories remain final-test only. Request uses the old development
pool plus fresh WildChat conversations that do not occur in final test. GLM is
excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
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
from build_ratio_sweep_workloads import (  # noqa: E402
    assign_wave_starts,
    ratio_name,
    split_strict_segments,
)

DEFAULT_SOURCE_WORKLOAD = REPO_ROOT / "workloads/mix_eval_3h_oh59_g150_r1050"
DEFAULT_OH_SOURCE_WORKLOAD = REPO_ROOT / "workloads/mix_eval_longgap_oh59_g150_r1050"
DEFAULT_SPLIT = REPO_ROOT / "models/MLP/data/session_split.json"
DEFAULT_OUT_ROOT = REPO_ROOT / "workloads/ratio_train_v4flash"
DEFAULT_FINAL_TEST_ROOT = REPO_ROOT / "workloads/ratio_sweep_v4flash_unseen"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def load_training_openhands(
    *,
    oh_source_workload: Path,
    split: dict[str, str],
    min_segment_turns: int,
) -> tuple[list[tuple[list[Turn], SessionMeta]], dict[str, Any]]:
    development_hashes: set[str] = set()
    legacy_split_counts = {"train": 0, "test": 0}
    for row in read_jsonl(oh_source_workload / "sessions.jsonl"):
        if row.get("traffic_class") != "openhands":
            continue
        digest = str((row.get("source") or {}).get("content_sha256") or "")
        if not digest:
            raise SystemExit(f"OpenHands session missing content hash: {row['session_id']}")
        tag = split.get(str(row["session_id"]))
        if tag not in legacy_split_counts:
            raise SystemExit(f"OpenHands session missing split: {row['session_id']}")
        legacy_split_counts[tag] += 1
        development_hashes.add(digest)

    paths = dict(list_openhands_unique(SKILLSBENCH_V11))
    missing = development_hashes - paths.keys()
    if missing:
        raise SystemExit(f"{len(missing)} training OpenHands hashes missing locally")

    sessions: list[tuple[list[Turn], SessionMeta]] = []
    for digest in sorted(development_hashes):
        loaded = load_agent_session(
            paths[digest],
            rel_root=REPO_ROOT,
            traffic_class="openhands",
            content_sha256=digest,
        )
        if loaded is None:
            raise SystemExit(f"empty OpenHands trajectory: {paths[digest]}")
        sessions.extend(
            split_strict_segments(
                loaded[0],
                loaded[1],
                min_turns=min_segment_turns,
            )
        )

    info = {
        "source_trajectories": len(development_hashes),
        "legacy_split_counts": legacy_split_counts,
        "strict_segments": len(sessions),
        "strict_segment_calls": sum(meta.n_turns for _, meta in sessions),
        "min_segment_turns": min_segment_turns,
        "content_hashes": sorted(development_hashes),
    }
    return sessions, info


def load_training_requests(
    *,
    source_workload: Path,
    split: dict[str, str],
) -> tuple[list[tuple[list[Turn], SessionMeta]], dict[str, Any]]:
    development_rows: list[dict[str, Any]] = []
    legacy_split_counts = {"train": 0, "test": 0}
    for row in read_jsonl(source_workload / "sessions.jsonl"):
        if row.get("traffic_class") != "request":
            continue
        sid = str(row["session_id"])
        tag = split.get(sid)
        if tag not in legacy_split_counts:
            raise SystemExit(f"Request session missing split: {sid}")
        legacy_split_counts[tag] += 1
        development_rows.append(row)

    # Keep one deterministic row per conversation hash. The legacy test split
    # was already used for development, so it can join final training after
    # model design and hyperparameters are frozen.
    metas: dict[str, SessionMeta] = {}
    seen_train_hashes: set[str] = set()
    n_duplicate_sessions = 0
    for row in sorted(development_rows, key=lambda item: str(item["session_id"])):
        sid = str(row["session_id"])
        digest = str((row.get("source") or {}).get("conversation_hash") or "")
        if not digest:
            raise SystemExit(f"Request session missing conversation hash: {sid}")
        if digest in seen_train_hashes:
            n_duplicate_sessions += 1
            continue
        seen_train_hashes.add(digest)
        metas[sid] = SessionMeta(**row)

    turns_by_sid: dict[str, list[Turn]] = {sid: [] for sid in metas}
    for row in read_jsonl(source_workload / "workload.jsonl"):
        sid = str(row["session_id"])
        if sid in turns_by_sid:
            turns_by_sid[sid].append(Turn(**row))

    sessions: list[tuple[list[Turn], SessionMeta]] = []
    train_hashes: set[str] = set()
    for sid in sorted(metas):
        turns = sorted(turns_by_sid[sid], key=lambda turn: turn.turn_idx)
        meta = metas[sid]
        if len(turns) != meta.n_turns:
            raise SystemExit(
                f"Request turn mismatch for {sid}: {len(turns)} != {meta.n_turns}"
            )
        digest = str(meta.source.get("conversation_hash") or "")
        if not digest:
            raise SystemExit(f"Request session missing conversation hash: {sid}")
        train_hashes.add(digest)
        sessions.append((turns, meta))

    info = {
        "source_sessions": len(sessions),
        "source_calls": sum(meta.n_turns for _, meta in sessions),
        "unique_conversation_hashes": len(train_hashes),
        "legacy_split_counts": legacy_split_counts,
        "duplicate_sessions_removed": n_duplicate_sessions,
        "conversation_hashes": sorted(train_hashes),
    }
    return sessions, info


def load_final_test_request_hashes(final_test_root: Path) -> set[str]:
    hashes: set[str] = set()
    for path in sorted(final_test_root.glob("agent_*/sessions.jsonl")):
        for row in read_jsonl(path):
            if row.get("traffic_class") != "request":
                continue
            digest = str((row.get("source") or {}).get("conversation_hash") or "")
            if digest:
                hashes.add(digest)
    return hashes


def augment_training_requests(
    sessions: list[tuple[list[Turn], SessionMeta]],
    info: dict[str, Any],
    *,
    final_test_root: Path,
    wildchat_dir: Path,
    required_calls: int,
    seed: int,
) -> tuple[list[tuple[list[Turn], SessionMeta]], dict[str, Any]]:
    current_calls = sum(meta.n_turns for _, meta in sessions)
    if current_calls >= required_calls:
        return sessions, info

    import random

    development_hashes = {
        str(meta.source.get("conversation_hash") or "") for _, meta in sessions
    }
    final_test_hashes = load_final_test_request_hashes(final_test_root)
    excluded = development_hashes | final_test_hashes
    candidates: list[dict[str, Any]] = []
    seen = set(excluded)
    for pick in iter_wildchat_index(wildchat_dir, max_turns=8):
        digest = str(pick.get("conversation_hash") or "")
        if not digest or digest in seen:
            continue
        seen.add(digest)
        candidates.append(pick)

    rng = random.Random(seed)
    rng.shuffle(candidates)
    added: list[tuple[list[Turn], SessionMeta]] = []
    cursor = 0
    while current_calls + sum(meta.n_turns for _, meta in added) < required_calls + 200:
        picks = candidates[cursor : cursor + 256]
        if not picks:
            raise SystemExit("not enough disjoint WildChat requests for training")
        cursor += len(picks)
        convs = load_wildchat_rows(wildchat_dir, picks)
        for pick, conv in zip(picks, convs):
            loaded = build_request_session(
                conv,
                pick,
                gap_cap_s=30.0,
                max_tokens_cap=4096,
            )
            if loaded is not None:
                added.append(loaded)

    combined = sessions + added
    updated = dict(info)
    updated.update(
        {
            "base_development_calls": current_calls,
            "fresh_added_sessions": len(added),
            "fresh_added_calls": sum(meta.n_turns for _, meta in added),
            "source_sessions": len(combined),
            "source_calls": sum(meta.n_turns for _, meta in combined),
            "final_test_hashes_excluded": len(final_test_hashes),
            "conversation_hashes": sorted(
                str(meta.source.get("conversation_hash") or "")
                for _, meta in combined
            ),
        }
    )
    return combined, updated


def choose_near_calls(
    sessions: list[tuple[list[Turn], SessionMeta]],
    target: int,
) -> list[tuple[list[Turn], SessionMeta]]:
    """Select whole sessions with total calls nearest target."""
    if target <= 0:
        return []
    max_weight = max(meta.n_turns for _, meta in sessions)
    limit = target + max_weight
    reachable = [False] * (limit + 1)
    parent_sum = [-1] * (limit + 1)
    parent_idx = [-1] * (limit + 1)
    reachable[0] = True
    for idx, (_, meta) in enumerate(sessions):
        weight = meta.n_turns
        for total in range(limit - weight, -1, -1):
            nxt = total + weight
            if reachable[total] and not reachable[nxt]:
                reachable[nxt] = True
                parent_sum[nxt] = total
                parent_idx[nxt] = idx

    totals = [total for total, ok in enumerate(reachable) if ok]
    best = min(totals, key=lambda total: (abs(total - target), total > target, total))
    chosen: list[int] = []
    cursor = best
    while cursor:
        chosen.append(parent_idx[cursor])
        cursor = parent_sum[cursor]
    return [sessions[idx] for idx in sorted(chosen)]


def parse_ratios(values: Iterable[str]) -> list[float]:
    ratios = [float(value) for value in values]
    for ratio in ratios:
        if not 0.0 <= ratio <= 1.0:
            raise SystemExit(f"ratio must be in [0,1], got {ratio}")
    return ratios


def write_ratio_workload(
    *,
    out_dir: Path,
    sessions: list[tuple[list[Turn], SessionMeta]],
    target_ratio: float,
    target_calls: int,
    seed: int,
    horizon_s: float,
    n_waves: int,
    wave_width_s: float,
    oh_info: dict[str, Any],
    request_info: dict[str, Any],
) -> dict[str, Any]:
    turns = [turn for session_turns, _ in sessions for turn in session_turns]
    metas = [meta for _, meta in sessions]
    turns.sort(key=lambda turn: (turn.session_start_s, turn.session_id, turn.turn_idx))
    metas.sort(key=lambda meta: (meta.session_start_s, meta.session_id))
    summary = summarize(metas, turns)
    agent_calls = int(summary["n_turns_by_class"].get("openhands", 0))
    request_calls = int(summary["n_turns_by_class"].get("request", 0))
    total_calls = agent_calls + request_calls
    if total_calls != target_calls:
        raise SystemExit(
            f"{out_dir.name}: expected {target_calls} calls, got {total_calls}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    workload_sha = write_jsonl(out_dir / "workload.jsonl", [asdict(t) for t in turns])
    sessions_sha = write_jsonl(out_dir / "sessions.jsonl", [asdict(m) for m in metas])
    spec = {
        "name": out_dir.name,
        "protocol": "v4flash-ratio-matched-daily-train-v1",
        "data_role": "train",
        "seed": seed,
        "target_calls": target_calls,
        "target_agent_call_fraction": target_ratio,
        "actual_agent_call_fraction": agent_calls / total_calls,
        "n_agent_calls": agent_calls,
        "n_request_calls": request_calls,
        "n_glm_calls": 0,
        "arrival": {
            "type": "frozen",
            "horizon_s": horizon_s,
            "n_waves": n_waves,
            "wave_width_s": wave_width_s,
            "note": "Replay with --arrival frozen; starts are baked into workload.jsonl.",
        },
        "sources": {
            "openhands_train_pool": oh_info,
            "request_train_pool": request_info,
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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-workload", type=Path, default=DEFAULT_SOURCE_WORKLOAD)
    p.add_argument(
        "--openhands-source-workload",
        type=Path,
        default=DEFAULT_OH_SOURCE_WORKLOAD,
    )
    p.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    p.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    p.add_argument("--final-test-root", type=Path, default=DEFAULT_FINAL_TEST_ROOT)
    p.add_argument("--wildchat-dir", type=Path, default=DEFAULT_WILDCHAT_DIR)
    p.add_argument("--target-calls", type=int, default=2100)
    p.add_argument("--min-segment-turns", type=int, default=12)
    p.add_argument(
        "--ratios",
        nargs="+",
        default=[f"{idx / 10:.1f}" for idx in range(11)],
    )
    p.add_argument("--horizon-s", type=float, default=10800.0)
    p.add_argument("--arrival-waves", type=int, default=9)
    p.add_argument("--wave-width-s", type=float, default=10.0)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    source_workload = (
        args.source_workload
        if args.source_workload.is_absolute()
        else REPO_ROOT / args.source_workload
    )
    oh_source_workload = (
        args.openhands_source_workload
        if args.openhands_source_workload.is_absolute()
        else REPO_ROOT / args.openhands_source_workload
    )
    split_path = args.split if args.split.is_absolute() else REPO_ROOT / args.split
    out_root = args.out_root if args.out_root.is_absolute() else REPO_ROOT / args.out_root
    final_test_root = (
        args.final_test_root
        if args.final_test_root.is_absolute()
        else REPO_ROOT / args.final_test_root
    )
    wildchat_dir = (
        args.wildchat_dir
        if args.wildchat_dir.is_absolute()
        else REPO_ROOT / args.wildchat_dir
    )
    split: dict[str, str] = json.loads(split_path.read_text())
    ratios = parse_ratios(args.ratios)
    target_calls = int(args.target_calls)

    print("[pool] load OpenHands train split", flush=True)
    oh_sessions, oh_info = load_training_openhands(
        oh_source_workload=oh_source_workload,
        split=split,
        min_segment_turns=int(args.min_segment_turns),
    )
    print(json.dumps({k: v for k, v in oh_info.items() if k != "content_hashes"}, indent=2))

    print("[pool] load Request train split", flush=True)
    request_sessions, request_info = load_training_requests(
        source_workload=source_workload,
        split=split,
    )
    request_sessions, request_info = augment_training_requests(
        request_sessions,
        request_info,
        final_test_root=final_test_root,
        wildchat_dir=wildchat_dir,
        required_calls=target_calls,
        seed=int(args.seed) + 1,
    )
    print(
        json.dumps(
            {k: v for k, v in request_info.items() if k != "conversation_hashes"},
            indent=2,
        )
    )

    if sum(meta.n_turns for _, meta in oh_sessions) < target_calls:
        raise SystemExit("OpenHands training pool cannot satisfy ratio=1")
    if sum(meta.n_turns for _, meta in request_sessions) < target_calls:
        raise SystemExit("Request training pool cannot satisfy ratio=0")

    specs: list[dict[str, Any]] = []
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
        spec = write_ratio_workload(
            out_dir=out_root / ratio_name(ratio),
            sessions=selected,
            target_ratio=ratio,
            target_calls=target_calls,
            seed=int(args.seed),
            horizon_s=float(args.horizon_s),
            n_waves=int(args.arrival_waves),
            wave_width_s=float(args.wave_width_s),
            oh_info=oh_info,
            request_info=request_info,
        )
        specs.append(spec)
        print(
            f"[write] {ratio_name(ratio)} agent={spec['n_agent_calls']} "
            f"request={spec['n_request_calls']} "
            f"fraction={spec['actual_agent_call_fraction']:.6f}",
            flush=True,
        )

    index = {
        "protocol": "v4flash-ratio-matched-daily-train-v1",
        "data_role": "train",
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
        "openhands_train_pool": oh_info,
        "request_train_pool": request_info,
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
