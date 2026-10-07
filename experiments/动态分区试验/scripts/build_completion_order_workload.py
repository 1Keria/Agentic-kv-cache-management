#!/usr/bin/env python3
"""Build a deterministic one-turn workload from a recorded completion order.

The phased replay client sends several Agent sessions concurrently.  Cache
insertion follows response completion, so two runs can differ even when their
arrival plan is identical.  This utility freezes one observed completion order
while keeping every original prompt body and traffic class unchanged.  Each
row becomes an independent one-turn session; the full prompt already contains
the conversation history, so this changes client scheduling without changing
the prefix bytes presented to the cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload-dir", type=Path, required=True)
    parser.add_argument("--replay-jsonl", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    workload_dir = args.workload_dir.resolve()
    source_path = workload_dir / "workload.jsonl"
    if not source_path.is_file():
        raise SystemExit(f"missing workload: {source_path}")
    source_rows = read_jsonl(source_path)
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for row in source_rows:
        key = (str(row["session_id"]), int(row["turn_idx"]))
        if key in by_key:
            raise SystemExit(f"duplicate workload key: {key}")
        by_key[key] = row

    replay_rows = read_jsonl(args.replay_jsonl.resolve())
    ordered: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, int]] = set()
    for replay_row in replay_rows:
        key = (str(replay_row["session_id"]), int(replay_row["turn_index"]))
        if key in seen:
            raise SystemExit(f"duplicate replay key: {key}")
        if key not in by_key:
            raise SystemExit(f"replay row is absent from workload: {key}")
        seen.add(key)
        phase = str(replay_row.get("phase") or "")
        if phase not in {"ordinary_warm", "agent_pressure", "ordinary_return"}:
            raise SystemExit(f"unsupported or missing phase for {key}: {phase!r}")
        ordered.append((phase, by_key[key]))
    if len(seen) != len(by_key):
        missing = sorted(set(by_key) - seen)
        raise SystemExit(f"replay is missing {len(missing)} workload rows; first={missing[:3]}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_rows: list[dict[str, Any]] = []
    phase_sessions: dict[str, list[str]] = {
        "ordinary_warm": [],
        "agent_pressure": [],
        "ordinary_return": [],
    }
    for ordinal, (phase, original) in enumerate(ordered):
        session_id = f"completion_order:{ordinal:04d}"
        row = dict(original)
        row["session_id"] = session_id
        row["turn_idx"] = 0
        row["session_start_s"] = 0.0
        row["pre_gap_s"] = 0.0
        # Keep the original class and prompt body.  The unique ID is only a
        # client/request label; matching is still performed on token prefixes.
        output_rows.append(row)
        phase_sessions[phase].append(session_id)

    workload_path = output_dir / "workload.jsonl"
    workload_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in output_rows)
    )
    sessions = {str(row["session_id"]): str(row["traffic_class"]) for row in output_rows}
    manifest = {
        "name": "completion_order_frozen_one_turn",
        "protocol": "dynamic-partition-controlled-v2-completion-order",
        "source_workload": str(source_path),
        "source_workload_sha256": sha256_file(source_path),
        "source_replay_jsonl": str(args.replay_jsonl.resolve()),
        "source_replay_jsonl_sha256": sha256_file(args.replay_jsonl.resolve()),
        "workload_jsonl_sha256": sha256_file(workload_path),
        "n_turns": len(output_rows),
        "n_sessions": len(sessions),
        "n_sessions_by_class": {
            traffic_class: sum(value == traffic_class for value in sessions.values())
            for traffic_class in sorted(set(sessions.values()))
        },
        "transformation": {
            "type": "freeze_recorded_completion_order",
            "one_turn_sessions": True,
            "prompt_bodies_unchanged": True,
            "original_session_ids_preserved_as_metadata_only": False,
            "source_completion_order_is_observational": True,
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (output_dir / "phase_assignment.json").write_text(
        json.dumps(
            {
                "source": str(args.replay_jsonl.resolve()),
                "phases": [
                    {
                        "name": name,
                        "start_s": 0.0,
                        "end_s": 0.0,
                        "traffic_class": "request" if name != "agent_pressure" else "agent",
                        "session_ids": ids,
                    }
                    for name, ids in phase_sessions.items()
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    (output_dir / "replay_plan.json").write_text(
        json.dumps(
            {
                "name": "frozen_completion_order",
                "phases": [
                    {
                        "name": "ordinary_warm",
                        "execution": "serial",
                        "session_ids": phase_sessions["ordinary_warm"],
                    },
                    {
                        "name": "agent_pressure",
                        "execution": "serial",
                        "session_ids": phase_sessions["agent_pressure"],
                    },
                    {
                        "name": "ordinary_return",
                        "execution": "serial",
                        "session_ids": phase_sessions["ordinary_return"],
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
