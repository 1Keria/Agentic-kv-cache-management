#!/usr/bin/env python3
"""Audit all v2 evidence, v1 reproduction and the full win/loss distribution."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import statistics

from analyze_resizable_native import metrics, delta, records, read, digest
from replay_resizable_native import canonical_digest, save_json

ROOT = Path(__file__).resolve().parents[1]
PHASES = ("initial", "half", "quarter", "restored")


def lifecycle(events):
    active, seen, ended, lives, reasons, rejected = {}, set(), set(), [], Counter(), Counter()
    for seq, event in enumerate(events, 1):
        assert event["event_seq"] == seq
        kind = event["event_type"]
        if kind == "admission_reject":
            rejected[event["reason"]] += 1
            continue
        identity = event["unit_id"]
        if kind == "admit":
            assert identity not in seen
            seen.add(identity)
            active[identity] = {"admit": event, "reuses": 0}
        elif kind == "reuse":
            assert identity in active
            active[identity]["reuses"] += 1
            assert active[identity]["reuses"] == event["observed_reuses"]
        elif kind in ("revoke", "final_resident"):
            assert identity in active and identity not in ended
            ended.add(identity)
            start = active.pop(identity)
            assert start["reuses"] == event["observed_reuses"]
            age = event["request_index"] - start["admit"]["request_index"]
            assert age >= 0
            reason = event.get("reason", "right_censored_at_end")
            reasons[reason] += 1
            lives.append({"unit_id": identity, "admit_index": start["admit"]["request_index"],
                          "end_index": event["request_index"], "age_requests": age,
                          "reuses": start["reuses"], "end_reason": reason,
                          "admit_phase": start["admit"]["phase"],
                          "boundary_tokens": start["admit"]["boundary_tokens"]})
        else:
            raise AssertionError("Unexpected unit event: " + kind)
    assert not active and seen == ended
    return {"admitted_units": len(lives), "units_reused_while_protected": sum(x["reuses"] > 0 for x in lives),
            "observed_reuse_events": sum(x["reuses"] for x in lives),
            "end_reasons": dict(reasons), "admission_reject_reasons": dict(rejected),
            "uncensored_median_age_requests": statistics.median([
                x["age_requests"] for x in lives if x["end_reason"] != "right_censored_at_end"]) if lives else None,
            "unit_lifetimes": lives,
            "scope": "Observed matches during protection only; migration creates a new unit. End-resident units are right censored."}


def analyze(source, output):
    source, output = source.resolve(), output.resolve()
    if not source.is_relative_to(ROOT / "results") or not output.is_relative_to(ROOT / "results"):
        raise ValueError("Evidence and analysis must stay under experiment results")
    suite = read(source / "suite.json")
    assert suite["status"] == "complete" and suite["total_executed_requests"] == 7236
    protocol_path = ROOT / suite["protocol"]
    assert digest(protocol_path) == suite["protocol_sha256"]
    protocol = read(protocol_path)
    assert suite["implementation_sha256"] == protocol["implementation_sha256"]
    for name, expected in suite["implementation_sha256"].items():
        assert digest(ROOT / "scripts" / name) == expected
        assert digest(source / "executed_sources" / name) == expected
    snapshot_manifest = read(source / "executed_sources/manifest.json")
    for name, expected in snapshot_manifest.items():
        assert digest(source / "executed_sources" / name) == expected
    for spec in protocol["settings"].values():
        assert digest(ROOT / spec["path"]) == spec["sha256"]
    order = read(source / "order.json")
    assert len(order) == 1206 and canonical_digest(order) == suite["order_sha256"]
    all_rows, summaries, transitions, unit_summary, evidence = {}, {}, [], {}, {}
    old_source = ROOT / "results/resizable_native/20261008T155100Z_v1"
    old_suite = read(old_source / "suite.json")
    assert old_suite["order_sha256"] == suite["order_sha256"]
    reproduction = {}
    for condition in suite["conditions"]:
        name, profile, variant = condition["condition"], condition["profile"], condition["variant"]
        folder = source / name
        assert condition["checks_passed"] and condition["completed_requests"] == 1206
        for filename, expected in condition["evidence_sha256"].items():
            assert digest(folder / filename) == expected
        rows = records(folder / "requests.jsonl")
        events = records(folder / "budget_events.jsonl")
        expected_events = protocol["profile_events"][profile]
        assert len(rows) == 1206 and len(events) == len(expected_events)
        for event, expected in zip(events, expected_events, strict=True):
            assert event["request_index"] == expected["before_request_index"]
            assert event["hard_budget"] == {p: expected[p] for p in ("full", "swa")}
            assert event["accounting_ok"] and event["complete"]
            assert event["shortfall"] == {"full": 0, "swa": 0}
            transitions.append({"condition": name, **event})
        for index, row in enumerate(rows):
            assert row["request_index"] == index
            assert {k: row[k] for k in order[index]} == order[index]
            assert row["profile"] == profile and row["variant"] == variant
            assert all(row[k] for k in ("integrity_passed", "budget_checks_complete", "physical_accounting_ok"))
            assert 0 <= row["matched_tokens"] <= row["full_resident_match_tokens"] <= row["history_match_tokens"]
            assert row["capacity_loss_tokens"] == row["history_match_tokens"] - row["matched_tokens"]
            assert row["missed_input_tokens"] == row["unavoidable_new_input_tokens"] + row["capacity_loss_tokens"]
            expected = next(e for e in reversed(expected_events) if e["before_request_index"] <= index)
            assert row["hard_budget"] == {p: expected[p] for p in ("full", "swa")}
            f = row["after"]["frontier"]
            for pool in ("full", "swa"):
                assert row["after"]["resident"][pool] <= row["hard_budget"][pool]
                assert row["after"]["locked"][pool] == 0
                assert sum(e["tokens"] for e in row["native_free_events"] if e["pool"] == pool) == row["real_eviction_release"][pool]
                assert f[pool + "_dependency_tokens"] <= f[pool + "_protection_limit"]
            assert f["units"] <= 8
        counts = condition["frontier_counts"]
        assert counts.get("window_tail_splits", 0) == counts.get("input_boundary_splits", 0) == 0
        total = metrics(rows)
        for key in condition["totals"]:
            assert total[key] == condition["totals"][key]
        assert total["prompt_tokens"] == 48787785
        phase_metrics = {phase: metrics([row for row in rows if row["phase"] == phase]) for phase in PHASES}
        summaries[name] = {"total": total, "phases": phase_metrics, "frontier_counts": counts}
        all_rows[name] = rows
        unit_summary[name] = lifecycle(records(folder / "unit_events.jsonl"))
        assert unit_summary[name]["admitted_units"] == counts.get("registered", 0)
        assert unit_summary[name]["observed_reuse_events"] == counts.get("observed_unit_reuses", 0)
        evidence[name] = {**condition["evidence_sha256"], "summary.json": digest(folder / "summary.json")}
        if variant in ("lru", "v1"):
            old_name = profile + ("_lru" if variant == "lru" else "_frontier")
            prior = next(c for c in old_suite["conditions"] if c["condition"] == old_name)
            assert digest(old_source / old_name / "requests.jsonl") == prior["requests_sha256"]
            old_rows = records(old_source / old_name / "requests.jsonl")
            fields = ("matched_tokens", "full_resident_match_tokens", "history_match_tokens", "real_eviction_release")
            reproduction[name] = {field: all(a[field] == b[field] for a, b in zip(old_rows, rows, strict=True))
                                  for field in fields}
            assert all(reproduction[name].values()), (name, reproduction[name])
    assert set(all_rows) == {p + "_" + v for p in protocol["profiles"] for v in protocol["variants"]}
    comparisons, paired = {}, []
    for profile in protocol["profiles"]:
        for baseline in ("lru", "v1"):
            a, b = all_rows[profile + "_" + baseline], all_rows[profile + "_v2"]
            assert [r["history_match_tokens"] for r in a] == [r["history_match_tokens"] for r in b]
            key = profile + "_v2_vs_" + baseline
            comparisons[key] = {"total": delta(a, b), "phases": {
                phase: delta([r for r in a if r["phase"] == phase], [r for r in b if r["phase"] == phase])
                for phase in PHASES}}
        for index in range(1206):
            lru, v1, v2 = (all_rows[profile + "_" + variant][index] for variant in ("lru", "v1", "v2"))
            paired.append({"profile": profile, "index": index, "phase": v2["phase"],
                           "prompt_tokens": v2["prompt_tokens"], "lru_match": lru["matched_tokens"],
                           "v1_match": v1["matched_tokens"], "v2_match": v2["matched_tokens"],
                           "v2_minus_lru": v2["matched_tokens"] - lru["matched_tokens"],
                           "v2_minus_v1": v2["matched_tokens"] - v1["matched_tokens"]})
    for variant in ("lru", "v1", "v2"):
        a, b = all_rows["constant_" + variant], all_rows["shrink_restore_" + variant]
        comparisons[variant + "_resized_vs_constant"] = {"total": delta(a, b), "phases": {
            phase: delta([r for r in a if r["phase"] == phase], [r for r in b if r["phase"] == phase])
            for phase in PHASES}}
    acceptance = {phase: all(comparisons["shrink_restore_v2_vs_" + baseline]["phases"][phase]["matched_token_delta"] > 0
                             for baseline in ("lru", "v1")) for phase in ("half", "quarter")}
    summary = {"schema": "agentkv.retained_frontier_analysis.v2", "all_checks_passed": True,
               "total_executed_requests": suite["total_executed_requests"],
               "protocol": suite["protocol"], "protocol_sha256": suite["protocol_sha256"],
               "source_suite": str(source.relative_to(ROOT)), "source_suite_sha256": digest(source / "suite.json"),
               "v1_and_lru_reproduction": reproduction, "shrink_stage_acceptance": acceptance,
               "both_shrink_stages_improve": all(acceptance.values()), "conditions": summaries,
               "comparisons": comparisons, "unit_lifecycle": unit_summary,
               "transitions": transitions, "evidence_sha256": evidence,
               "limitations": protocol["limitations"] + [
                   "Single deterministic input trace and frozen capacity trajectory; no population confidence interval.",
                   "Unit matches are observed while protected; per-unit causal replacement benefit is not identified.",
                   "Current native adapter is Agent-only; no mixed-traffic ownership/scoped eviction integration."]}
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "summary.json", summary)
    with (output / "paired_requests.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(paired[0]))
        writer.writeheader()
        writer.writerows(paired)
    print(json.dumps({"all_checks_passed": True, "requests": 7236, "acceptance": acceptance,
                      "comparisons": {k: v for k, v in comparisons.items() if "v2_vs" in k}}, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.source, args.output)
