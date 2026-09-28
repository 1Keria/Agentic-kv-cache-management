#!/usr/bin/env python3
"""Freeze validation and three-run inputs before measuring candidate policies."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from build_workload import POOL, build, read_rows
from check_admission import validate_admission
from prepare_calibration import select_sessions
from prepare_data import ROOT, canonical_digest, digest_file, save_json
from shape_warmup import validate_shapes


ACCELERATION_SCALE = 0.30
RAW_START_SPACING_SECONDS = 90.0
VALIDATION_SESSION_COUNT = 20
EVALUATION_SESSION_COUNT = 20
EXPLORATION_MAX_TOTAL_TOKENS = 524288


def ordered_selection(pool: dict, split: str, purpose: str,
                      start_spacing_seconds: float = RAW_START_SPACING_SECONDS,
                      session_limit: int | None = None) -> dict:
    candidates = [entry for entry in pool["sessions"] if entry["split"] == split]
    ordered = sorted(candidates, key=lambda entry: hashlib.sha256(
        ("formal-schedule-proposal-v1:42:" + entry["session_id"]).encode()).hexdigest())
    candidate_count = len(ordered)
    if session_limit is not None:
        if type(session_limit) is not int or not 0 < session_limit <= len(ordered):
            raise ValueError("Invalid complete-session limit")
        ordered = ordered[:session_limit]
    return {"purpose": purpose,
            "selection_method": "sha256_order_prefix_v1",
            "selection_key": "formal-schedule-proposal-v1:42:<session_id>",
            "candidate_sessions": candidate_count,
            "selected_complete_sessions": len(ordered),
            "requests_or_outputs_truncated": False,
            "sessions": [
        {"session_id": entry["session_id"], "start_offset_seconds": index * start_spacing_seconds}
        for index, entry in enumerate(ordered)]}


def apply_timing_transform(workload: dict, gap_scale: float, raw_start_spacing_seconds: float) -> dict:
    if type(gap_scale) not in {int, float} or not 0 < gap_scale <= 1:
        raise ValueError("Invalid acceleration scale")
    effective_spacing = raw_start_spacing_seconds * gap_scale
    workload["timing_transform"] = {
        "name": "uniform_accelerated_replay_v1",
        "inter_request_gap_scale": gap_scale,
        "raw_start_spacing_seconds": raw_start_spacing_seconds,
        "effective_start_spacing_seconds": effective_spacing,
        "formula": "effective_gap = recorded_gap * inter_request_gap_scale; token content and output targets unchanged",
        "preserves_all_sessions_and_requests": True,
        "synthetic_timing_not_natural_traffic": True,
    }
    workload["arrival_basis"] = "accelerated_synthetic_session_starts"
    workload["dependency_basis"] = "previous_local_completion_plus_scaled_recorded_relative_gap"
    workload["time_basis"] = "uniformly_scaled_recorded_callback_relative_interval_version_unverified"
    return workload


def timing_profile(workload: dict) -> dict:
    scale = workload["timing_transform"]["inter_request_gap_scale"]
    sessions = []
    for entry in workload["sessions"]:
        rows = read_rows(entry)[:entry["replay_requests"]]
        source_gap_sum = sum(row["wait_after_previous_response_seconds"] for row in rows[1:])
        sessions.append({"session_id": entry["session_id"], "requests": len(rows),
                         "start_offset_seconds": entry["start_offset_seconds"],
                         "source_gap_sum_seconds": source_gap_sum,
                         "effective_gap_sum_seconds": source_gap_sum * scale,
                         "prompt_tokens": sum(row["prompt_tokens"] for row in rows),
                         "output_tokens": sum(row["output_tokens"] for row in rows)})
    return {"purpose": workload["purpose"], "sessions": len(sessions),
            "requests": sum(row["requests"] for row in sessions),
            "prompt_tokens": sum(row["prompt_tokens"] for row in sessions),
            "output_tokens": sum(row["output_tokens"] for row in sessions),
            "last_session_start_seconds": max(row["start_offset_seconds"] for row in sessions),
            "source_gap_sum_seconds": sum(row["source_gap_sum_seconds"] for row in sessions),
            "effective_gap_sum_seconds": sum(row["effective_gap_sum_seconds"] for row in sessions),
            "maximum_start_plus_effective_gap_seconds": max(
                row["start_offset_seconds"] + row["effective_gap_sum_seconds"] for row in sessions),
            "timing_transform": workload["timing_transform"],
            "note": "Generation time and queueing are not included; this is not a runtime guarantee."}


def make_shapes(pool: dict) -> dict:
    sources = []
    first_rows = {}
    for entry in pool["sessions"]:
        if entry["split"] != "calibration":
            continue
        rows = read_rows(entry)
        first_rows[entry["session_id"]] = rows[0]
        sources.extend(rows)
    ranked = sorted(sources, key=lambda row: (row["prompt_tokens"], row["session_id"], row["turn_index"]))
    cases = []
    def add_case(case_id, row, tokens=None, synthetic=False):
        tokens = row["input_ids"] if tokens is None else tokens
        cases.append({"case_id": case_id, "input_ids": tokens, "input_ids_sha256": canonical_digest(tokens),
                      "output_tokens": 128, "source": {"session_id": row["session_id"], "turn_index": row["turn_index"],
                                                          "split": "calibration", "synthetic_shape_only": synthetic}})
    for index, fraction in enumerate([.5, .95, 1]):
        add_case(f"length_{index}", ranked[round((len(ranked) - 1) * fraction)])
    longest = ranked[-1]
    target_length = 172032
    original = longest["input_ids"]
    extra = target_length - len(original)
    if extra <= 0:
        raise ValueError("Warmup synthetic envelope must exceed calibration maximum")
    body = original[256:-256]
    padding = (body * ((extra + len(body) - 1) // len(body)))[:extra]
    add_case("synthetic_long_envelope", longest, original[:-256] + padding + original[-256:], True)
    batch_ids = []
    for index, entry in enumerate(select_sessions(pool["sessions"])):
        case_id = f"batch_{index}"
        add_case(case_id, first_rows[entry["session_id"]])
        batch_ids.append(case_id)
    return {"purpose": "engineering_shape_warmup_only", "passes": 2, "cases": cases,
            "groups": [["length_0"], ["length_1"], ["length_2"], ["synthetic_long_envelope"], batch_ids],
            "flush_before_each_pass_and_before_measurement": True,
            "synthetic_construction": "Pad a calibration prompt before its final 256 tokens with repeated calibration content",
            "note": "Engineering shapes only; no evaluation content, tool execution or contribution to measured workload."}


def prepare(output: Path) -> dict:
    if output.exists() or not output.resolve().is_relative_to(ROOT):
        raise ValueError("Use a new directory inside this experiment")
    pool = json.loads(POOL.read_text())
    config = json.loads((ROOT / "configs/calibration_high_server.json").read_text())
    config.update(purpose="frozen_single_pass_exploration_and_density_validation",
                  measurement_timeout_seconds=7200,
                  max_total_tokens=EXPLORATION_MAX_TOTAL_TOKENS)
    info = {"context_length": config["context_length"], "max_total_num_tokens": config["max_total_tokens"], "page_size": config["page_size"]}
    accelerated_spacing = RAW_START_SPACING_SECONDS * ACCELERATION_SCALE
    validation_selection = ordered_selection(
        pool, "calibration", "calibration", accelerated_spacing, VALIDATION_SESSION_COUNT)
    evaluation_selection = ordered_selection(
        pool, "evaluation", "formal", accelerated_spacing, EVALUATION_SESSION_COUNT)
    validation = build(pool, validation_selection, digest_file(POOL))
    evaluation = build(pool, evaluation_selection, digest_file(POOL))
    apply_timing_transform(validation, ACCELERATION_SCALE, RAW_START_SPACING_SECONDS)
    apply_timing_transform(evaluation, ACCELERATION_SCALE, RAW_START_SPACING_SECONDS)
    evaluation.update(formal_protocol_accepted=True, comparison_stage="single_pass_exploratory")
    if (len(validation["sessions"]), validation["requests"], len(evaluation["sessions"]), evaluation["requests"]) != (20, 894, 20, 1206):
        raise ValueError("Frozen coverage changed")
    shapes = make_shapes(pool)
    validate_shapes(shapes, info)
    admissions = {}
    for name, workload in [("validation", validation), ("evaluation", evaluation)]:
        checks = [validate_admission([(entry, read_rows(entry))], workload, info) for entry in workload["sessions"]]
        admissions[name] = {"status": "passed", "requests": sum(check["requests"] for check in checks),
                            "minimum_output_headroom_tokens": min(check["minimum_output_headroom_tokens"] for check in checks)}
    criteria = {"complete_sessions_required": True, "max_total_retractions": 0,
                "max_scheduler_queue_mean_seconds": 10.0, "max_scheduler_queue_p95_upper_seconds": 60.0,
                "max_sampled_queue_requests": 24, "max_client_schedule_lag_p99_seconds": 1.0,
                "require_observed_native_eviction_activity": True,
                "min_observed_native_eviction_raw_delta": 1000000,
                "require_cache_pressure": True,
                "min_full_resident_fraction_p95": 0.95,
                "min_swa_resident_fraction_p95": 0.90,
                "target_validation_seconds": 3600,
                "max_validation_seconds": 4500,
                "measurement_safety_timeout_seconds": config["measurement_timeout_seconds"],
                "require_empty_cache_and_owned_gpu_release": True,
                "note": "All requests are retained. Only synthetic waits are uniformly accelerated; duration target is an engineering budget, not a truncation rule. Cache-pressure thresholds ensure acceleration does not hide eviction."}
    output.mkdir(parents=True)
    timing = {"validation": timing_profile(validation), "evaluation": timing_profile(evaluation),
              "target_seconds_per_policy": 3600,
              "note": "Full coverage is retained; actual duration depends on generation throughput and queueing."}
    artifacts = {"server.json": config, "validation_selection.json": validation_selection,
                 "evaluation_selection.json": evaluation_selection, "validation.json": validation,
                 "evaluation.json": evaluation, "shape_warmup.json": shapes, "criteria.json": criteria,
                 "timing_profile.json": timing}
    for name, value in artifacts.items():
        save_json(output / name, value)
    snapshot = {"purpose": "user_authorized_validation_then_three_run_exploration",
                "user_authorized_auto_start_after_validation": True, "policies": ["lru", "lfu", "slru"],
                "repeats_per_policy": 1, "start_spacing_seconds": accelerated_spacing,
                "raw_start_spacing_seconds": RAW_START_SPACING_SECONDS,
                "inter_request_gap_scale": ACCELERATION_SCALE,
                "validation_session_count": VALIDATION_SESSION_COUNT,
                "evaluation_session_count": EVALUATION_SESSION_COUNT,
                "max_total_tokens": EXPLORATION_MAX_TOTAL_TOKENS,
                "complete_session_selection": "sha256_order_prefix_v1",
                "timing_transform": "uniform_accelerated_replay_v1",
                "target_experiment_seconds": 3600,
                "admission": admissions, "shape_case_count": len(shapes["cases"]),
                "artifact_sha256": {name: digest_file(output / name) for name in artifacts},
                "pool_manifest_sha256": digest_file(POOL),
                "note": "Formal execution still requires a passed validation release; no automatic repeats on failure."}
    save_json(output / "prepared.json", snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(prepare(args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
