#!/usr/bin/env python3
"""Freeze task/length coverage before seeing GPU calibration measurements."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from build_workload import POOL, build, read_rows
from check_admission import validate_admission
from prepare_data import ROOT, digest_file, save_json


def stable_key(session_id: str) -> str:
    return hashlib.sha256(("calibration-v1:42:" + session_id).encode()).hexdigest()


def select_sessions(entries: list[dict], count: int = 8) -> list[dict]:
    representatives = {}
    for entry in entries:
        if entry["split"] != "calibration":
            continue
        previous = representatives.get(entry["task_id"])
        if previous is None or stable_key(entry["session_id"]) < stable_key(previous["session_id"]):
            representatives[entry["task_id"]] = entry
    ranked = sorted(representatives.values(), key=lambda entry: (entry["max_prompt_plus_output_tokens"], entry["session_id"]))
    if not 2 <= count <= len(ranked):
        raise ValueError("Need at least two distinct calibration tasks per selection")
    indices = [round(index * (len(ranked) - 1) / (count - 1)) for index in range(count)]
    selected = [ranked[index] for index in indices]
    return sorted(selected, key=lambda entry: stable_key(entry["session_id"]))


def prepare(destination: Path, config_path: Path) -> dict:
    if destination.exists() or not destination.resolve().is_relative_to(ROOT):
        raise ValueError("Use a new directory inside this experiment")
    pool = json.loads(POOL.read_text())
    config = json.loads(config_path.read_text())
    selected = select_sessions(pool["sessions"])
    selection = {"purpose": "calibration", "selection_seed": 42,
                 "selection_rule": "SHA256 trial representative per calibration task, eight equidistant length ranks",
                 "arrival_rule": "SHA256 ordered sessions, one start every 15 seconds; synthetic, not source wall clock",
                 "length_rank_rounding": "Python round, ties to even",
                 "sessions": [{"session_id": entry["session_id"], "start_offset_seconds": index * 15}
                              for index, entry in enumerate(selected)]}
    workload = build(pool, selection, digest_file(POOL))
    loaded = [(entry, read_rows(entry)) for entry in workload["sessions"]]
    admission = validate_admission(loaded, workload, {"context_length": config["context_length"],
                                   "max_total_num_tokens": config["max_total_tokens"], "page_size": config["page_size"]})
    sessions = [{"session_id": entry["session_id"], "task_id": entry["task_id"], "requests": len(rows),
                 "start_offset_seconds": entry["start_offset_seconds"],
                 "max_prompt_plus_output_tokens": max(row["prompt_tokens"] + row["output_tokens"] for row in rows),
                 "prompt_tokens_total": sum(row["prompt_tokens"] for row in rows),
                 "output_tokens_total": sum(row["output_tokens"] for row in rows),
                 "recorded_wait_sum_seconds": sum(row["wait_after_previous_response_seconds"] for row in rows[1:])}
                for entry, rows in loaded]
    summary = {"purpose": "complete_session_lru_calibration_not_formal", "sessions": sessions,
               "session_count": len(sessions), "requests": workload["requests"],
               "pool_manifest_sha256": digest_file(POOL), "config_sha256": digest_file(config_path),
               "admission": admission, "selection_uses_policy_results": False,
               "selection_uses_task_success_or_reuse": False, "waits_shortened": False,
               "output_lengths_capped": False,
               "formal_coverage_target": {"sessions": 83, "requests": 4154},
               "formal_gate_open": False,
               "warmup_scope": "Existing four-request protocol warmup; new shapes may still compile during calibration",
               "maximum_sum_of_waits_seconds": max(entry["recorded_wait_sum_seconds"] for entry in sessions)}
    destination.mkdir(parents=True)
    save_json(destination / "selection.json", selection)
    save_json(destination / "manifest.json", workload)
    save_json(destination / "preflight.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/calibration_high_server.json")
    args = parser.parse_args()
    os.umask(0o077)
    result = prepare(args.output, args.config)
    print(json.dumps({key: value for key, value in result.items() if key != "sessions"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
