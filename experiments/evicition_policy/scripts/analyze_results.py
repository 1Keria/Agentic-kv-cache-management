#!/usr/bin/env python3
"""Audit complete runs; smoke summaries are not policy-performance rankings."""

import argparse
import json
import os
from pathlib import Path

from build_workload import effective_gap_seconds, read_rows
from prepare_data import ROOT, canonical_digest, digest_file, save_json
from profile_agent import distribution
from run_suite import cache_is_empty


def audit_run(folder: Path) -> dict:
    state = json.loads((folder / "state.json").read_text())
    workload = json.loads((folder / "workload.json").read_text())
    summary = json.loads((folder / "measurement/summary.json").read_text())
    log = folder / "measurement/requests.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines()]
    expected = {(entry["session_id"], row["turn_index"]): {key: value for key, value in row.items() if key != "input_ids"} for entry in workload["sessions"]
                for row in read_rows(entry)[:entry["replay_requests"]]}
    errors = []
    if state["status"] != "completed" or summary["status"] != "completed":
        errors.append("run_not_completed")
    if digest_file(log) != summary["request_log_sha256"]:
        errors.append("request_log_hash_drift")
    if canonical_digest(workload) != summary["workload_sha256"]:
        errors.append("workload_hash_drift")
    observed = [(row["session_id"], row["turn_index"]) for row in records]
    if len(set(observed)) != len(observed) or set(observed) != set(expected):
        errors.append("duplicate_or_missing_requests")
    for row in records:
        source = expected.get((row["session_id"], row["turn_index"]))
        if source is None:
            continue
        if row["input_ids_sha256"] != source["input_ids_sha256"]:
            errors.append("input_hash_drift")
        if canonical_digest(row["output_ids"]) != row["output_ids_sha256"]:
            errors.append("output_hash_drift")
        target = min(source["output_tokens"], workload["output_token_cap"]) if workload["output_token_cap"] is not None else source["output_tokens"]
        if row["status"] != "completed" or row["actual_output_tokens"] != target or len(row["output_ids"]) != target:
            errors.append("incomplete_generation")
        expected_gap = effective_gap_seconds(source, workload)
        source_gap = source["wait_after_previous_response_seconds"]
        if row.get("source_gap_seconds") != source_gap or row.get("effective_gap_seconds") != expected_gap:
            errors.append("timing_transform_drift")
        if row["turn_index"] and row["actual_gap_seconds"] + 1e-6 < expected_gap:
            errors.append("dependency_wait_shortened")
    flush_empty = cache_is_empty((folder / "metrics_before.prom").read_text())
    flush = json.loads((folder / "flush.json").read_text())
    if not flush["success"]:
        errors.append("cache_flush_failed")
    signature = json.loads((folder / "effective_signature.json").read_text())
    cleanup = json.loads((folder / "cleanup.json").read_text())
    if cleanup["remaining_group_members"]:
        errors.append("owned_processes_remain")
    cache_known = all(type(row["cached_tokens"]) is int and 0 <= row["cached_tokens"] <= row["prompt_tokens"] for row in records)
    result = {"run": folder.name, "policy": state["policy"],
              "strategy": state.get("strategy", state["policy"]),
              "exposure_barrier": state.get("exposure_barrier", False),
              "purpose": workload["purpose"],
              "integrity_errors": sorted(set(errors)), "protocol_integrity_passed": not errors,
              "requests": len(records), "expected_requests": len(expected), "signature": signature,
              "prompt_tokens_total": sum(row["prompt_tokens"] for row in records),
              "output_tokens_total": sum(row["actual_output_tokens"] for row in records),
              "ttft_seconds": distribution([row["ttft_seconds"] for row in records]),
              "latency_seconds": distribution([row["latency_seconds"] for row in records]),
              "cached_tokens_all_known": cache_known, "cache_flush_acknowledged": flush["success"],
              "post_flush_native_metrics_empty": flush_empty,
              "generation_continuation_checks": sum("previous_local_output_fully_matches_next_input" in row for row in records),
              "generation_continuation_matches": sum(row.get("previous_local_output_fully_matches_next_input", False) for row in records),
              "cleanup_confirmed": not cleanup["remaining_group_members"],
              "single_run_descriptive_comparison_allowed": workload["purpose"] == "formal" and not errors and flush_empty,
              "performance_claim_allowed": workload["purpose"] == "formal" and workload.get("comparison_stage") != "single_pass_exploratory" and not errors and flush_empty}
    result["token_weighted_cache_hit_fraction"] = (sum(row["cached_tokens"] for row in records) / result["prompt_tokens_total"]) if cache_known else None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if not args.output.resolve().is_relative_to(ROOT) or args.output.exists():
        raise ValueError("Use a new output path inside this experiment")
    suite = json.loads((args.suite / "suite.json").read_text())
    results = []
    for path in sorted(args.suite.glob("*/state.json")):
        try:
            results.append(audit_run(path.parent))
        except Exception as error:
            results.append({"run": path.parent.name, "protocol_integrity_passed": False, "error": repr(error)})
    signatures = [canonical_digest(result["signature"]) for result in results if "signature" in result]
    summary = {"suite_status": suite["status"], "purpose": suite["purpose"], "runs": results,
               "all_protocol_checks_passed": suite["status"] == "completed" and len(results) == len(suite["policies"]) and all(result["protocol_integrity_passed"] for result in results),
               "all_effective_signatures_equal": len(signatures) == len(results) and len(set(signatures)) == 1,
               "all_post_flush_metrics_empty": all(result.get("post_flush_native_metrics_empty", False) for result in results),
               "note": "Smoke tests validate engineering only; do not rank policies or infer eviction benefits from these timings."}
    save_json(args.output, summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "runs"}, ensure_ascii=False))
    if not summary["all_protocol_checks_passed"] or not summary["all_effective_signatures_equal"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
