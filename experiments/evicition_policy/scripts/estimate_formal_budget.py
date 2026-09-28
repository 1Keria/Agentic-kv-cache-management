#!/usr/bin/env python3
"""Produce a planning estimate, never an executable or measured formal workload."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

from prepare_data import ROOT, digest_file, save_json


def estimate(sessions: dict, seconds_per_output: float, spacing: int, multiplier: float) -> dict:
    order = sorted(sessions, key=lambda session: hashlib.sha256(
        ("formal-schedule-proposal-v1:42:" + session).encode()).hexdigest())
    schedule = []
    for index, session_id in enumerate(order):
        session = sessions[session_id]
        start = index * spacing
        duration = session["wait_seconds"] + multiplier * seconds_per_output * session["output_tokens"]
        schedule.append({"session_id": session_id, "task_id": session["task_id"],
                         "proposed_start_seconds": start, "estimated_end_seconds": start + duration,
                         "source_wait_seconds": session["wait_seconds"]})
    events = sorted([(entry["proposed_start_seconds"], 1) for entry in schedule]
                    + [(entry["estimated_end_seconds"], -1) for entry in schedule])
    active = 0
    peak = 0
    for _, delta in events:
        active += delta
        peak = max(peak, active)
    return {"spacing_seconds": spacing, "service_time_multiplier": multiplier,
            "estimated_makespan_hours": max(entry["estimated_end_seconds"] for entry in schedule) / 3600,
            "peak_unfinished_sessions_not_running_requests": peak, "schedule": schedule}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.output.exists() or not args.output.resolve().is_relative_to(ROOT):
        raise ValueError("Use a new output file inside this experiment")
    calibration = json.loads(args.calibration_report.read_text())["runs"][0]
    if not calibration["integrity_audit"]["protocol_integrity_passed"]:
        raise ValueError("Use a completed, integrity-checked calibration")
    service_seconds = sum(session["request_latency_sum_seconds"] for session in calibration["sessions"])
    seconds_per_output = service_seconds / calibration["integrity_audit"]["output_tokens_total"]
    profile = ROOT / "results/audit/encoded_profile_20260926"
    sessions = {}
    with (profile / "sessions.csv").open() as stream:
        for row in csv.DictReader(stream):
            if row["split"] == "evaluation":
                sessions[row["session_id"]] = {"task_id": row["task_id"], "requests": int(row["requests"]),
                                               "wait_seconds": float(row["recorded_wait_sum_seconds"]),
                                               "output_tokens": 0}
    with (profile / "requests.csv").open() as stream:
        for row in csv.DictReader(stream):
            if row["session_id"] in sessions:
                sessions[row["session_id"]]["output_tokens"] += int(row["source_output_tokens"])
    proposals = [estimate(sessions, seconds_per_output, spacing, factor)
                 for spacing in [60, 90, 120] for factor in [.5, 1, 2]]
    result = {"purpose": "formal_schedule_budget_proposal_not_frozen_or_executable", "formal_gate_open": False,
              "source_sha256": {str(path.relative_to(ROOT)): digest_file(path) for path in [
                  args.calibration_report.resolve(), profile / "sessions.csv", profile / "requests.csv", Path(__file__)]},
              "sessions": len(sessions), "requests": sum(session["requests"] for session in sessions.values()),
              "seconds_of_request_latency_per_output_token_proxy": seconds_per_output,
              "calibration_cached_input_fraction": calibration["integrity_audit"]["token_weighted_cache_hit_fraction"],
              "proposals": proposals,
              "limitations": ["Arithmetic scaling, not a fitted model, queue simulator, lower bound or confidence interval",
                              "Includes all recorded waits; output-proportional scaling does not model prompt length, cache misses or concurrency",
                              "Service factor 0.5/1/2 is illustrative sensitivity, not an empirical error interval",
                              "Unfinished sessions include waiting sessions and do not equal active GPU requests",
                              "Startup, warmup, cleanup and failures add time; formal arrival density requires validation"]}
    save_json(args.output, result)
    print(json.dumps({"output": str(args.output), "proposals": [
        {key: value for key, value in proposal.items() if key != "schedule"} for proposal in proposals]}))


if __name__ == "__main__":
    main()
