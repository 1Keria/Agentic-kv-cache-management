#!/usr/bin/env python3
"""Summarize calibration only, retaining native metric ambiguity and failures."""

import argparse
import datetime
import json
import math
import os
from pathlib import Path

from prometheus_client.parser import text_string_to_metric_families

from analyze_results import audit_run
from prepare_data import ROOT, digest_file, save_json
from profile_agent import distribution


COUNTERS = {"sglang:evicted_tokens_total", "sglang:eviction_duration_seconds_count",
            "sglang:eviction_duration_seconds_sum"}
QUEUE_METRICS = {"sglang:queue_time_seconds_sum", "sglang:queue_time_seconds_count",
                 "sglang:queue_time_seconds_bucket"}
GAUGES = {"sglang:num_running_reqs", "sglang:num_queue_reqs", "sglang:kv_available_tokens",
          "sglang:kv_evictable_tokens", "sglang:kv_used_tokens", "sglang:swa_available_tokens",
          "sglang:swa_evictable_tokens", "sglang:swa_used_tokens"}


def metric_samples(raw: str) -> dict:
    result = {}
    for family in text_string_to_metric_families(raw):
        for sample in family.samples:
            if sample.name in COUNTERS | GAUGES | QUEUE_METRICS and math.isfinite(sample.value):
                key = (sample.name, tuple(sorted(sample.labels.items())))
                if key in result:
                    raise ValueError("Duplicate native metric series")
                result[key] = sample.value
    return result


def counter_deltas(before: dict, after: dict) -> list[dict]:
    result = []
    for key in sorted(set(before) | set(after)):
        if key[0] not in COUNTERS:
            continue
        initial, final = before.get(key), after.get(key)
        delta = final - initial if initial is not None and final is not None and final >= initial else None
        result.append({"name": key[0], "labels": dict(key[1]), "before": initial, "after": final,
                       "raw_delta": delta, "complete_monotone_pair": delta is not None})
    return result


def observed_counter_windows(series: dict) -> list[dict]:
    result = []
    for key, samples in sorted(series.items()):
        values = [sample[1] for sample in samples]
        monotone = all(right >= left for left, right in zip(values, values[1:]))
        result.append({"name": key[0], "labels": dict(key[1]), "samples": len(samples),
                       "first_timestamp_utc": samples[0][0], "last_timestamp_utc": samples[-1][0],
                       "first_observed": values[0], "last_observed": values[-1],
                       "observed_window_raw_delta": values[-1] - values[0] if monotone else None,
                       "monotone": monotone, "covers_entire_measurement": False})
    return result


def queue_histogram_deltas(before: dict, after: dict, expected_requests: int) -> list[dict]:
    results = []
    for (name, labels), final_count in sorted(after.items()):
        if name != "sglang:queue_time_seconds_count":
            continue
        initial_count = before.get((name, labels))
        initial_sum = before.get(("sglang:queue_time_seconds_sum", labels))
        final_sum = after.get(("sglang:queue_time_seconds_sum", labels))
        count = final_count - initial_count if initial_count is not None else None
        total = final_sum - initial_sum if final_sum is not None and initial_sum is not None else None
        buckets = []
        for (bucket_name, bucket_labels), final_value in after.items():
            label_dict = dict(bucket_labels)
            if bucket_name != "sglang:queue_time_seconds_bucket" or "le" not in label_dict:
                continue
            upper_text = label_dict.pop("le")
            if tuple(sorted(label_dict.items())) != labels:
                continue
            initial_value = before.get((bucket_name, bucket_labels))
            if initial_value is not None:
                buckets.append((float(upper_text), final_value - initial_value))
        buckets.sort()
        valid = (count is not None and count > 0 and total is not None and total >= 0
                 and count == expected_requests and bool(buckets)
                 and math.isinf(buckets[-1][0]) and buckets[-1][1] == count
                 and all(0 <= value <= count for _, value in buckets)
                 and all(left[1] <= right[1] for left, right in zip(buckets, buckets[1:])))
        bounds = {}
        if valid:
            for quantile in [.5, .95, .99]:
                lower = 0.0
                for upper, cumulative in buckets:
                    if cumulative >= count * quantile:
                        bounds[str(quantile)] = {"lower_seconds": lower,
                                                 "upper_seconds": upper if math.isfinite(upper) else None,
                                                 "upper_unbounded": not math.isfinite(upper),
                                                 "exact_percentile": False}
                        break
                    lower = upper
        results.append({"labels": dict(labels), "count_delta": count, "sum_seconds_delta": total,
                        "expected_requests": expected_requests, "measurement_coverage_validated": valid,
                        "mean_seconds": total / count if valid else None,
                        "quantile_bucket_bounds": bounds,
                        "note": "Per-rank histogram differences; never add tensor-parallel copies; quantiles are bounds, not exact values."})
    return results


def pool_observations(samples: dict, capacities: dict) -> list[dict]:
    observations = []
    for pool, prefix, capacity_key in [("full", "kv", "full_tokens"), ("swa", "swa", "swa_tokens")]:
        capacity = capacities[capacity_key]
        available_name = f"sglang:{prefix}_available_tokens"
        for (name, labels), available in samples.items():
            if name != available_name:
                continue
            used = samples.get((f"sglang:{prefix}_used_tokens", labels))
            evictable = samples.get((f"sglang:{prefix}_evictable_tokens", labels))
            valid_free = 0 <= available <= capacity
            observations.append({"pool": pool, "labels": dict(labels), "capacity": capacity,
                                 "free_tokens": available, "non_evictable_used_tokens": used,
                                 "evictable_tokens": evictable,
                                 "resident_fraction": (capacity - available) / capacity if valid_free else None,
                                 "accounting_residual_tokens": None if used is None or evictable is None else capacity - available - used - evictable})
    return observations


def numeric_distribution(records: list[dict], field: str, nested: bool = False) -> dict:
    values = [(row.get("meta_info", {}) if nested else row).get(field) for row in records]
    known = [value for value in values if type(value) in {int, float} and math.isfinite(value)]
    return {**distribution(known), "missing_or_nonfinite": len(records) - len(known)}


def summarize_run(folder: Path) -> dict:
    state = json.loads((folder / "state.json").read_text())
    result = {"path": str(folder.relative_to(ROOT)), "state": state, "purpose": "calibration_not_policy_comparison"}
    measurement = folder / "measurement"
    records = []
    parse_errors = 0
    if (measurement / "requests.jsonl").exists():
        with (measurement / "requests.jsonl").open() as stream:
            for line in stream:
                try:
                    records.append(json.loads(line))
                except ValueError:
                    parse_errors += 1
    result["request_log_parse_errors"] = parse_errors
    result["recorded_requests"] = len(records)
    result["completed_requests"] = sum(row["status"] == "completed" for row in records)
    if (measurement / "summary.json").exists():
        summary = json.loads((measurement / "summary.json").read_text())
        result["measurement"] = {key: value for key, value in summary.items() if key != "generation_consistency_checks"}
    result["client_ttft_seconds"] = numeric_distribution(records, "ttft_seconds")
    result["client_latency_seconds"] = numeric_distribution(records, "latency_seconds")
    result["native_queue_time_seconds_raw_untrusted"] = numeric_distribution(records, "queue_time", nested=True)
    result["request_queue_time_validated"] = False
    result["queue_time_warning"] = "Pinned native two-hop timing serialization drops timestamps; zero response queue_time is not zero observed queueing. Use per-rank scheduler histograms."
    result["native_num_retractions"] = numeric_distribution(records, "num_retractions", nested=True)
    result["client_schedule_lag_seconds"] = numeric_distribution(records, "schedule_lag_seconds")
    workload = json.loads((folder / "workload.json").read_text())
    sessions = []
    for entry in workload["sessions"]:
        observed = [row for row in records if row["session_id"] == entry["session_id"]]
        completed = [row for row in observed if row["status"] == "completed"]
        sessions.append({"session_id": entry["session_id"], "task_id": entry["task_id"],
                         "expected_requests": entry["replay_requests"], "completed_requests": len(completed),
                         "complete": len(completed) == entry["replay_requests"],
                         "recorded_wait_seconds_observed": sum(row["source_gap_seconds"] or 0 for row in observed),
                         "effective_wait_seconds_observed": sum(row.get("effective_gap_seconds") or 0 for row in observed),
                         "request_latency_sum_seconds": sum(row["latency_seconds"] for row in observed),
                         "observed_span_seconds": max(row["completed_seconds"] for row in observed) - min(row["submitted_seconds"] for row in observed) if observed else None,
                         "final_completion_from_workload_start_seconds": max(row["completed_seconds"] for row in observed) if observed else None})
    result["sessions"] = sessions
    signature_path = folder / "effective_signature.json"
    signature = json.loads(signature_path.read_text()) if signature_path.exists() else None
    result["effective_signature"] = signature
    before_path, after_path = folder / "metrics_before.prom", folder / "metrics_after.prom"
    before = metric_samples(before_path.read_text()) if before_path.exists() else {}
    after = metric_samples(after_path.read_text()) if after_path.exists() else {}
    result["raw_counter_deltas"] = counter_deltas(before, after)
    result["scheduler_queue_histogram_by_rank"] = queue_histogram_deltas(before, after, workload["requests"])
    pool_series = {}
    gauge_series = {}
    counter_series = {}
    monitor_errors = 0
    if (folder / "monitor.jsonl").exists() and signature:
        with (folder / "monitor.jsonl").open() as stream:
            for line in stream:
                try:
                    sample = json.loads(line)
                    values = metric_samples(sample["metrics"])
                    if sample.get("error"):
                        monitor_errors += 1
                    for key, value in values.items():
                        if key[0] in GAUGES:
                            gauge_series.setdefault(key, []).append(value)
                        if key[0] in COUNTERS:
                            counter_series.setdefault(key, []).append((sample["timestamp_utc"], value))
                    for observed in pool_observations(values, signature["capacities"]):
                        key = (observed["pool"], tuple(sorted(observed["labels"].items())))
                        pool_series.setdefault(key, []).append(observed)
                except (ValueError, KeyError):
                    monitor_errors += 1
    result["monitor_error_samples"] = monitor_errors
    result["observed_counter_windows"] = observed_counter_windows(counter_series)
    result["native_gauges_by_series"] = [{"name": key[0], "labels": dict(key[1]), "sample_distribution": distribution(values)}
                                          for key, values in sorted(gauge_series.items())]
    result["pool_residency_by_series"] = [
        {"pool": key[0], "labels": dict(key[1]), "samples": len(values),
         "resident_fraction_sample_distribution": distribution([row["resident_fraction"] for row in values if row["resident_fraction"] is not None]),
         "accounting_mismatch_samples": sum(row["accounting_residual_tokens"] not in {None, 0} for row in values),
         "missing_accounting_samples": sum(row["accounting_residual_tokens"] is None for row in values)}
        for key, values in sorted(pool_series.items())]
    try:
        result["integrity_audit"] = audit_run(folder)
    except Exception as error:
        result["integrity_audit"] = {"protocol_integrity_passed": False, "error": repr(error)}
    if (folder / "cleanup.json").exists():
        cleanup = json.loads((folder / "cleanup.json").read_text())
        result["owned_gpu_allocations_released"] = cleanup.get("owned_gpu_allocations_released", False)
    result["formal_performance_claim_allowed"] = False
    result["limitations"] = [
        "Calibration only; no policy ranking or best-capacity claim",
        "Raw eviction counters may aggregate TP ranks and mix Full/SWA components; no division or logical-token interpretation",
        "Missing initial counters remain unknown; observed-window deltas exclude the unobserved beginning",
        "Pool gauges exclude evictable tokens from used; resident fraction derives from capacity minus free",
        "Gauge sample distributions are not time-weighted and native updates can lag",
        "No complete Full/SWA eviction event or legal-candidate coverage; Full policy pressure not proven",
        "Warmup does not prove all workload shapes precompiled; inspect any saved shape warmup plan and pass summaries",
        "Native response queue_time timestamps are lost on the second IPC serialization; scheduler histograms provide only aggregate bounds",
        "Observed session spans include source waits, local generation and queueing; not real tool execution"]
    return result


def suite_from_log(path: Path) -> Path:
    for line in path.read_text().splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and "suite" in record:
            return Path(record["suite"])
    raise ValueError("Controller log does not contain a suite directory")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--suite", type=Path)
    inputs.add_argument("--controller-log", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.output.exists() or not args.output.resolve().is_relative_to(ROOT):
        raise ValueError("Use a new report path inside this experiment")
    folder = (args.suite or suite_from_log(args.controller_log)).resolve()
    if not folder.is_relative_to(ROOT / "results/pilot"):
        raise ValueError("Only local pilot results may be analyzed")
    suite = json.loads((folder / "suite.json").read_text())
    if suite["purpose"] != "calibration":
        raise ValueError("Not a calibration suite")
    result = {"created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "suite": str(folder.relative_to(ROOT)), "suite_status": suite["status"],
              "analysis_fingerprints": {path.name: digest_file(path) for path in [Path(__file__), ROOT / "scripts/analyze_results.py", ROOT / "scripts/profile_agent.py"]},
              "runs": [summarize_run(path.parent) for path in sorted(folder.glob("*/state.json"))]}
    save_json(args.output, result)
    print(json.dumps({"report": str(args.output), "suite": str(folder), "status": suite["status"]}))


if __name__ == "__main__":
    main()
