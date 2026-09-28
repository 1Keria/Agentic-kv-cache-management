#!/usr/bin/env python3
"""Freeze explicit session arrivals; only smoke mode selects a tiny default."""

import argparse
import gzip
import json
import math
import os
from pathlib import Path

from prepare_data import ROOT, canonical_digest, digest_file, save_json

POOL = ROOT / "data/encoded/sglang_0513_thinking_max_v1/manifest_all.json"


def read_rows(entry: dict) -> list[dict]:
    path = (ROOT / entry["path"]).resolve()
    if not path.is_relative_to(ROOT) or digest_file(path) != entry["sha256"]:
        raise ValueError("Encoded session path/hash mismatch")
    with gzip.open(path, "rt") as stream:
        rows = [json.loads(line) for line in stream]
    if len(rows) != entry["requests"]:
        raise ValueError("Session request count mismatch")
    for turn, row in enumerate(rows):
        if row["turn_index"] != turn or row["session_id"] != entry["session_id"]:
            raise ValueError("Session order/identity mismatch")
        if not row["input_ids"] or canonical_digest(row["input_ids"]) != row["input_ids_sha256"]:
            raise ValueError("Input token hash mismatch")
        if row["prompt_tokens"] != len(row["input_ids"]):
            raise ValueError("Input token count mismatch")
        if type(row["output_tokens"]) is not int or row["output_tokens"] <= 0:
            raise ValueError("Missing positive output length")
        gap = row["wait_after_previous_response_seconds"]
        if turn and (not isinstance(gap, (int, float)) or not math.isfinite(gap) or gap < 0):
            raise ValueError("Missing/invalid dependency interval")
    return rows


def timing_scale(workload: dict) -> float:
    """Return the frozen replay-time scale without changing encoded source gaps."""
    transform = workload.get("timing_transform") or {}
    scale = transform.get("inter_request_gap_scale", 1.0)
    if type(scale) not in {int, float} or not math.isfinite(scale) or scale <= 0 or scale > 1:
        raise ValueError("Invalid replay timing scale")
    return float(scale)


def effective_gap_seconds(row: dict, workload: dict) -> float | None:
    gap = row["wait_after_previous_response_seconds"]
    if gap is None:
        return None
    return gap * timing_scale(workload)


def build(pool: dict, selection: dict, pool_hash: str) -> dict:
    purpose = selection["purpose"]
    if purpose not in {"smoke", "calibration", "formal"}:
        raise ValueError("Unknown workload purpose")
    entries = {entry["session_id"]: entry for entry in pool["sessions"]}
    sessions = []
    seen = set()
    for chosen in selection["sessions"]:
        session_id = chosen["session_id"]
        if session_id in seen:
            raise ValueError("Duplicating sessions is prohibited")
        seen.add(session_id)
        entry = entries[session_id]
        expected_split = "evaluation" if purpose == "formal" else "calibration"
        if entry["split"] != expected_split:
            raise ValueError("Wrong task-group split for workload purpose")
        offset = chosen["start_offset_seconds"]
        if not isinstance(offset, (int, float)) or not math.isfinite(offset) or offset < 0:
            raise ValueError("Invalid explicit session arrival")
        rows = read_rows(entry)
        limit = min(2, len(rows)) if purpose == "smoke" else len(rows)
        sessions.append({**entry, "start_offset_seconds": offset, "replay_requests": limit})
    if not sessions:
        raise ValueError("No sessions selected")
    return {"schema": 1, "purpose": purpose, "frozen": True,
            "pool_manifest_sha256": pool_hash, "sessions": sessions,
            "requests": sum(entry["replay_requests"] for entry in sessions),
            "output_token_cap": 32 if purpose == "smoke" else None,
            "complete_sessions": purpose != "smoke", "sampling_seed": 42,
            "temperature": 0, "ignore_eos": True,
            "arrival_basis": "explicit_synthetic_session_starts",
            "dependency_basis": "previous_local_completion_plus_recorded_relative_gap",
            "time_basis": "recorded_callback_relative_interval_version_unverified",
            "source_template_reproduced": False,
            "historical_outputs_replaced_by_local_generation": False,
            "formal_protocol_accepted": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.smoke == bool(args.selection):
        parser.error("Choose exactly one of --smoke or --selection")
    destination = args.output.resolve()
    if not destination.is_relative_to(ROOT) or destination.exists():
        raise ValueError("Output must be a new file inside this experiment")
    pool = json.loads(POOL.read_text())
    if args.smoke:
        candidates = sorted((entry for entry in pool["sessions"] if entry["split"] == "calibration"),
                            key=lambda entry: entry["session_id"])
        selection = {"purpose": "smoke", "sessions": [
            {"session_id": entry["session_id"], "start_offset_seconds": index * 1.0}
            for index, entry in enumerate(candidates[:2])]}
    else:
        selection = json.loads(args.selection.read_text())
    workload = build(pool, selection, digest_file(POOL))
    save_json(destination, workload)
    print(json.dumps({"workload": str(destination), "requests": workload["requests"],
                      "purpose": workload["purpose"]}))


if __name__ == "__main__":
    main()
