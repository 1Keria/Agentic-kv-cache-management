#!/usr/bin/env python3
"""Fail closed unless a saved calibration audit authorizes exact frozen inputs."""

import json
import math
from pathlib import Path

from prepare_data import ROOT, digest_file


def validation_errors(result: dict, criteria: dict) -> list[str]:
    errors = []
    audit = result.get("integrity_audit", {})
    if result.get("state", {}).get("status") != "completed" or not audit.get("protocol_integrity_passed"):
        errors.append("incomplete_or_invalid_replay")
    sessions = result.get("sessions", [])
    if not sessions or not all(session.get("complete") for session in sessions):
        errors.append("incomplete_sessions")
    if not audit.get("post_flush_native_metrics_empty") or not result.get("owned_gpu_allocations_released"):
        errors.append("cache_or_process_release_unverified")
    retractions = result.get("native_num_retractions", {})
    if (retractions.get("missing_or_nonfinite") != 0 or retractions.get("count") != result.get("completed_requests")
            or retractions.get("sum", math.inf) > criteria["max_total_retractions"]):
        errors.append("retractions_missing_or_excessive")
    ranks = result.get("scheduler_queue_histogram_by_rank", [])
    expected_tp = result.get("effective_signature", {}).get("server", {}).get("tp_size", 0)
    observed_ranks = [row.get("labels", {}).get("tp_rank") for row in ranks]
    if len(ranks) != expected_tp or not expected_tp or set(observed_ranks) != {str(rank) for rank in range(expected_tp)}:
        errors.append("queue_rank_coverage_missing")
    for row in ranks:
        upper = row.get("quantile_bucket_bounds", {}).get("0.95", {}).get("upper_seconds")
        mean = row.get("mean_seconds")
        if (not row.get("measurement_coverage_validated") or mean is None or upper is None
                or mean > criteria["max_scheduler_queue_mean_seconds"]
                or upper > criteria["max_scheduler_queue_p95_upper_seconds"]):
            errors.append("queue_latency_exceeds_release_threshold")
    gauges = [row for row in result.get("native_gauges_by_series", []) if row["name"] == "sglang:num_queue_reqs"]
    if not gauges or any(row["sample_distribution"].get("max", math.inf) > criteria["max_sampled_queue_requests"] for row in gauges):
        errors.append("queue_depth_missing_or_excessive")
    lag = result.get("client_schedule_lag_seconds", {})
    if lag.get("missing_or_nonfinite") != 0 or lag.get("p99", math.inf) > criteria["max_client_schedule_lag_p99_seconds"]:
        errors.append("client_cannot_follow_arrival_schedule")
    eviction = [row for row in result.get("observed_counter_windows", [])
                if row["name"] == "sglang:evicted_tokens_total" and row.get("monotone")
                and (row.get("observed_window_raw_delta") or 0) > 0]
    if criteria["require_observed_native_eviction_activity"] and not eviction:
        errors.append("native_eviction_activity_unobserved")
    minimum_eviction_delta = criteria.get("min_observed_native_eviction_raw_delta")
    if minimum_eviction_delta is not None and (not eviction or max(
            row["observed_window_raw_delta"] for row in eviction) < minimum_eviction_delta):
        errors.append("native_eviction_activity_below_pressure_floor")
    pools = result.get("pool_residency_by_series", [])
    if {row["pool"] for row in pools} != {"full", "swa"} or any(
            row["accounting_mismatch_samples"] or row["missing_accounting_samples"] for row in pools):
        errors.append("pool_accounting_unverified")
    if criteria.get("require_cache_pressure"):
        pressure_thresholds = {"full": criteria["min_full_resident_fraction_p95"],
                               "swa": criteria["min_swa_resident_fraction_p95"]}
        for pool, threshold in pressure_thresholds.items():
            rows = [row for row in pools if row.get("pool") == pool]
            observed = [row.get("resident_fraction_sample_distribution", {}).get("p95") for row in rows]
            known = [value for value in observed if value is not None]
            if not known or max(known) < threshold:
                errors.append(f"{pool}_cache_pressure_unobserved")
    elapsed = result.get("measurement", {}).get("elapsed_seconds")
    if criteria.get("max_validation_seconds") is not None and elapsed is not None and elapsed > criteria["max_validation_seconds"]:
        errors.append("validation_duration_exceeds_target")
    if result.get("monitor_error_samples") != 0:
        errors.append("monitor_errors")
    if not audit.get("cached_tokens_all_known"):
        errors.append("cache_hit_observation_missing")
    return sorted(set(errors))


def verify_release(path: Path, config_path: Path, workload_path: Path, warmup_path: Path, shapes_path: Path, policies: list[str]) -> dict:
    path = path.resolve()
    if not path.is_relative_to(ROOT / "results"):
        raise ValueError("Release must be retained in this experiment's results")
    release = json.loads(path.read_text())
    if release.get("status") != "passed" or release.get("validation_errors") != []:
        raise ValueError("Validation release has not passed")
    if policies != ["lru", "lfu", "slru"] or release.get("policies") != policies or release.get("repeats_per_policy") != 1:
        raise ValueError("Only the approved single-pass three-policy order is allowed")
    paths = {"config": config_path, "workload": workload_path, "protocol_warmup": warmup_path, "shape_warmup": shapes_path}
    for name, artifact in paths.items():
        if artifact is None or digest_file(artifact) != release["input_sha256"][name]:
            raise ValueError(f"Released {name} has changed")
    for relative, expected in release["evidence_sha256"].items():
        evidence = (ROOT / relative).resolve()
        if not evidence.is_relative_to(ROOT) or digest_file(evidence) != expected:
            raise ValueError("Validation evidence has changed")
    for name, expected in release["script_sha256"].items():
        if Path(name).name != name or digest_file(ROOT / "scripts" / name) != expected:
            raise ValueError("Experiment script changed after validation")
    return release
