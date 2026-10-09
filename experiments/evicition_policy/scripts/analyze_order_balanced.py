#!/usr/bin/env python3
"""Audit and compare complete opposite-order LRU/SLRU serving repeats.

Requests are paired by session and turn, while arrival order is allowed to
change with previous response completion.  Repeat ranges describe variation;
they are not confidence intervals or independent per-request significance tests.
"""

import argparse
import csv
import datetime
import json
import math
import os
from pathlib import Path
import re
import statistics
from zoneinfo import ZoneInfo

from analyze_calibration import (
    counter_deltas, metric_samples, numeric_distribution, pool_observations,
    queue_histogram_deltas,
)
from analyze_results import audit_run
from prepare_data import ROOT, canonical_digest, digest_file, save_json
from profile_agent import distribution


ORDERS = (("lru", "slru"), ("slru", "lru"))
MEASUREMENT_SCRIPTS = (
    "run_suite.py", "shape_warmup.py", "replay_agent.py", "server_command.py",
    "run_server.sh", "runtime_env.sh", "verify_protocol.py",
)


def load(path):
    return json.loads(path.read_text())


def mean_range(values):
    return {"runs": len(values), "values": values, "mean": statistics.mean(values),
            "min": min(values), "max": max(values), "range": max(values) - min(values)}


def ranks(records):
    ordered = sorted(records, key=lambda key: (records[key]["submitted_seconds"], key))
    return {key: index for index, key in enumerate(ordered)}


def compare(left, right):
    if set(left) != set(right):
        raise ValueError("Paired runs have different request keys")
    delta = [right[key]["cached_tokens"] - left[key]["cached_tokens"] for key in left]
    prompt = sum(row["prompt_tokens"] for row in left.values())
    before, after = ranks(left), ranks(right)
    return {
        "cached_tokens_delta": sum(delta),
        "hit_rate_delta_percentage_points": 100 * sum(delta) / prompt,
        "more_cached_requests": sum(value > 0 for value in delta),
        "less_cached_requests": sum(value < 0 for value in delta),
        "equal_cached_requests": sum(value == 0 for value in delta),
        "positive_cached_tokens_delta": sum(max(0, value) for value in delta),
        "negative_cached_tokens_delta": sum(min(0, value) for value in delta),
        "changed_submission_rank_requests": sum(before[key] != after[key] for key in left),
        "submission_rank_absolute_delta": distribution(
            [abs(before[key] - after[key]) for key in left]),
    }


def monitor_summary(folder, signature):
    pool_samples = {"full": [], "swa": []}
    non_evictable_samples = {"full": [], "swa": []}
    evictable_samples = {"full": [], "swa": []}
    temperatures, utilization = [], []
    errors, mismatches, samples = 0, 0, 0
    for line in (folder / "monitor.jsonl").open():
        record = json.loads(line)
        samples += 1
        if record.get("error"):
            errors += 1
            continue
        pool_metrics = "\n".join(
            line for line in record["metrics"].splitlines() if line.startswith((
                "sglang:kv_available_tokens", "sglang:kv_evictable_tokens",
                "sglang:kv_used_tokens", "sglang:swa_available_tokens",
                "sglang:swa_evictable_tokens", "sglang:swa_used_tokens",
            )))
        values = metric_samples(pool_metrics)
        for row in pool_observations(values, signature["capacities"]):
            if row["labels"].get("tp_rank") == "0":
                pool_samples[row["pool"]].append(row["resident_fraction"])
                used, evictable = row["non_evictable_used_tokens"], row["evictable_tokens"]
                if used is not None:
                    non_evictable_samples[row["pool"]].append(used / row["capacity"])
                if evictable is not None:
                    evictable_samples[row["pool"]].append(evictable / row["capacity"])
                mismatches += row["accounting_residual_tokens"] not in {None, 0}
        for row in csv.reader(record.get("gpu_csv", "").splitlines()):
            if len(row) == 6:
                utilization.append(float(row[3].strip().removesuffix("%").strip()))
                temperatures.append(float(row[4].strip()))
    return {
        "samples": samples, "error_samples": errors,
        "rank0_pool_accounting_mismatch_samples": mismatches,
        "rank0_pool_resident_fraction": {
            pool: distribution([value for value in values if value is not None])
            for pool, values in pool_samples.items()
        },
        "rank0_pool_non_evictable_used_fraction": {
            pool: distribution(values) for pool, values in non_evictable_samples.items()
        },
        "rank0_pool_evictable_fraction": {
            pool: distribution(values) for pool, values in evictable_samples.items()
        },
        "gpu_temperature_celsius": distribution(temperatures),
        "gpu_utilization_percent": distribution(utilization),
        "sampling_distribution_is_not_time_weighted": True,
    }


def run_summary(folder, run_id, batch, position):
    audit = audit_run(folder)
    required = ("protocol_integrity_passed", "post_flush_native_metrics_empty",
                "cached_tokens_all_known", "cleanup_confirmed")
    if not all(audit[field] for field in required):
        raise ValueError(f"Run failed integrity: {folder}")
    cleanup = load(folder / "cleanup.json")
    if not cleanup.get("owned_gpu_allocations_released"):
        raise ValueError(f"GPU release unverified: {folder}")
    if load(folder / "protocol.json")["status"] != "passed":
        raise ValueError(f"Protocol failed: {folder}")
    shapes = load(folder / "shape_warmup_plan.json")
    for index in range(1, shapes["passes"] + 1):
        shape = load(folder / f"shape_pass_{index}" / "summary.json")
        if (shape["status"] != "completed" or shape["completed_requests"] != len(shapes["cases"])
                or shape["plan_sha256"] != canonical_digest(shapes)):
            raise ValueError(f"Shape warmup incomplete: {folder}")
    rows = [json.loads(line) for line in (folder / "measurement/requests.jsonl").open()]
    for row in rows:
        for field in ("ttft_seconds", "latency_seconds", "schedule_lag_seconds"):
            if not math.isfinite(row[field]) or row[field] < 0:
                raise ValueError(f"Invalid request timing: {folder}")
    before = metric_samples((folder / "metrics_before.prom").read_text())
    after = metric_samples((folder / "metrics_after.prom").read_text())
    measurement = load(folder / "measurement/summary.json")
    native = counter_deltas(before, after)
    queue = queue_histogram_deltas(before, after, len(rows))
    monitor = monitor_summary(folder, audit["signature"])
    retractions = numeric_distribution(rows, "num_retractions", nested=True)
    cached = sum(row["cached_tokens"] for row in rows)
    ttft, latency = audit["ttft_seconds"], audit["latency_seconds"]
    result = {
        "run_id": run_id, "batch": batch, "position": position, "policy": audit["policy"],
        "path": str(folder.relative_to(ROOT)), "requests": len(rows),
        "prompt_tokens": audit["prompt_tokens_total"], "output_tokens": audit["output_tokens_total"],
        "cached_tokens": cached, "uncached_input_tokens": audit["prompt_tokens_total"] - cached,
        "hit_rate": audit["token_weighted_cache_hit_fraction"],
        "previous_input_lcp_shortfall_proxy_tokens": sum(
            max(0, (row.get("previous_input_lcp_tokens") or 0) // 256 * 256
                - row["cached_tokens"]) for row in rows),
        "ttft_seconds": {**ttft, "mean": ttft["sum"] / len(rows)},
        "latency_seconds": {**latency, "mean": latency["sum"] / len(rows)},
        "post_first_token_seconds": distribution(
            [row["latency_seconds"] - row["ttft_seconds"] for row in rows]),
        "measurement_elapsed_seconds": measurement["elapsed_seconds"],
        "native_num_retractions": retractions,
        "schedule_lag_seconds": numeric_distribution(rows, "schedule_lag_seconds"),
        "raw_native_counter_deltas": native, "scheduler_queue_by_rank": queue,
        "monitor": monitor, "integrity": audit,
        "measurement_script_sha256": {
            name: load(folder / "script_fingerprints.json")[name]
            for name in MEASUREMENT_SCRIPTS
        },
    }
    # Server timestamps in these retained logs use Asia/Shanghai. Count JIT
    # messages only inside the independently recorded measurement window.
    start = datetime.datetime.fromisoformat(measurement["started_at_utc"])
    finish = start + datetime.timedelta(seconds=measurement["elapsed_seconds"])
    jit = 0
    for line in (folder / "server.log").open():
        if "Entering DeepGEMM JIT Pre-Compile session" not in line:
            continue
        match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if match:
            when = datetime.datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=ZoneInfo("Asia/Shanghai"))
            if start <= when <= finish:
                jit += 1
    result["measurement_deepgemm_jit_messages"] = jit
    result["evidence_sha256"] = {
        name: digest_file(folder / name) for name in (
            "state.json", "effective_signature.json", "script_fingerprints.json",
            "metrics_before.prom", "metrics_after.prom", "cleanup.json",
            "measurement/summary.json", "measurement/requests.jsonl",
        )
    }
    return result, {(row["session_id"], row["turn_index"]): row for row in rows}


def analyze(batch_root, output):
    metadata = load(batch_root / "batch.json")
    if metadata["status"] != "completed" or len(metadata["batches"]) != 2:
        raise ValueError("Both independent opposite-order batches must be complete")
    runs, records, source_summary_checks = [], {}, []
    for index, order in enumerate(ORDERS, start=1):
        batch = batch_root / f"{index:02d}_{'_'.join(order)}"
        suite = load(batch / "suite.json")
        if suite["status"] != "completed" or suite["policies"] != list(order):
            raise ValueError(f"Incomplete or changed batch: {batch}")
        for position, policy in enumerate(order, start=1):
            run_id = f"batch{index}_{policy}"
            result, keyed = run_summary(
                batch / f"{position:02d}_{policy}", run_id, index, position)
            if result["policy"] != policy:
                raise ValueError("Policy mismatch")
            runs.append(result)
            records[run_id] = keyed
        actual = runs[-2]["integrity"]["signature"] == runs[-1]["integrity"]["signature"]
        saved = load(batch / "summary.json")["all_effective_signatures_equal"]
        source_summary_checks.append({
            "batch": index, "saved_all_effective_signatures_equal": saved,
            "recomputed_all_effective_signatures_equal": actual,
            "saved_boolean_disagrees": saved != actual,
        })
    signatures = [row["integrity"]["signature"] for row in runs]
    script_sets = [row["measurement_script_sha256"] for row in runs]
    workload_hashes = [load(ROOT / row["path"] / "measurement/summary.json")["workload_sha256"]
                       for row in runs]
    config_hashes = [canonical_digest(load(ROOT / row["path"] / "config.resolved.json"))
                     for row in runs]
    if (len({canonical_digest(row) for row in signatures}) != 1
            or len({canonical_digest(row) for row in script_sets}) != 1
            or len(set(workload_hashes)) != 1 or len(set(config_hashes)) != 1):
        raise ValueError("Measurement config, scripts or inputs drifted across runs")
    released_signature = json.loads(json.dumps(metadata["frozen_original_release_signature"]))
    released_signature["server"]["model_path"] = signatures[0]["server"]["model_path"]
    if released_signature != signatures[0]:
        raise ValueError("Effective signature changed beyond the recorded model relocation")
    if any(set(keyed) != set(records["batch1_lru"]) for keyed in records.values()):
        raise ValueError("Runs have different requests")
    pairs = []
    for index in (1, 2):
        lru = next(row for row in runs if row["run_id"] == f"batch{index}_lru")
        slru = next(row for row in runs if row["run_id"] == f"batch{index}_slru")
        pair = {"batch": index, "order": list(ORDERS[index - 1]),
                **compare(records[lru["run_id"]], records[slru["run_id"]])}
        for field in ("ttft_seconds", "latency_seconds"):
            pair[field + "_relative_change"] = {
                metric: slru[field][metric] / lru[field][metric] - 1
                for metric in ("mean", "p50", "p95")
            }
        pair["elapsed_relative_change"] = (
            slru["measurement_elapsed_seconds"] / lru["measurement_elapsed_seconds"] - 1)
        pairs.append(pair)
    aggregates, within = {}, {}
    for policy in ("lru", "slru"):
        subset = [row for row in runs if row["policy"] == policy]
        aggregates[policy] = {
            "hit_rate": mean_range([row["hit_rate"] for row in subset]),
            "measurement_elapsed_seconds": mean_range(
                [row["measurement_elapsed_seconds"] for row in subset]),
        }
        for field in ("ttft_seconds", "latency_seconds"):
            aggregates[policy][field] = {
                metric: mean_range([row[field][metric] for row in subset])
                for metric in ("mean", "p50", "p95")
            }
        within[policy] = compare(records[f"batch1_{policy}"], records[f"batch2_{policy}"])
    request_rows, session_rows = [], {}
    for key in sorted(records["batch1_lru"]):
        source = records["batch1_lru"][key]
        row = {"session_id": key[0], "task_id": source["task_id"],
               "turn_index": key[1], "prompt_tokens": source["prompt_tokens"]}
        for run_id, keyed in records.items():
            row[f"cached_tokens_{run_id}"] = keyed[key]["cached_tokens"]
            row[f"ttft_seconds_{run_id}"] = keyed[key]["ttft_seconds"]
            row[f"previous_input_lcp_shortfall_proxy_tokens_{run_id}"] = max(
                0, (keyed[key].get("previous_input_lcp_tokens") or 0) // 256 * 256
                - keyed[key]["cached_tokens"])
        for index in (1, 2):
            row[f"slru_minus_lru_batch{index}"] = (
                row[f"cached_tokens_batch{index}_slru"] - row[f"cached_tokens_batch{index}_lru"])
        session = session_rows.setdefault(key[0], {
            "session_id": key[0], "task_id": source["task_id"], "requests": 0,
            "slru_minus_lru_batch1": 0, "slru_minus_lru_batch2": 0,
        })
        session["requests"] += 1
        for index in (1, 2):
            session[f"slru_minus_lru_batch{index}"] += row[f"slru_minus_lru_batch{index}"]
        request_rows.append(row)
    d1 = [row["slru_minus_lru_batch1"] for row in request_rows]
    d2 = [row["slru_minus_lru_batch2"] for row in request_rows]
    repeated = {
        "both_positive_requests": sum(a > 0 and b > 0 for a, b in zip(d1, d2)),
        "both_negative_requests": sum(a < 0 and b < 0 for a, b in zip(d1, d2)),
        "opposite_sign_requests": sum(a * b < 0 for a, b in zip(d1, d2)),
        "both_zero_requests": sum(a == b == 0 for a, b in zip(d1, d2)),
        "both_at_least_8192_more_cached_requests": sum(
            a >= 8192 and b >= 8192 for a, b in zip(d1, d2)),
        "both_at_least_8192_less_cached_requests": sum(
            a <= -8192 and b <= -8192 for a, b in zip(d1, d2)),
        "all_four_at_least_8192_lcp_shortfall_proxy_requests": sum(
            all(row[f"previous_input_lcp_shortfall_proxy_tokens_{run_id}"] >= 8192
                for run_id in records) for row in request_rows),
        "all_four_minimum_lcp_shortfall_proxy_tokens_sum": sum(
            min(row[f"previous_input_lcp_shortfall_proxy_tokens_{run_id}"]
                for run_id in records) for row in request_rows),
    }
    report = {
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "purpose": "opposite_order_repeat_descriptive_validation",
        "source_batch": str(batch_root.relative_to(ROOT)), "orders": [list(o) for o in ORDERS],
        "all_runs_complete_and_audited": True, "all_effective_signatures_equal": True,
        "all_measurement_scripts_equal": True, "workload_sha256": workload_hashes[0],
        "effective_signature_matches_release_except_model_path": True,
        "run_repeats_per_policy": 2, "runs": runs, "paired_comparisons": pairs,
        "aggregate_per_run_metrics": aggregates, "within_policy_repeat_changes": within,
        "cross_repeat_request_evidence": repeated, "per_session": list(session_rows.values()),
        "source_summary_boolean_audit": source_summary_checks,
        "statistical_significance_claim_allowed": False,
        "limitations": [
            "Two repeats per policy; ranges are descriptive, not confidence intervals.",
            "Same content/dependencies, but closed-loop submission order changes with completion.",
            "No complete Full/SWA victim/candidate events; cache differences are not causal attribution.",
            "Native policy selection affects Full; SWA retains native LRU in this frozen backend.",
            "Uncached input tokens include new content; they are not exact avoidable recomputation.",
            "Native eviction counters may combine pools and TP copies; retain raw series.",
            "Native response queue_time is untrusted; only scheduler histogram coverage is checked.",
            "Historical next-turn inputs are not forced to contain the newly generated output.",
        ],
        "provenance": {
            "analyzer_sha256": digest_file(Path(__file__).resolve()),
            "executed_runner_sha256": metadata["runner_sha256"],
            "batch_metadata_sha256": digest_file(batch_root / "batch.json"),
            "model_relocation": metadata["model_relocation"],
        },
    }
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "summary.json", report)
    with (output / "paired_requests.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(request_rows[0]))
        writer.writeheader()
        writer.writerows(request_rows)
    print(json.dumps({
        "output": str(output), "runs": len(runs), "aggregate": aggregates,
        "paired_comparisons": pairs, "cross_repeat_request_evidence": repeated,
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    batch, output = args.batch.resolve(), args.output.resolve()
    if not batch.is_relative_to(ROOT / "results") or not output.is_relative_to(ROOT):
        raise ValueError("Keep evidence and analysis inside this experiment")
    analyze(batch, output)


if __name__ == "__main__":
    main()
