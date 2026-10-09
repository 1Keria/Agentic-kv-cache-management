#!/usr/bin/env python3
"""Audit and compare uninterrupted native CPU cache budget experiments."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def records(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream]


def phase(index, boundaries):
    return ("initial", "half", "quarter", "restored")[sum(index >= b for b in boundaries)]


def metrics(rows):
    keys = ("prompt_tokens", "matched_tokens", "history_match_tokens", "capacity_loss_tokens",
            "unavoidable_new_input_tokens", "missed_input_tokens",
            "full_resident_but_joint_unavailable_tokens")
    result = {key: sum(row[key] for row in rows) for key in keys}
    result.update({"requests": len(rows),
                   "hit_rate": result["matched_tokens"] / result["prompt_tokens"],
                   "full_history_missing_tokens": sum(row["history_match_tokens"] -
                                                      row["full_resident_match_tokens"] for row in rows),
                   "loss_requests": sum(row["capacity_loss_tokens"] > 0 for row in rows),
                   "mean_frontier_units": sum(row["after"]["frontier"]["units"] for row in rows) / len(rows),
                   "min_frontier_units": min(row["after"]["frontier"]["units"] for row in rows),
                   "max_frontier_units": max(row["after"]["frontier"]["units"] for row in rows),
                   "request_eviction_calls": sum(row["eviction_calls"] for row in rows),
                   "request_native_eviction_release": {pool: sum(row["real_eviction_release"][pool] for row in rows)
                                                       for pool in ("full", "swa")}})
    assert result["capacity_loss_tokens"] == result["full_history_missing_tokens"] + result[
        "full_resident_but_joint_unavailable_tokens"]
    return result


def delta(left, right):
    """Report all wins and losses, with positive values meaning more matches."""
    differences = [b["matched_tokens"] - a["matched_tokens"] for a, b in zip(left, right, strict=True)]
    return {"matched_token_delta": sum(differences),
            "hit_rate_delta_pp": 100 * sum(differences) / sum(r["prompt_tokens"] for r in left),
            "positive_tokens": sum(max(value, 0) for value in differences),
            "negative_tokens": sum(min(value, 0) for value in differences),
            "improved_requests": sum(value > 0 for value in differences),
            "regressed_requests": sum(value < 0 for value in differences),
            "unchanged_requests": sum(value == 0 for value in differences)}


def write_csv(path, rows):
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze(source, output):
    source, output = source.resolve(), output.resolve()
    if not source.is_relative_to(ROOT / "results") or not output.is_relative_to(ROOT / "results"):
        raise ValueError("Sources and analysis must stay in experiment results")
    if output.exists():
        raise ValueError("Refusing to replace existing analysis")
    suite = read(source / "suite.json")
    assert suite["status"] == "complete"
    assert suite["requests"] == 1206 and suite["sessions"] == 20
    protocol_path = ROOT / suite["protocol"]
    assert digest(protocol_path) == suite["protocol_sha256"]
    protocol = read(protocol_path)
    assert suite["initial_physical_capacity"] == protocol["physical_capacity"]
    boundaries = suite["change_request_indices"][1:]
    assert boundaries == [301, 603, 904]
    order = read(source / "order.json")
    assert len(order) == suite["requests"]
    all_rows, condition_summary, evidence, transitions = {}, {}, {}, []
    for condition in suite["conditions"]:
        name = condition["condition"]
        folder = source / name
        rowset = records(folder / "requests.jsonl")
        events = records(folder / "budget_events.jsonl")
        assert digest(folder / "requests.jsonl") == condition["requests_sha256"]
        assert digest(folder / "budget_events.jsonl") == condition["budget_events_sha256"]
        assert len(rowset) == suite["requests"]
        profile, policy = name.rsplit("_", 1)
        expected_events = protocol["profile_events"][profile]
        assert [event["request_index"] for event in events] == [
            event["before_request_index"] for event in expected_events]
        for event, expected in zip(events, expected_events, strict=True):
            assert event["hard_budget"] == {pool: expected[pool] for pool in ("full", "swa")}
            assert event["complete"] and event["accounting_ok"]
            transitions.append({"condition": name, "request_index": event["request_index"],
                                "phase": expected["phase"], "budget": event["hard_budget"],
                                "before_resident": event["before"]["resident"],
                                "after_resident": event["after"]["resident"],
                                "requested_release": event["requested_release"],
                                "released": event["released"], "eviction_calls": event["eviction_calls"],
                                "shortfall": event["shortfall"], "complete": event["complete"],
                                "units_after": event["protection"]["units"]})
        for index, row in enumerate(rowset):
            assert row["request_index"] == index
            assert row["profile"] == profile and row["policy"] == policy
            assert {key: row[key] for key in order[index]} == order[index]
            assert all(row[key] for key in ("budget_checks_complete", "physical_accounting_ok", "integrity_passed"))
            assert 0 <= row["matched_tokens"] <= row["full_resident_match_tokens"] <= row[
                "history_match_tokens"] <= row["prompt_tokens"]
            assert row["capacity_loss_tokens"] == row["history_match_tokens"] - row["matched_tokens"]
            assert row["missed_input_tokens"] == row["capacity_loss_tokens"] + row["unavoidable_new_input_tokens"]
            expected = expected_events[max(i for i, e in enumerate(expected_events)
                                           if e["before_request_index"] <= index)]
            assert row["hard_budget"] == {pool: expected[pool] for pool in ("full", "swa")}
            for pool in ("full", "swa"):
                assert row["after"]["resident"][pool] <= row["hard_budget"][pool]
                assert row["after"]["locked"][pool] == 0
                assert sum(e["tokens"] for e in row["native_free_events"] if e["pool"] == pool) == row[
                    "real_eviction_release"][pool]
            f = row["after"]["frontier"]
            if policy == "frontier":
                assert f["units"] <= protocol["frontier_upper_limits"]["max_units"]
                assert f["full_dependency_tokens"] <= f["full_protection_limit"] <= row["hard_budget"]["full"]
                assert f["swa_dependency_tokens"] <= f["swa_protection_limit"] <= row["hard_budget"]["swa"]
            row["phase"] = phase(index, boundaries)
        # Extra splits would require an additional structural control before
        # attributing a difference to protection alone.
        counts = condition["frontier_counts"]
        assert counts.get("input_boundary_splits", 0) == counts.get("window_tail_splits", 0) == 0
        calculated = metrics(rowset)
        assert calculated["matched_tokens"] == condition["totals"]["matched_tokens"]
        assert calculated["capacity_loss_tokens"] == condition["totals"]["capacity_loss_tokens"]
        all_rows[name] = rowset
        slices = {label: metrics([row for row in rowset if row["phase"] == label])
                  for label in ("initial", "half", "quarter", "restored")}
        for label, values in [(None, calculated), *slices.items()]:
            relevant_events = [event for event in events
                               if label is None or phase(event["request_index"], boundaries) == label]
            values["budget_event_eviction_calls"] = sum(e["eviction_calls"] for e in relevant_events)
            values["budget_event_eviction_release"] = {pool: sum(e["released"][pool] for e in relevant_events)
                                                       for pool in ("full", "swa")}
            values["all_native_eviction_release"] = {
                pool: values["request_native_eviction_release"][pool] +
                      values["budget_event_eviction_release"][pool] for pool in ("full", "swa")}
        for pool in ("full", "swa"):
            assert calculated["all_native_eviction_release"][pool] == condition[
                "native_eviction_tokens"].get(pool, 0)
        counter_deltas, previous_counts = {}, {}
        for label in ("initial", "half", "quarter", "restored"):
            last = next(row for row in reversed(rowset) if row["phase"] == label)
            current_counts = last["after"]["frontier"]["counters"]
            counter_deltas[label] = {key: current_counts.get(key, 0) - previous_counts.get(key, 0)
                                    for key in set(current_counts) | set(previous_counts)}
            assert all(value >= 0 for value in counter_deltas[label].values())
            previous_counts = current_counts
        condition_summary[name] = {"total": calculated, "phases": slices, "frontier_counts": counts,
                                   "frontier_counter_deltas_by_phase": counter_deltas}
        evidence[name] = {filename: digest(folder / filename) for filename in (
            "summary.json", "requests.jsonl", "budget_events.jsonl")}
    assert set(all_rows) == {f"{p}_{s}" for p in protocol["profiles"] for s in protocol["policies"]}
    reference = next(iter(all_rows.values()))
    for rowset in all_rows.values():
        assert [r["history_match_tokens"] for r in rowset] == [r["history_match_tokens"] for r in reference]
    comparisons, paired = {}, []
    for profile in protocol["profiles"]:
        lru, frontier = all_rows[profile + "_lru"], all_rows[profile + "_frontier"]
        comparisons[profile] = {"total": delta(lru, frontier),
                                "phases": {label: delta([r for r in lru if r["phase"] == label],
                                                         [r for r in frontier if r["phase"] == label])
                                           for label in ("initial", "half", "quarter", "restored")},
                                "context_length_buckets": {}}
        for label in ("initial", "half", "quarter", "restored"):
            bucket_results = {}
            for bucket, lower, upper in (("0_16k", 0, 16384), ("16k_32k", 16384, 32768),
                                         ("32k_64k", 32768, 65536), ("64k_plus", 65536, float("inf"))):
                select = lambda row: row["phase"] == label and lower < row["prompt_tokens"] <= upper
                a, b = [r for r in lru if select(r)], [r for r in frontier if select(r)]
                if a:
                    bucket_results[bucket] = {"lru": metrics(a), "frontier": metrics(b),
                                              "delta": delta(a, b)}
            comparisons[profile]["context_length_buckets"][label] = bucket_results
        for a, b in zip(lru, frontier, strict=True):
            paired.append({"profile": profile, "request_index": a["request_index"], "phase": a["phase"],
                           "session_id": a["session_id"], "task_id": a["task_id"], "turn_index": a["turn_index"],
                           "prompt_tokens": a["prompt_tokens"], "history_match_tokens": a["history_match_tokens"],
                           "lru_matched_tokens": a["matched_tokens"], "frontier_matched_tokens": b["matched_tokens"],
                           "delta_tokens": b["matched_tokens"] - a["matched_tokens"],
                           "lru_full_missing": a["history_match_tokens"] - a["full_resident_match_tokens"],
                           "frontier_full_missing": b["history_match_tokens"] - b["full_resident_match_tokens"],
                           "lru_joint_gap": a["full_resident_but_joint_unavailable_tokens"],
                           "frontier_joint_gap": b["full_resident_but_joint_unavailable_tokens"]})
    profile_cost, recovery = {}, {}
    for policy in protocol["policies"]:
        constant, changing = all_rows["constant_" + policy], all_rows["shrink_restore_" + policy]
        profile_cost[policy] = {"total": delta(constant, changing),
                                "phases": {label: delta([r for r in constant if r["phase"] == label],
                                                         [r for r in changing if r["phase"] == label])
                                           for label in ("initial", "half", "quarter", "restored")}}
        assert profile_cost[policy]["phases"]["initial"]["matched_token_delta"] == 0
        recovery[policy] = {str(window): delta(constant[904:904 + window], changing[904:904 + window])
                            for window in (20, 60, 120, suite["requests"] - 904)}
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "agentkv.resizable_native_analysis.v1", "source": str(source.relative_to(ROOT)),
              "source_suite_sha256": digest(source / "suite.json"), "protocol_sha256": suite["protocol_sha256"],
              "all_checks_passed": True, "requests_per_condition": suite["requests"], "total_requests": 4824,
              "conditions": condition_summary, "protection_vs_lru": comparisons,
              "changing_vs_constant": profile_cost, "recovery_vs_constant": recovery,
              "transitions": transitions, "evidence_sha256": evidence,
              "eviction_metric_scope": "Request and budget-event native evictions are listed separately and combined explicitly. Natural completion/page-tail frees are not eviction metrics.",
              "limitations": suite["limitations"]}
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    write_csv(output / "paired_requests.csv", paired)
    phase_rows = []
    for name, condition in condition_summary.items():
        for label, values in condition["phases"].items():
            phase_rows.append({"condition": name, "phase": label, **{key: value for key, value in values.items()
                                                                      if not isinstance(value, dict)}})
    write_csv(output / "phase_metrics.csv", phase_rows)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.source, args.output)
    print(json.dumps({"all_checks_passed": result["all_checks_passed"],
                      "protection_vs_lru": result["protection_vs_lru"]}, ensure_ascii=False))
