#!/usr/bin/env python3
"""Audit the arrived-request workspace ablation against frozen native results."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from analyze_resizable_native import metrics, delta, records, read, digest
from analyze_retained_frontier import lifecycle
from replay_resizable_native import canonical_digest, save_json

ROOT = Path(__file__).resolve().parents[1]
PHASES = ("initial", "half", "quarter", "restored")
GEOMETRY = ("workload_sha256", "physical_capacity", "page_size", "sliding_window_size",
            "chunked_prefill_tokens", "profile_events", "source_session_files")


def frozen_suite(source):
    suite = read(source / "suite.json")
    assert suite["status"] == "complete"
    protocol_path = ROOT / suite["protocol"]
    assert digest(protocol_path) == suite["protocol_sha256"]
    protocol = read(protocol_path)
    assert suite["implementation_sha256"] == protocol["implementation_sha256"]
    for name, expected in protocol["implementation_sha256"].items():
        assert digest(ROOT / "scripts" / name) == expected
        assert digest(source / "executed_sources" / name) == expected
    for name, expected in read(source / "executed_sources/manifest.json").items():
        assert digest(source / "executed_sources" / name) == expected
    assert digest(source / "executed_sources" / protocol_path.name) == suite["protocol_sha256"]
    for spec in protocol["settings"].values():
        assert digest(ROOT / spec["path"]) == spec["sha256"]
        assert digest(source / "executed_sources" / Path(spec["path"]).name) == spec["sha256"]
    order = read(source / "order.json")
    assert len(order) == 1206 and canonical_digest(order) == suite["order_sha256"]
    return suite, protocol, order


def analyze(source, v3_analysis, output):
    source, v3_analysis, output = source.resolve(), v3_analysis.resolve(), output.resolve()
    assert all(p.is_relative_to(ROOT / "results") for p in (source, v3_analysis, output))
    suite, protocol, order = frozen_suite(source)
    assert protocol["variants"] == ["workspace"]
    assert protocol["profiles"] == ["constant", "shrink_restore"]
    assert suite["total_executed_requests"] == 2412
    assert digest(ROOT / protocol["workload"]) == protocol["workload_sha256"]
    for entry in protocol["source_session_files"]:
        assert digest(ROOT / entry["path"]) == entry["sha256"]
    for name, expected in protocol["test_source_sha256"].items():
        assert digest(ROOT / "tests" / name) == expected
    v3_summary = read(v3_analysis)
    assert v3_summary["all_checks_passed"] and v3_summary["total_executed_requests"] == 7236
    v3_source = ROOT / v3_summary["source_suite"]
    assert digest(v3_source / "suite.json") == v3_summary["source_suite_sha256"]
    v3_suite, v3_protocol, v3_order = frozen_suite(v3_source)
    assert v3_order == order
    old_source = ROOT / "results/retained_frontier/20261009_v2"
    old_suite, old_protocol, old_order = frozen_suite(old_source)
    assert old_order == order
    for key in GEOMETRY:
        assert protocol[key] == v3_protocol[key] == old_protocol[key]
    settings = read(ROOT / protocol["settings"]["workspace"]["path"])
    cap_full, cap_swa = settings["full_budget_tokens"], settings["swa_budget_tokens"]
    page = protocol["page_size"]
    conditions, all_rows, units, evidence, transitions, workspace_audits = {}, {}, {}, {}, [], {}
    for condition in suite["conditions"]:
        name, profile = condition["condition"], condition["profile"]
        assert condition["variant"] == "workspace" and name == profile + "_workspace"
        assert condition["checks_passed"] and condition["completed_requests"] == 1206
        folder = source / name
        for filename, expected in condition["evidence_sha256"].items():
            assert digest(folder / filename) == expected
        rows, budgets = records(folder / "requests.jsonl"), records(folder / "budget_events.jsonl")
        expected_events = protocol["profile_events"][profile]
        assert len(rows) == 1206 and len(budgets) == len(expected_events)
        high_water, caps = 0, []
        for index, row in enumerate(rows):
            assert row["request_index"] == index
            assert {key: row[key] for key in order[index]} == order[index]
            assert row["profile"] == profile and row["variant"] == "workspace"
            assert row["phase"] == PHASES[sum(index >= b for b in (301, 603, 904))]
            expected = next(e for e in reversed(expected_events) if e["before_request_index"] <= index)
            assert row["hard_budget"] == {pool: expected[pool] for pool in ("full", "swa")}
            high_water = max(high_water, (row["prompt_tokens"] + page - 1) // page * page)
            expected_cap = min(cap_full, max(0, expected["full"] - high_water))
            caps.append(expected_cap)
            assert row["workspace_high_water_full"] == high_water
            assert row["workspace_protection_full_cap"] == expected_cap
            assert all(row[k] for k in ("integrity_passed", "budget_checks_complete", "physical_accounting_ok"))
            assert 0 <= row["matched_tokens"] <= row["full_resident_match_tokens"] <= row["history_match_tokens"] <= row["prompt_tokens"]
            assert row["capacity_loss_tokens"] == row["history_match_tokens"] - row["matched_tokens"]
            assert row["missed_input_tokens"] == row["unavoidable_new_input_tokens"] + row["capacity_loss_tokens"]
            for state_name in ("before", "after"):
                state = row[state_name]
                frontier = state["frontier"]
                assert frontier["units"] <= settings["max_units"]
                for pool, limit in (("full", expected_cap), ("swa", min(cap_swa, expected["swa"]))):
                    assert frontier[pool + "_dependency_tokens"] <= frontier[pool + "_protection_limit"] == limit
                    assert state["resident"][pool] <= row["hard_budget"][pool]
                    assert state["locked"][pool] == 0
            for pool in ("full", "swa"):
                assert sum(e["tokens"] for e in row["native_free_events"] if e["pool"] == pool) == row["real_eviction_release"][pool]
        for version, (event, expected) in enumerate(zip(budgets, expected_events, strict=True)):
            index = expected["before_request_index"]
            previous_high_water = rows[index - 1]["workspace_high_water_full"] if index else 0
            expected_cap = min(cap_full, max(0, expected["full"] - previous_high_water))
            assert event["request_index"] == index and event["budget_version"] == version
            assert event["workspace_high_water_full"] == previous_high_water
            assert event["hard_budget"] == {pool: expected[pool] for pool in ("full", "swa")}
            assert event["accounting_ok"] and event["complete"]
            assert event["shortfall"] == {"full": 0, "swa": 0}
            assert event["protection"]["limits"] == {"full": expected_cap, "swa": min(cap_swa, expected["swa"])}
            transitions.append({"condition": name, **event})
        counts = condition["frontier_counts"]
        assert counts.get("window_tail_splits", 0) == counts.get("input_boundary_splits", 0) == 0
        for pool in ("full", "swa"):
            total_frees = sum(r["real_eviction_release"][pool] for r in rows) + sum(e["released"][pool] for e in budgets)
            assert total_frees == counts.get("freed_" + pool + "_tokens", 0)
        total = metrics(rows)
        assert total["prompt_tokens"] == 48787785
        assert all(total[key] == value for key, value in condition["totals"].items())
        conditions[name] = {"total": total, "phases": {
            phase: metrics([r for r in rows if r["phase"] == phase]) for phase in PHASES}, "frontier_counts": counts}
        unit_events = records(folder / "unit_events.jsonl")
        units[name] = lifecycle(unit_events)
        assert units[name]["admitted_units"] == counts.get("registered", 0)
        assert units[name]["observed_reuse_events"] == counts.get("observed_unit_reuses", 0)
        admitted = {e["unit_id"]: e for e in unit_events if e["event_type"] == "admit"}
        for event in unit_events:
            if event.get("downgrade_reason"):
                prior = admitted[event["predecessor_unit_ids"][0]]
                assert event["boundary_tokens"] < prior["boundary_tokens"]
        units[name]["downgrades_by_phase"] = {phase: dict(Counter(
            e["downgrade_reason"] for e in unit_events if e["phase"] == phase and e.get("downgrade_reason"))) for phase in PHASES}
        workspace_audits[name] = {"online_rule_passed": True, "final_high_water_full": high_water,
            "phases": {phase: {"min_cap": min(caps[i] for i, r in enumerate(rows) if r["phase"] == phase),
                                "max_cap": max(caps[i] for i, r in enumerate(rows) if r["phase"] == phase)} for phase in PHASES}}
        evidence[name] = {**condition["evidence_sha256"], "summary.json": digest(folder / "summary.json")}
        all_rows[name] = rows
    assert set(all_rows) == {p + "_workspace" for p in protocol["profiles"]}
    baselines = {}
    for profile in protocol["profiles"]:
        for variant in ("lru", "v1", "v2", "partial", "v3"):
            name = profile + "_" + variant
            prior_suite, prior_source = (old_suite, old_source) if variant in ("lru", "v1") else (v3_suite, v3_source)
            condition = next(c for c in prior_suite["conditions"] if c["condition"] == name)
            path = prior_source / name / "requests.jsonl"
            assert digest(path) == condition["evidence_sha256"]["requests.jsonl"]
            rows = records(path)
            assert len(rows) == 1206
            assert all({key: row[key] for key in order[i]} == order[i] for i, row in enumerate(rows))
            assert [r["prompt_tokens"] for r in rows] == [r["prompt_tokens"] for r in all_rows[profile + "_workspace"]]
            baselines[name] = {"total": metrics(rows), "phases": {
                phase: metrics([r for r in rows if r["phase"] == phase]) for phase in PHASES}}
            all_rows[name] = rows
    comparisons, paired, by_session, examples = {}, [], {}, {}
    for profile in protocol["profiles"]:
        candidate = all_rows[profile + "_workspace"]
        for variant in ("lru", "v1", "v2", "partial", "v3"):
            baseline = all_rows[profile + "_" + variant]
            assert [r["history_match_tokens"] for r in baseline] == [r["history_match_tokens"] for r in candidate]
            comparisons[profile + "_workspace_vs_" + variant] = {"total": delta(baseline, candidate), "phases": {
                phase: delta([r for r in baseline if r["phase"] == phase], [r for r in candidate if r["phase"] == phase]) for phase in PHASES}}
        for index, row in enumerate(candidate):
            paired.append({"profile": profile, "request_index": index, "phase": row["phase"],
                "prompt_tokens": row["prompt_tokens"], "workspace_high_water_full": row["workspace_high_water_full"],
                "workspace_protection_full_cap": row["workspace_protection_full_cap"],
                **{v + "_match": all_rows[profile + "_" + v][index]["matched_tokens"] for v in ("lru", "v1", "v2", "partial", "v3", "workspace")}})
        by_session[profile] = {}
        for identity in dict.fromkeys(r["session_id"] for r in candidate):
            selected = [r for r in candidate if r["session_id"] == identity]
            baseline = [r for r in all_rows[profile + "_v2"] if r["session_id"] == identity]
            by_session[profile][identity] = {"total_vs_v2": delta(baseline, selected), "phases_vs_v2": {
                phase: delta([r for r in baseline if r["phase"] == phase], [r for r in selected if r["phase"] == phase])
                for phase in PHASES if any(r["phase"] == phase for r in selected)}}
        examples[profile] = {}
        baseline = all_rows[profile + "_v2"]
        for phase in PHASES:
            pairs = [(b["matched_tokens"] - a["matched_tokens"], a, b)
                     for a, b in zip(baseline, candidate, strict=True) if b["phase"] == phase]
            examples[profile][phase] = {}
            for label, selected in (("largest_improvements", sorted((p for p in pairs if p[0] > 0), key=lambda p: -p[0])[:3]),
                                    ("largest_regressions", sorted((p for p in pairs if p[0] < 0), key=lambda p: p[0])[:3])):
                examples[profile][phase][label] = [{"request_index": b["request_index"],
                    "prompt_tokens": b["prompt_tokens"], "history_match_tokens": b["history_match_tokens"],
                    "v2_matched_tokens": a["matched_tokens"], "workspace_matched_tokens": b["matched_tokens"],
                    "matched_token_delta": gain, "workspace_protection_full_cap": b["workspace_protection_full_cap"],
                    "workspace_high_water_full": b["workspace_high_water_full"],
                    "protected_full_before": b["before"]["frontier"]["full_dependency_tokens"]} for gain, a, b in selected]
    acceptance = {phase: all(comparisons["shrink_restore_workspace_vs_" + v]["phases"][phase]["matched_token_delta"] > 0
                            for v in ("lru", "v1", "v2", "partial", "v3")) for phase in ("half", "quarter", "restored")}
    summary = {"schema": "agentkv.workspace_frontier_analysis.v3", "all_checks_passed": True,
        "source_suite": str(source.relative_to(ROOT)), "source_suite_sha256": digest(source / "suite.json"),
        "protocol": suite["protocol"], "protocol_sha256": suite["protocol_sha256"],
        "v3_analysis": str(v3_analysis.relative_to(ROOT)), "v3_analysis_sha256": digest(v3_analysis),
        "total_executed_requests": 2412, "stage_acceptance": acceptance, "conditions": conditions,
        "archived_baselines": baselines, "comparisons": comparisons, "unit_lifecycle": units,
        "workspace_audits": workspace_audits, "transitions": transitions, "evidence_sha256": evidence,
        "descriptive_session_deltas": by_session,
        "descriptive_examples_vs_v2": examples,
        "limitations": protocol["limitations"] + ["Conservative Full workspace reserve double counts shared active/protected pages.",
            "High water uses arrived request lengths only; it never shrinks for later shorter requests.",
            "Single previously explored deterministic trace, not independent generalization; no latency measured."]}
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "summary.json", summary)
    with (output / "paired_requests.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(paired[0]))
        writer.writeheader()
        writer.writerows(paired)
    print(json.dumps({"all_checks_passed": True, "requests": 2412, "acceptance": acceptance,
                      "comparisons": comparisons}, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--v3-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.source, args.v3_analysis, args.output)
