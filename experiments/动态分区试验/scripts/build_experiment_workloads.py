#!/usr/bin/env python3
"""Build controlled workloads for dynamic request-cache partition experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_workload(
    output_dir: Path,
    rows: list[dict[str, Any]],
    *,
    name: str,
    source_path: Path,
    transformation: dict[str, Any],
    phase_assignment: dict[str, Any] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    workload_path = output_dir / "workload.jsonl"
    with workload_path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    sessions: dict[str, str] = {}
    for row in rows:
        sessions.setdefault(str(row["session_id"]), str(row["traffic_class"]))
    manifest = {
        "name": name,
        "protocol": "dynamic-partition-controlled-v1",
        "source_workload": str(source_path),
        "source_workload_sha256": sha256_file(source_path),
        "workload_jsonl_sha256": sha256_file(workload_path),
        "n_turns": len(rows),
        "n_sessions": len(sessions),
        "n_sessions_by_class": {
            traffic_class: sum(value == traffic_class for value in sessions.values())
            for traffic_class in sorted(set(sessions.values()))
        },
        "transformation": transformation,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    if phase_assignment is not None:
        (output_dir / "phase_assignment.json").write_text(
            json.dumps(phase_assignment, ensure_ascii=False, indent=2) + "\n"
        )


def build_scaled(rows: list[dict[str, Any]], scale: float) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        row["session_start_s"] = round(float(row["session_start_s"]) * scale, 6)
        result.append(row)
    return result


def evenly_spaced(sessions: list[str], start: float, end: float) -> dict[str, float]:
    if not sessions:
        return {}
    if len(sessions) == 1:
        return {sessions[0]: start}
    step = (end - start) / (len(sessions) - 1)
    return {session_id: round(start + index * step, 6) for index, session_id in enumerate(sessions)}


def build_phased(
    rows: list[dict[str, Any]], seed: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    session_order: list[str] = []
    for row in rows:
        session_id = str(row["session_id"])
        if session_id not in sessions:
            session_order.append(session_id)
        sessions[session_id].append(row)

    agent_sessions = [
        sid
        for sid in session_order
        if str(sessions[sid][0]["traffic_class"]) in {"agent", "openhands", "glm"}
    ]
    request_sessions = [sid for sid in session_order if sid not in set(agent_sessions)]
    shuffled_requests = list(request_sessions)
    random.Random(seed).shuffle(shuffled_requests)
    midpoint = len(shuffled_requests) // 2
    request_first = shuffled_requests[:midpoint]
    request_last = shuffled_requests[midpoint:]

    starts = {}
    starts.update(evenly_spaced(request_first, 0.0, 40.0))
    starts.update(evenly_spaced(agent_sessions, 90.0, 110.0))
    starts.update(evenly_spaced(request_last, 300.0, 340.0))

    result: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        row["session_start_s"] = starts[str(row["session_id"])]
        result.append(row)

    assignment = {
        "seed": seed,
        "phases": [
            {
                "name": "request_first",
                "start_s": 0.0,
                "end_s": 40.0,
                "traffic_class": "request",
                "session_ids": request_first,
            },
            {
                "name": "agent_middle",
                "start_s": 90.0,
                "end_s": 110.0,
                "traffic_class": "agent",
                "session_ids": agent_sessions,
            },
            {
                "name": "request_last",
                "start_s": 300.0,
                "end_s": 340.0,
                "traffic_class": "request",
                "session_ids": request_last,
            },
        ],
    }
    return result, assignment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeline-scale", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    source_path = args.source_dir.resolve() / "workload.jsonl"
    if not source_path.is_file():
        raise SystemExit(f"missing source workload: {source_path}")
    if not 0 < args.timeline_scale <= 1:
        raise SystemExit("timeline scale must be in (0, 1]")
    rows = read_rows(source_path)

    scaled = build_scaled(rows, args.timeline_scale)
    write_workload(
        args.output_root / "mixed_scaled",
        scaled,
        name="token_balanced_mixed_scaled",
        source_path=source_path,
        transformation={
            "type": "scale_session_start",
            "timeline_scale": args.timeline_scale,
            "prompt_bodies_unchanged": True,
            "session_order_unchanged": True,
            "pre_gap_s_unchanged": True,
        },
    )

    phased, assignment = build_phased(rows, args.seed)
    write_workload(
        args.output_root / "request_agent_request",
        phased,
        name="request_agent_request_phases",
        source_path=source_path,
        transformation={
            "type": "request_agent_request_phases",
            "seed": args.seed,
            "phase_intervals_s": [[0.0, 40.0], [90.0, 110.0], [300.0, 340.0]],
            "prompt_bodies_unchanged": True,
            "session_turn_order_unchanged": True,
            "pre_gap_s_unchanged": True,
        },
        phase_assignment=assignment,
    )
    print(args.output_root / "mixed_scaled")
    print(args.output_root / "request_agent_request")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
