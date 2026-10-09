#!/usr/bin/env python3
"""Audit native v3 checkpoints with v2 reproduction and mechanism ablations."""

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


def analyze(source, output):
    source, output = source.resolve(), output.resolve()
    if not source.is_relative_to(ROOT / "results") or not output.is_relative_to(ROOT / "results"):
        raise ValueError("All evidence stays under experiment results")
    suite = read(source / "suite.json")
    assert suite["status"] == "complete" and suite["total_executed_requests"] == 7236
    protocol_path = ROOT / suite["protocol"]
    assert digest(protocol_path) == suite["protocol_sha256"]
    protocol = read(protocol_path)
    assert protocol["variants"] == ["v2", "partial", "v3"]
    assert protocol["profiles"] == ["constant", "shrink_restore"]
    assert protocol["requests"] == 1206 and protocol["complete_sessions"] == 20
    for name, expected in protocol["implementation_sha256"].items():
        assert digest(ROOT / "scripts" / name) == expected
        assert digest(source / "executed_sources" / name) == expected
    for name, expected in read(source / "executed_sources/manifest.json").items():
        assert digest(source / "executed_sources" / name) == expected
    for spec in protocol["settings"].values():
        assert digest(ROOT / spec["path"]) == spec["sha256"]
        assert digest(source / "executed_sources" / Path(spec["path"]).name) == spec["sha256"]
    order = read(source / "order.json")
    assert canonical_digest(order) == suite["order_sha256"] and len(order) == 1206
    old = ROOT / "results/retained_frontier/20261009_v2"
    old_suite = read(old / "suite.json")
    old_protocol = read(ROOT / old_suite["protocol"])
    assert digest(ROOT / old_suite["protocol"]) == old_suite["protocol_sha256"]
    assert old_suite["order_sha256"] == suite["order_sha256"]
    for key in ("workload_sha256", "physical_capacity", "page_size", "sliding_window_size",
                "chunked_prefill_tokens", "profile_events", "source_session_files"):
        assert protocol[key] == old_protocol[key]
    conditions, all_rows, units, evidence, transitions, reproduction = {}, {}, {}, {}, [], {}
    for condition in suite["conditions"]:
        name, profile, variant = condition["condition"], condition["profile"], condition["variant"]
        folder = source / name
        assert condition["checks_passed"] and condition["completed_requests"] == 1206
        for filename, expected in condition["evidence_sha256"].items():
            assert digest(folder / filename) == expected
        rows = records(folder / "requests.jsonl")
        budgets = records(folder / "budget_events.jsonl")
        expected_events = protocol["profile_events"][profile]
        assert len(rows) == 1206 and len(budgets) == len(expected_events)
        for event, expected in zip(budgets, expected_events, strict=True):
            assert event["complete"] and event["accounting_ok"]
            assert event["request_index"] == expected["before_request_index"]
            assert event["hard_budget"] == {pool: expected[pool] for pool in ("full", "swa")}
            assert event["shortfall"] == {"full": 0, "swa": 0}
            transitions.append({"condition": name, **event})
        for index, row in enumerate(rows):
            assert row["request_index"] == index
            assert {key: row[key] for key in order[index]} == order[index]
            assert row["profile"] == profile and row["variant"] == variant
            assert row["phase"] == PHASES[sum(index >= b for b in (301, 603, 904))]
            assert all(row[k] for k in ("integrity_passed", "budget_checks_complete", "physical_accounting_ok"))
            assert 0 <= row["matched_tokens"] <= row["full_resident_match_tokens"] <= row["history_match_tokens"]
            assert row["capacity_loss_tokens"] == row["history_match_tokens"] - row["matched_tokens"]
            assert row["missed_input_tokens"] == row["unavoidable_new_input_tokens"] + row["capacity_loss_tokens"]
            expected = next(e for e in reversed(expected_events) if e["before_request_index"] <= index)
            assert row["hard_budget"] == {pool: expected[pool] for pool in ("full", "swa")}
            frontier = row["after"]["frontier"]
            assert frontier["units"] <= 8
            for pool in ("full", "swa"):
                assert row["after"]["resident"][pool] <= row["hard_budget"][pool]
                assert row["after"]["locked"][pool] == 0
                assert frontier[pool + "_dependency_tokens"] <= frontier[pool + "_protection_limit"] <= row["hard_budget"][pool]
                assert sum(e["tokens"] for e in row["native_free_events"] if e["pool"] == pool) == row["real_eviction_release"][pool]
        counts = condition["frontier_counts"]
        # Native SWA already isolates chunk tails. Any new prototype split
        # would require a separate structural control before attribution.
        assert counts.get("window_tail_splits", 0) == counts.get("input_boundary_splits", 0) == 0, name
        total = metrics(rows)
        assert total["prompt_tokens"] == 48787785
        assert all(total[k] == v for k, v in condition["totals"].items())
        phase_metrics = {phase: metrics([r for r in rows if r["phase"] == phase]) for phase in PHASES}
        conditions[name] = {"total": total, "phases": phase_metrics, "frontier_counts": counts}
        all_rows[name] = rows
        unit_events = records(folder / "unit_events.jsonl")
        units[name] = lifecycle(unit_events)
        assert units[name]["admitted_units"] == counts.get("registered", 0)
        assert units[name]["observed_reuse_events"] == counts.get("observed_unit_reuses", 0)
        unit_by_id = {e["unit_id"]: e for e in unit_events if e["event_type"] == "admit"}
        for event in unit_events:
            if event.get("downgrade_reason"):
                prior = unit_by_id[event["predecessor_unit_ids"][0]]
                assert event["boundary_tokens"] < prior["boundary_tokens"]
        units[name]["downgrades_by_phase"] = {phase: dict(Counter(
            e["downgrade_reason"] for e in unit_events if e["phase"] == phase and e.get("downgrade_reason")))
            for phase in PHASES}
        evidence[name] = {**condition["evidence_sha256"], "summary.json": digest(folder / "summary.json")}
        if variant == "v2":
            prior = next(c for c in old_suite["conditions"] if c["condition"] == name)
            old_path = old / name / "requests.jsonl"
            assert digest(old_path) == prior["evidence_sha256"]["requests.jsonl"]
            original_rows = records(old_path)
            reproduction[name] = {key: all(a[key] == b[key] for a, b in zip(original_rows, rows, strict=True))
                for key in ("matched_tokens", "full_resident_match_tokens", "history_match_tokens", "real_eviction_release")}
            assert all(reproduction[name].values())
    assert set(all_rows) == {p + "_" + v for p in protocol["profiles"] for v in protocol["variants"]}
    archived_conditions = {}
    for profile in protocol["profiles"]:
        for variant in ("lru", "v1"):
            name = profile + "_" + variant
            prior = next(c for c in old_suite["conditions"] if c["condition"] == name)
            assert digest(old / name / "requests.jsonl") == prior["evidence_sha256"]["requests.jsonl"]
            rows = records(old / name / "requests.jsonl")
            assert len(rows) == 1206
            assert all({key: row[key] for key in order[i]} == order[i] for i, row in enumerate(rows))
            archived_conditions[name] = {"total": metrics(rows), "phases": {
                phase: metrics([r for r in rows if r["phase"] == phase]) for phase in PHASES}}
            all_rows[name] = rows
    comparisons, paired = {}, []
    for profile in protocol["profiles"]:
        for candidate, baseline in (("partial", "v2"), ("v3", "partial"), ("v3", "v2"),
                                    ("v3", "lru"), ("v3", "v1")):
            a, b = all_rows[profile + "_" + baseline], all_rows[profile + "_" + candidate]
            assert [r["history_match_tokens"] for r in a] == [r["history_match_tokens"] for r in b]
            key = profile + "_" + candidate + "_vs_" + baseline
            comparisons[key] = {"total": delta(a, b), "phases": {
                phase: delta([r for r in a if r["phase"] == phase], [r for r in b if r["phase"] == phase])
                for phase in PHASES}}
        for index in range(1206):
            row = {"profile": profile, "request_index": index,
                   "phase": all_rows[profile + "_v3"][index]["phase"],
                   "prompt_tokens": all_rows[profile + "_v3"][index]["prompt_tokens"]}
            for variant in ("lru", "v1", "v2", "partial", "v3"):
                row[variant + "_match"] = all_rows[profile + "_" + variant][index]["matched_tokens"]
            paired.append(row)
    acceptance = {phase: all(comparisons["shrink_restore_v3_vs_" + baseline]["phases"][phase]["matched_token_delta"] > 0
                            for baseline in ("v2", "lru", "v1")) for phase in ("half", "quarter", "restored")}
    summary = {"schema": "agentkv.checkpoint_frontier_analysis.v3", "all_checks_passed": True,
               "source_suite": str(source.relative_to(ROOT)), "source_suite_sha256": digest(source / "suite.json"),
               "protocol": suite["protocol"], "protocol_sha256": suite["protocol_sha256"],
               "total_executed_requests": 7236, "v2_reproduced": reproduction,
               "stage_acceptance": acceptance, "conditions": conditions, "archived_baselines": archived_conditions,
               "comparisons": comparisons, "unit_lifecycle": units, "transitions": transitions,
               "evidence_sha256": evidence, "limitations": protocol["limitations"] + [
                   "One previously explored deterministic trace; this is a mechanism experiment, not independent generalization.",
                   "Partial-only ablation isolates downgrade effects, but not per-victim causal replacement cost.",
                   "All policies retain the original max 8 units and 262144/4096 protection upper limits."]}
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "summary.json", summary)
    with (output / "paired_requests.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(paired[0]))
        writer.writeheader()
        writer.writerows(paired)
    print(json.dumps({"all_checks_passed": True, "requests": 7236, "acceptance": acceptance,
                      "comparisons": comparisons}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.source, args.output)
