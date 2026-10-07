#!/usr/bin/env python3
"""Build a controlled mixed workload with reusable Agent and request prefixes.

The source conversations remain real traces.  Request sessions are selected
from real multi-turn sessions, prefixed with a deterministic per-session
header large enough to survive page-level matching, then replayed twice around
the real Agent sessions.  The second request wave uses identical prompt bodies
under new session ids, so its hit rate measures whether the first wave survived
the Agent pressure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


AGENT_CLASSES = {"agent", "openhands", "glm"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def make_header(index: int, chars: int) -> str:
    # The counter makes each logical request session physically distinct while
    # the exact same header is reused by its second wave.
    seed = f"REQ_CACHE_STRESS_SESSION_{index:03d}_"
    pieces: list[str] = []
    cursor = 0
    while cursor < chars:
        block = f"{seed}BLOCK_{cursor // 64:06d}_a7f3c91d2e5b4a8c "
        pieces.append(block)
        cursor += len(block)
    return (
        "This is a deterministic ordinary-request cache stress prefix. "
        "It carries no agent instructions and is repeated exactly for the "
        "same logical session. "
        + "".join(pieces)[:chars]
    )


def with_header(row: dict[str, Any], header: str, session_id: str) -> dict[str, Any]:
    out = dict(row)
    body = dict(row.get("prompt_body") or {})
    messages = [dict(message) for message in body.get("messages") or []]
    messages.insert(0, {"role": "system", "content": header})
    body["messages"] = messages
    out["prompt_body"] = body
    out["session_id"] = session_id
    out["traffic_class"] = "request"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--request-sessions", type=int, default=8)
    parser.add_argument("--request-turns", type=int, default=4)
    parser.add_argument("--header-chars", type=int, default=32000)
    parser.add_argument(
        "--request-selection",
        choices=("longest", "shortest"),
        default="longest",
        help="Select request sessions by the serialized size of the selected turns.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--request-start-spacing-s", type=float, default=0.8)
    parser.add_argument("--request-first-start-s", type=float, default=0.0)
    parser.add_argument("--request-second-start-s", type=float, default=120.0)
    parser.add_argument("--agent-start-s", type=float, default=50.0)
    parser.add_argument("--agent-end-s", type=float, default=110.0)
    parser.add_argument(
        "--return-last-prompt", action="store_true",
        help="Return to the final warmup prompt, rather than rewind the session.",
    )
    parser.add_argument(
        "--background-workload-dir", type=Path,
        help="Optional frozen workload whose ordinary sessions provide scan pressure.",
    )
    args = parser.parse_args()
    if min(args.request_sessions, args.request_turns, args.header_chars) <= 0:
        raise SystemExit("request sessions, turns, and header chars must be positive")
    if args.request_start_spacing_s < 0 or args.agent_end_s < args.agent_start_s:
        raise SystemExit("invalid session arrival intervals")

    source = args.source.resolve()
    rows = read_rows(source)
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order: list[str] = []
    for row in rows:
        sid = str(row["session_id"])
        if sid not in sessions:
            order.append(sid)
        sessions[sid].append(row)

    agent_ids = [sid for sid in order if sessions[sid][0]["traffic_class"] in AGENT_CLASSES]
    request_candidates = [
        sid for sid in order
        if sessions[sid][0]["traffic_class"] == "request" and len(sessions[sid]) >= args.request_turns
    ]
    if len(request_candidates) < args.request_sessions:
        raise SystemExit(
            f"need {args.request_sessions} request sessions with at least "
            f"{args.request_turns} turns, found {len(request_candidates)}"
        )
    # Select real request conversations deterministically.  The short option is
    # useful for a cache-preservation control: it lets the terminal working set
    # fit inside the ordinary SWA guarantee before pressure is introduced.
    def selection_key(sid: str) -> tuple[int, str]:
        selected = sorted(sessions[sid], key=lambda row: int(row["turn_idx"]))[: args.request_turns]
        size = sum(len(json.dumps(row.get("prompt_body") or {}, ensure_ascii=False)) for row in selected)
        return (size, sid)

    request_ids = sorted(
        request_candidates,
        key=(lambda sid: (selection_key(sid)[0], sid))
        if args.request_selection == "shortest"
        else (lambda sid: (-len(sessions[sid]), sid)),
    )[: args.request_sessions]

    output_rows: list[dict[str, Any]] = []
    phase_rows: dict[str, list[str]] = {"request_first": [], "agent_middle": [], "request_second": []}
    rng = random.Random(args.seed)
    request_ids = list(request_ids)
    rng.shuffle(request_ids)

    # First ordinary wave: keep the cache warm before the Agent pressure.
    for index, sid in enumerate(request_ids):
        logical = f"request_reuse:{index:03d}"
        header = make_header(index, args.header_chars)
        wave_sid = f"{logical}:first"
        selected = sorted(sessions[sid], key=lambda row: int(row["turn_idx"]))[: args.request_turns]
        phase_rows["request_first"].append(wave_sid)
        for row in selected:
            item = with_header(row, header, wave_sid)
            item["session_start_s"] = round(
                args.request_first_start_s + index * args.request_start_spacing_s, 6
            )
            output_rows.append(item)

        # Terminal probes keep the latest reusable endpoint available in SWA.
        # Rewinding an older prompt is a separate, intentionally harder case.
        wave_sid = f"{logical}:second"
        phase_rows["request_second"].append(wave_sid)
        returning = [selected[-1]] * len(selected) if args.return_last_prompt else selected
        for probe_index, row in enumerate(returning):
            item = with_header(row, header, wave_sid)
            item["turn_idx"] = probe_index
            item["pre_gap_s"] = 0.0 if probe_index == 0 else row["pre_gap_s"]
            item["session_start_s"] = round(
                args.request_second_start_s + index * args.request_start_spacing_s, 6
            )
            output_rows.append(item)

    # Real Agent sessions run between the two request waves.
    for index, sid in enumerate(agent_ids):
        start = args.agent_start_s + (
            (args.agent_end_s - args.agent_start_s) * index / max(len(agent_ids) - 1, 1)
        )
        phase_rows["agent_middle"].append(sid)
        for row in sessions[sid]:
            item = dict(row)
            item["session_start_s"] = round(start, 6)
            output_rows.append(item)

    background = None
    background_phases: list[dict[str, Any]] = []
    if args.background_workload_dir:
        background_path = args.background_workload_dir.resolve() / "workload.jsonl"
        background_rows = read_rows(background_path)
        background_rows = [row for row in background_rows if row["traffic_class"] == "request"]
        output_rows.extend(background_rows)
        background = {
            "workload": str(background_path),
            "sha256": sha256_file(background_path),
            "n_turns": len(background_rows),
            "prompt_bodies_unchanged": True,
        }
        assignment_path = background_path.parent / "phase_assignment.json"
        if assignment_path.is_file():
            assignment = json.loads(assignment_path.read_text())
            existing_ids = {row["session_id"] for row in background_rows}
            for phase in assignment["phases"]:
                ids = [sid for sid in phase["session_ids"] if sid in existing_ids]
                if ids:
                    background_phases.append({**phase, "name": "background_" + phase["name"], "session_ids": ids})

    output_rows.sort(key=lambda row: (float(row["session_start_s"]), str(row["session_id"]), int(row["turn_idx"])))
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    workload = out_dir / "workload.jsonl"
    with workload.open("w") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    manifest = {
        "name": "bidirectional_reuse_phase_stress",
        "protocol": "dynamic-partition-controlled-v2",
        "source_workload": str(source),
        "source_workload_sha256": sha256_file(source),
        "workload_jsonl_sha256": sha256_file(workload),
        "n_turns": len(output_rows),
        "n_sessions": len({str(row["session_id"]) for row in output_rows}),
        "n_sessions_by_class": {
            "agent": len(agent_ids),
            "request": len({row["session_id"] for row in output_rows if row["traffic_class"] == "request"}),
        },
        "transformation": {
            "type": "real_multiturn_bidirectional_reuse",
            "request_sessions": len(request_ids),
            "request_turns_per_wave": args.request_turns,
            "header_chars": args.header_chars,
            "request_wave_intervals_s": [
                [start, start + (len(request_ids) - 1) * args.request_start_spacing_s]
                for start in (args.request_first_start_s, args.request_second_start_s)
            ],
            "agent_interval_s": [args.agent_start_s, args.agent_end_s],
            "return_mode": "repeat_terminal_prompt" if args.return_last_prompt else "rewind_all_turns",
            "second_wave_prompts_match": "last_warmup_prompt" if args.return_last_prompt else "corresponding_warmup_turn",
            "agent_prompt_bodies_unchanged": True,
            "background": background,
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (out_dir / "phase_assignment.json").write_text(
        json.dumps(
            {
                "seed": args.seed,
                "phases": [
                    {"name": "request_first", "start_s": args.request_first_start_s, "end_s": args.request_first_start_s + (len(request_ids) - 1) * args.request_start_spacing_s, "traffic_class": "request", "session_ids": phase_rows["request_first"]},
                    {"name": "agent_middle", "start_s": args.agent_start_s, "end_s": args.agent_end_s, "traffic_class": "agent", "session_ids": phase_rows["agent_middle"]},
                    {"name": "request_second", "start_s": args.request_second_start_s, "end_s": args.request_second_start_s + (len(request_ids) - 1) * args.request_start_spacing_s, "traffic_class": "request", "session_ids": phase_rows["request_second"]},
                    *background_phases,
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    (out_dir / "replay_plan.json").write_text(
        json.dumps(
            {
                "name": "ordinary_warm_agent_pressure_ordinary_return",
                "phases": [
                    {
                        "name": "ordinary_warm",
                        "execution": "serial",
                        "session_ids": [f"request_reuse:{i:03d}:first" for i in range(len(request_ids))],
                        "require_warm_hit": 0.9,
                    },
                    {
                        "name": "agent_pressure",
                        "execution": "parallel",
                        "session_ids": phase_rows["agent_middle"],
                    },
                    {
                        "name": "ordinary_return",
                        "execution": "serial",
                        "session_ids": [f"request_reuse:{i:03d}:second" for i in range(len(request_ids))],
                        "require_first_hit": 0.5,
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(out_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
