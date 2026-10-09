#!/usr/bin/env python3
"""Seal accepted research artifacts without modifying measurements or history."""

import argparse
import datetime
import json
from pathlib import Path

from analyze_resizable_native import read, digest

ROOT = Path(__file__).resolve().parents[1]


def audit(output):
    assert output.resolve().is_relative_to(ROOT / "results")
    v3_path = ROOT / "results/analysis/checkpoint_frontier_native_20261009/summary.json"
    workspace_path = ROOT / "results/analysis/workspace_frontier_native_20261009/summary.json"
    v3, workspace = read(v3_path), read(workspace_path)
    assert v3["all_checks_passed"] and workspace["all_checks_passed"]
    assert v3["total_executed_requests"] == 7236 and workspace["total_executed_requests"] == 2412
    assert workspace["v3_analysis_sha256"] == digest(v3_path)
    files = [v3_path, workspace_path]
    for summary in (v3, workspace):
        source = ROOT / summary["source_suite"]
        assert digest(source / "suite.json") == summary["source_suite_sha256"]
        files.extend([source / "suite.json", source / "order.json", source / "executed_sources/manifest.json"])
        protocol_path = ROOT / summary["protocol"]
        assert digest(protocol_path) == summary["protocol_sha256"]
        files.append(protocol_path)
        protocol = read(protocol_path)
        for name, expected in protocol["implementation_sha256"].items():
            for p in (ROOT / "scripts" / name, source / "executed_sources" / name):
                assert digest(p) == expected
                files.append(p)
        for name, condition in summary["conditions"].items():
            assert condition["frontier_counts"].get("window_tail_splits", 0) == 0
            assert condition["frontier_counts"].get("input_boundary_splits", 0) == 0
            for filename, expected in summary["evidence_sha256"][name].items():
                p = source / name / filename
                assert digest(p) == expected
                files.append(p)
    for folder in ("20261009_v3_tests", "20261009_native_workspace_tests"):
        test_root = ROOT / "results/checkpoint_frontier" / folder
        receipt = read(test_root / "test_receipt.json")
        assert receipt["all_passed"] and receipt["exit_code"] == 0
        for name, expected in receipt["test_sources_sha256"].items():
            assert digest(ROOT / "tests" / name) == expected
            files.append(ROOT / "tests" / name)
        files.extend(test_root / p for p in ("test_receipt.json", "stdout.log", "stderr.log"))
    for folder in ("20261009_v3_fixed", "20261009_workspace"):
        receipt = ROOT / "results/checkpoint_frontier" / folder / "audit_rejection/receipt.json"
        assert read(receipt)["audit_passed"] is False
        files.append(receipt)
    diagnostic = ROOT / "results/shallow_probe/20261009_v3_diagnosis"
    probe = read(diagnostic / "summary.json")
    assert probe["requests"] == 1206 and probe["v2_reproduced_request_matches_and_frees"]
    files.append(diagnostic / "summary.json")
    for name, expected in probe["outputs_sha256"].items():
        assert digest(diagnostic / name) == expected
        files.append(diagnostic / name)
    lock_path = ROOT / "configs/environment.lock.json"
    lock = read(lock_path)
    files.append(lock_path)
    wheel = ROOT / lock["engine"]["wheel"]
    assert digest(wheel) == lock["engine"]["wheel_sha256"]
    files.append(wheel)
    for name, expected in lock["engine"]["source_hashes"].items():
        p = ROOT / "runtime/frontier_pristine_20261008_v1/sglang" / name
        assert digest(p) == expected
        files.append(p)
    protocol = read(ROOT / workspace["protocol"])
    workload = ROOT / protocol["workload"]
    assert digest(workload) == protocol["workload_sha256"]
    files.append(workload)
    for entry in protocol["source_session_files"]:
        p = ROOT / entry["path"]
        assert digest(p) == entry["sha256"]
        files.append(p)
    figure_root = ROOT / "reports/figures/checkpoint_frontier_20261009"
    figure_manifest = read(figure_root / "manifest.json")
    for name, expected in figure_manifest["outputs_sha256"].items():
        assert digest(figure_root / name) == expected
        files.append(figure_root / name)
    files.extend([figure_root / "manifest.json", ROOT / "README.md", ROOT / "reports/Agent策略研究接续.md"])
    assert "本轮状态：已完成" in (ROOT / "reports/Agent策略研究接续.md").read_text()
    files.extend(ROOT / "reports" / ("浅检查点与工作空间预留_v3验证_20261009." + suffix) for suffix in ("md", "json"))
    files.extend(ROOT / "scripts" / name for name in (
        "analyze_checkpoint_frontier.py", "analyze_workspace_frontier.py", "plot_native_checkpoint_frontier.py",
        "report_checkpoint_research.py", "audit_checkpoint_delivery.py"))
    postprocessing = ROOT / "results/checkpoint_frontier/20261009_postprocessing"
    receipts = read(postprocessing / "receipt.json")
    assert len(receipts) == 4 and all(r["exit_code"] == 0 for r in receipts)
    files.extend(postprocessing.iterdir())
    manifest = {str(p.relative_to(ROOT)): digest(p) for p in sorted(set(files))}
    result = {"schema": "agentkv.checkpoint_delivery_audit.v3", "all_checks_passed": True,
        "sealed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "accepted_requests": 9648,
        "archived_structural_gate_failed_requests": 9648, "read_only_diagnostic_requests": 1206,
        "tests": "47 foundation/checkpoint tests plus 4 native-endpoint/workspace tests; receipts retained",
        "evidence_sha256": manifest,
        "limits": ["CPU cache indices only; no model KV payload, GPU or latency claims.",
                   "Single explored deterministic trace and external budget profile; no generalization claim."]}
    output.mkdir(parents=True, exist_ok=False)
    (output / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"all_checks_passed": True, "accepted_requests": 9648, "hashed_artifacts": len(manifest)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.output)
