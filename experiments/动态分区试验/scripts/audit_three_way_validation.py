#!/usr/bin/env python3
"""Audit actual replay integrity, resource parity, and region counters."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    reports = {}
    comparable = defaultdict(list)
    for scenario in sorted(root.iterdir()):
        config_path = scenario / "config.json"
        if not config_path.is_file():
            continue
        config = json.loads(config_path.read_text())
        workload = Path(config["workload_dir"]) / "workload.jsonl"
        digest = hashlib.sha256(workload.read_bytes()).hexdigest()
        expected = config["expected_requests"]
        for mode in config["modes"]:
            folder = scenario / mode
            summary_path = folder / "run_mix_replay/summary.json"
            if not summary_path.is_file():
                reports[f"{scenario.name}/{mode}"] = {"complete": False}
                continue
            summary = json.loads(summary_path.read_text())
            rows = [json.loads(line) for line in (folder / "run_mix_replay/replay.jsonl").read_text().splitlines() if line.strip()]
            before = json.loads((folder / "server_info_before.json").read_text())["internal_states"][0]
            after = json.loads((folder / "server_info_after.json").read_text())["internal_states"][0]
            trajectory = [json.loads(line) for line in (folder / "controller_trajectory.jsonl").read_text().splitlines() if line.strip()]
            region_states = [row["regions"] for row in trajectory if row.get("regions")]
            if after.get("request_cache_regions"):
                region_states.append(after["request_cache_regions"])
            negative_fields = []
            regressions = []
            previous = {}
            for index, regions in enumerate(region_states):
                for region, values in regions.items():
                    for key, value in values.items():
                        if isinstance(value, (int, float)) and value < 0:
                            negative_fields.append([index, region, key, value])
                    for key in ("eviction_count", "full_evicted_tokens", "swa_evicted_tokens", "borrowed_eviction_count", "borrowed_full_evicted_tokens", "borrowed_swa_evicted_tokens"):
                        value = int(values.get(key) or 0)
                        pair = region, key
                        if value < previous.get(pair, 0):
                            regressions.append([index, region, key])
                        previous[pair] = value
            identity = [(row["index"], row["trace_id"], row["prompt_tokens"], row["completion_tokens"]) for row in sorted(rows, key=lambda row: row["index"])]
            identity_digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
            totals_match = (
                sum(row.get("prompt_tokens") or 0 for row in rows) == summary["kv"]["prompt_tokens_sum"]
                and sum(row.get("cached_tokens") or 0 for row in rows) == summary["kv"]["cached_tokens_sum"]
            )
            integrity = summary["integrity"]
            passed = (
                len(rows) == expected
                and len({row["index"] for row in rows}) == expected
                and integrity["n_issued"] == integrity["n_ok"] == expected
                and integrity["n_err"] == 0
                and all(row["status"] == "200" for row in rows)
                and all(0 <= row["cached_tokens"] <= row["prompt_tokens"] for row in rows)
                and all(row["completion_tokens"] == config["max_output_tokens"] for row in rows)
                and totals_match and not negative_fields and not regressions
            )
            report = {
                "complete": True, "passed": passed, "n_requests": len(rows),
                "workload_sha256": digest, "request_identity_sha256": identity_digest,
                "token_totals_match_summary": totals_match,
                "negative_region_fields": negative_fields,
                "region_counter_regressions": regressions,
                "sample_count": len(trajectory),
                "full_capacity_tokens": before["memory_usage"]["token_capacity"],
                "mem_fraction_static": before["mem_fraction_static"],
                "radix_eviction_policy": before["radix_eviction_policy"],
                "request_regions_enabled": before.get("enable_request_cache_regions", False),
                "classifier_checkpoint": before.get("request_classifier_checkpoint"),
                "server_log_retracted_requests_tp0": sum(
                    int(match.group(1))
                    for line in (folder / "server.log").read_text(errors="replace").splitlines()
                    if "TP0]" in line
                    for match in [re.search(r"#retracted_reqs:\s*(\d+)", line)]
                    if match
                ),
                "borrow_reclaim_reasons": {
                    region: values.get("borrow_reclaim_reasons", {})
                    for region, values in after.get("request_cache_regions", {}).items()
                },
            }
            reports[f"{scenario.name}/{mode}"] = report
            comparable[digest].append(report)
    parity = {}
    for digest, group in comparable.items():
        fields = ("request_identity_sha256", "full_capacity_tokens", "mem_fraction_static", "radix_eviction_policy")
        parity[digest] = {field: len({row[field] for row in group}) == 1 for field in fields}
    result = {
        "runs": reports, "same_workload_parity": parity,
        "all_completed_runs_passed": all(report.get("passed", True) for report in reports.values()),
        "all_configured_runs_complete": all(report["complete"] for report in reports.values()),
        "all_parity_checks_passed": all(all(group.values()) for group in parity.values()),
        "scope": "服务完整性与可比性；单次并发回放不构成固定事件顺序或统计显著性证明。",
    }
    output = root / "integrity_audit.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, ensure_ascii=False, indent=2))
    print(output)
    return 0 if result["all_completed_runs_passed"] and result["all_parity_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
