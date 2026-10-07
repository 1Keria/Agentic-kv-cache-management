#!/usr/bin/env python3
"""Analyze exact-continuation runtime candidate and eviction diagnostics."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def percentile(values: list[float], q: float):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def client_summary(case_dir: Path) -> dict:
    requests = load_jsonl(case_dir / "client/requests.jsonl")
    summary = json.loads((case_dir / "client/summary.json").read_text())
    return {
        "requests": requests,
        "summary": summary,
        "input_hashes": [row["input_ids_sha256"] for row in requests],
        "output_hashes": [row["output_ids_sha256"] for row in requests],
        "cached_tokens_by_seq": {row["request_seq"]: int(row["cached_tokens"] or 0) for row in requests},
        "mean_ttft_seconds": statistics.fmean(row["ttft_seconds"] for row in requests),
        "p95_ttft_seconds": percentile([row["ttft_seconds"] for row in requests], 0.95),
        "mean_latency_seconds": statistics.fmean(row["latency_seconds"] for row in requests),
    }


def runtime_events(case_dir: Path) -> list[dict]:
    files = sorted((case_dir / "runtime_events").glob("events.rank0.pid*.jsonl"))
    events = []
    for path in files:
        events.extend(load_jsonl(path))
    return sorted(events, key=lambda row: (row["event_time_unix_ns"], row["event_seq"]))


def future_demand_index(requests: list[dict]) -> dict[str, list[int]]:
    result = defaultdict(list)
    for request in requests:
        for page in request["page_prefixes"]:
            result[page["stable_prefix_digest"]].append(request["request_seq"])
    return result


def has_future(index: dict[str, list[int]], digest: str, after_seq: int) -> bool:
    return any(seq > after_seq for seq in index.get(digest, ()))


def analyze_runtime_case(case_dir: Path, client: dict, control: dict) -> dict:
    events = runtime_events(case_dir)
    rid_to_seq = {row["request_id"]: row["request_seq"] for row in client["requests"]}
    demand_index = future_demand_index(client["requests"])
    latest_request_seq = 0
    decisions = {}
    ordered_decisions = []
    for event in events:
        kind = event["event_type"]
        if kind == "demand":
            latest_request_seq = rid_to_seq.get(event.get("request_id"), latest_request_seq)
        elif kind == "eviction_begin":
            decision = {
                "eviction_id": event["eviction_id"],
                "pool": event["pool"],
                "request_seq": latest_request_seq,
                "requested_tokens": event["requested_free_tokens"],
                "candidates": event["candidates"],
                "candidate_coverage_complete": event["candidate_coverage_complete"],
                "steps": [],
                "end": None,
            }
            decisions[event["eviction_id"]] = decision
            ordered_decisions.append(decision)
        elif kind == "eviction_step":
            decisions[event["eviction_id"]]["steps"].append(event)
        elif kind == "eviction_end":
            decisions[event["eviction_id"]]["end"] = event

    pool_metrics = {}
    for pool in ("full", "swa"):
        selected = [decision for decision in ordered_decisions if decision["pool"] == pool]
        steps = [step for decision in selected for step in decision["steps"]]
        initial_candidate_count = 0
        initial_candidate_tokens = 0
        new_tail_count = 0
        new_tail_tokens = 0
        new_tail_no_future_count = 0
        new_tail_no_future_tokens = 0
        parent_exposures = 0
        parent_exposed_tokens = 0
        initial_stage_tokens = 0
        exposed_stage_tokens = 0
        future_demand_initial_tokens = 0
        future_demand_exposed_tokens = 0
        deep_chain_events = 0
        max_chain_depth = 0
        locked_candidates = 0
        overshoot_tokens = 0
        incomplete = 0
        exposure_decisions = 0
        decisions_with_overshoot = 0
        candidate_hit_counts = Counter()
        victim_hit_counts = Counter()
        victim_logical_tokens = Counter()
        steps_per_decision = Counter()
        for decision in selected:
            steps_per_decision[len(decision["steps"])] += 1
            initial = {candidate["stable_prefix_digest"] for candidate in decision["candidates"]}
            initial_candidate_count += len(decision["candidates"])
            initial_candidate_tokens += sum(candidate["logical_tokens"] for candidate in decision["candidates"])
            locked_candidates += sum(int(candidate.get("lock_ref") or 0) > 0 for candidate in decision["candidates"])
            for candidate in decision["candidates"]:
                candidate_hit_counts[int(candidate.get("hit_count") or 0)] += 1
                if int(candidate.get("demand_count") or 0) == 0:
                    new_tail_count += 1
                    new_tail_tokens += candidate["logical_tokens"]
                    if not has_future(demand_index, candidate["stable_prefix_digest"], decision["request_seq"]):
                        new_tail_no_future_count += 1
                        new_tail_no_future_tokens += candidate["logical_tokens"]
            exposure_depth = {}
            decision_exposed = False
            for step in decision["steps"]:
                victim = step["victim"]
                victim_hit_counts[int(victim.get("hit_count") or 0)] += 1
                victim_logical_tokens[int(victim["logical_tokens"])] += 1
                digest = victim["stable_prefix_digest"]
                released = step["released_tokens"]
                depth = exposure_depth.get(digest, 0)
                max_chain_depth = max(max_chain_depth, depth)
                if depth > 0:
                    deep_chain_events += 1
                exposed = digest not in initial
                if exposed:
                    exposed_stage_tokens += released
                else:
                    initial_stage_tokens += released
                if has_future(demand_index, digest, decision["request_seq"]):
                    if exposed:
                        future_demand_exposed_tokens += released
                    else:
                        future_demand_initial_tokens += released
                if step.get("parent_exposed") and step.get("added_candidate"):
                    decision_exposed = True
                    parent_exposures += 1
                    added = step["added_candidate"]
                    parent_exposed_tokens += added["logical_tokens"]
                    exposure_depth[added["stable_prefix_digest"]] = depth + 1
            if decision["end"] is None:
                incomplete += 1
            else:
                overshoot_tokens += decision["end"]["overshoot_tokens"]
                decisions_with_overshoot += decision["end"]["overshoot_tokens"] > 0
            exposure_decisions += decision_exposed
        requested_tokens = sum(decision["requested_tokens"] for decision in selected)
        released_tokens = sum(step["released_tokens"] for step in steps)
        future_demand_released_tokens = future_demand_initial_tokens + future_demand_exposed_tokens
        pool_metrics[pool] = {
            "decisions": len(selected),
            "steps": len(steps),
            "requested_tokens": requested_tokens,
            "released_tokens": released_tokens,
            "overshoot_tokens": overshoot_tokens,
            "released_over_requested_ratio": None if requested_tokens == 0 else released_tokens / requested_tokens,
            "overshoot_over_requested_ratio": None if requested_tokens == 0 else overshoot_tokens / requested_tokens,
            "decisions_with_overshoot": decisions_with_overshoot,
            "steps_per_decision": {str(key): value for key, value in sorted(steps_per_decision.items())},
            "initial_candidate_count": initial_candidate_count,
            "initial_candidate_tokens": initial_candidate_tokens,
            "new_tail_count": new_tail_count,
            "new_tail_tokens": new_tail_tokens,
            "new_tail_no_future_count": new_tail_no_future_count,
            "new_tail_no_future_tokens": new_tail_no_future_tokens,
            "new_tail_no_future_ratio_count": None if new_tail_count == 0 else new_tail_no_future_count / new_tail_count,
            "new_tail_no_future_ratio_tokens": None if new_tail_tokens == 0 else new_tail_no_future_tokens / new_tail_tokens,
            "parent_exposures": parent_exposures,
            "decisions_with_parent_exposure": exposure_decisions,
            "parent_exposed_tokens": parent_exposed_tokens,
            "initial_stage_released_tokens": initial_stage_tokens,
            "exposed_stage_released_tokens": exposed_stage_tokens,
            "future_demand_initial_stage_tokens": future_demand_initial_tokens,
            "future_demand_exposed_stage_tokens": future_demand_exposed_tokens,
            "future_demand_released_tokens": future_demand_released_tokens,
            "future_demand_released_ratio": None if released_tokens == 0 else future_demand_released_tokens / released_tokens,
            "deep_chain_victim_steps": deep_chain_events,
            "max_exposure_chain_depth": max_chain_depth,
            "locked_candidates": locked_candidates,
            "incomplete_decisions": incomplete,
            "candidate_coverage_complete": all(decision["candidate_coverage_complete"] for decision in selected),
            "candidate_hit_count_distribution": {str(key): value for key, value in sorted(candidate_hit_counts.items())},
            "victim_hit_count_distribution": {str(key): value for key, value in sorted(victim_hit_counts.items())},
            "victim_logical_token_distribution": {str(key): value for key, value in sorted(victim_logical_tokens.items())},
        }

    if client["input_hashes"] != control["input_hashes"]:
        comparable = False
        cache_loss = None
    else:
        comparable = True
        per_request = []
        for request in client["requests"]:
            seq = request["request_seq"]
            delta = max(0, control["cached_tokens_by_seq"][seq] - client["cached_tokens_by_seq"][seq])
            per_request.append({"request_seq": seq, "extra_recompute_tokens_vs_control": delta})
        cache_loss = {
            "total_extra_recompute_tokens_vs_control": sum(row["extra_recompute_tokens_vs_control"] for row in per_request),
            "requests_with_extra_recompute": sum(row["extra_recompute_tokens_vs_control"] > 0 for row in per_request),
            "per_request": per_request,
        }
    return {
        "event_count": len(events),
        "event_types": {kind: sum(event["event_type"] == kind for event in events) for kind in sorted({event["event_type"] for event in events})},
        "pool_metrics": pool_metrics,
        "same_external_input_trace_as_control": comparable,
        "cache_loss": cache_loss,
        "mean_ttft_seconds": client["mean_ttft_seconds"],
        "p95_ttft_seconds": client["p95_ttft_seconds"],
        "mean_latency_seconds": client["mean_latency_seconds"],
    }


def analyze_suite(suite: Path) -> dict:
    names = ["01_control_lru_off", "02_control_lru_on", "03_pressure_lru", "04_pressure_slru"]
    clients = {name: client_summary(suite / name) for name in names}
    control = clients["02_control_lru_on"]
    traces_equal = all(client["input_hashes"] == control["input_hashes"] for client in clients.values())
    outputs_equal = all(client["output_hashes"] == control["output_hashes"] for client in clients.values())
    overhead = {
        "mean_ttft_ratio_on_over_off": clients["02_control_lru_on"]["mean_ttft_seconds"] / clients["01_control_lru_off"]["mean_ttft_seconds"],
        "mean_latency_ratio_on_over_off": clients["02_control_lru_on"]["mean_latency_seconds"] / clients["01_control_lru_off"]["mean_latency_seconds"],
        "cached_tokens_equal": clients["02_control_lru_on"]["cached_tokens_by_seq"] == clients["01_control_lru_off"]["cached_tokens_by_seq"],
    }
    runtime = {
        name: analyze_runtime_case(suite / name, clients[name], control)
        for name in ("02_control_lru_on", "03_pressure_lru", "04_pressure_slru")
    }
    def eviction_signature(case_name: str, pool: str) -> list[tuple]:
        signature = []
        for event in runtime_events(suite / case_name):
            if event.get("pool") != pool:
                continue
            if event["event_type"] == "eviction_begin":
                signature.append(("begin", event["requested_free_tokens"]))
            elif event["event_type"] == "eviction_step":
                signature.append(
                    (
                        "step",
                        event["victim"]["stable_prefix_digest"],
                        event["released_tokens"],
                        event["parent_exposed"],
                    )
                )
            elif event["event_type"] == "eviction_end":
                signature.append(("end", event["released_tokens"], event["overshoot_tokens"]))
        return signature
    policy_comparison = {
        "cached_tokens_equal": clients["03_pressure_lru"]["cached_tokens_by_seq"] == clients["04_pressure_slru"]["cached_tokens_by_seq"],
        "full_eviction_sequence_identical": eviction_signature("03_pressure_lru", "full") == eviction_signature("04_pressure_slru", "full"),
        "swa_eviction_sequence_identical": eviction_signature("03_pressure_lru", "swa") == eviction_signature("04_pressure_slru", "swa"),
    }
    manifest = json.loads((suite / "suite.json").read_text())
    valid_fixed_trace_comparison = traces_equal and all(
        runtime[name]["pool_metrics"][pool]["candidate_coverage_complete"]
        and runtime[name]["pool_metrics"][pool]["incomplete_decisions"] == 0
        for name in runtime
        for pool in ("full", "swa")
    )
    return {
        "schema": "agentkv_exact_diagnostics_analysis_v1",
        "suite": str(suite),
        "input_traces_identical": traces_equal,
        "output_traces_identical": outputs_equal,
        "trace_mode": manifest.get("trace_mode"),
        "valid_fixed_trace_comparison": valid_fixed_trace_comparison,
        "diagnostics_overhead": overhead,
        "clients": {
            name: {
                "requests": clients[name]["summary"]["requests"],
                "cached_tokens": clients[name]["summary"]["cached_tokens"],
                "mean_ttft_seconds": clients[name]["mean_ttft_seconds"],
                "p95_ttft_seconds": clients[name]["p95_ttft_seconds"],
                "mean_latency_seconds": clients[name]["mean_latency_seconds"],
            }
            for name in names
        },
        "runtime": runtime,
        "policy_comparison": policy_comparison,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze_suite(args.suite.resolve())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
