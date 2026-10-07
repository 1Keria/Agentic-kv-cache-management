#!/usr/bin/env python3
"""Analyze the fixed-trace Exposure Barrier isolation suite."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from analyze_exact_diagnostics import (
    analyze_runtime_case,
    client_summary,
    runtime_events,
)


def victim_signature(case_dir: Path, pool: str) -> list[tuple]:
    return [
        (
            event["victim"]["stable_prefix_digest"],
            event["released_tokens"],
            event.get("step_kind"),
        )
        for event in runtime_events(case_dir)
        if event.get("pool") == pool and event["event_type"] == "eviction_step"
    ]


def selected_same_chain_metrics(case_dir: Path, pool: str) -> dict:
    decisions = {}
    for event in runtime_events(case_dir):
        if event.get("pool") != pool:
            continue
        if event["event_type"] == "eviction_begin":
            decisions[event["eviction_id"]] = {
                "candidates": event["candidates"],
                "victims": [],
            }
        elif event["event_type"] == "eviction_step":
            decisions[event["eviction_id"]]["victims"].append(
                event["victim"]["stable_prefix_digest"]
            )
    pair_count = 0
    decisions_with_pair = 0
    for decision in decisions.values():
        parents = {
            candidate["stable_prefix_digest"]: candidate[
                "parent_stable_prefix_digest"
            ]
            for candidate in decision["candidates"]
        }
        paths = {}
        for digest in parents:
            path = {digest}
            current = digest
            while current in parents and parents[current] not in path:
                current = parents[current]
                path.add(current)
            paths[digest] = path
        local_pairs = 0
        victims = decision["victims"]
        for index, digest in enumerate(victims):
            for previous in victims[:index]:
                if digest in paths.get(previous, ()) or previous in paths.get(
                    digest, ()
                ):
                    local_pairs += 1
        pair_count += local_pairs
        decisions_with_pair += local_pairs > 0
    return {
        "selected_same_chain_pairs": pair_count,
        "decisions_with_selected_same_chain_pair": decisions_with_pair,
    }


def analyze_suite(suite: Path) -> dict:
    manifest = json.loads((suite / "suite.json").read_text())
    if manifest.get("status") != "completed":
        raise RuntimeError("Suite is not complete")
    cases = manifest["cases"]
    clients = {case["name"]: client_summary(suite / case["name"]) for case in cases}
    control_case = next(case for case in cases if case["regime"] == "control")
    control = clients[control_case["name"]]
    input_traces_identical = all(
        client["input_hashes"] == control["input_hashes"] for client in clients.values()
    )
    output_traces_identical = all(
        client["output_hashes"] == control["output_hashes"] for client in clients.values()
    )
    results = {}
    for case in cases:
        name = case["name"]
        client = clients[name]
        runtime = analyze_runtime_case(suite / name, client, control)
        full_step_kinds = Counter(
            event.get("step_kind")
            for event in runtime_events(suite / name)
            if event["event_type"] == "eviction_step" and event.get("pool") == "full"
        )
        swa_step_kinds = Counter(
            event.get("step_kind")
            for event in runtime_events(suite / name)
            if event["event_type"] == "eviction_step" and event.get("pool") == "swa"
        )
        full_selection_stages = Counter(
            event.get("selection_stage") or event.get("step_kind")
            for event in runtime_events(suite / name)
            if event["event_type"] == "eviction_step" and event.get("pool") == "full"
        )
        swa_selection_stages = Counter(
            event.get("selection_stage") or "native_lru"
            for event in runtime_events(suite / name)
            if event["event_type"] == "eviction_step" and event.get("pool") == "swa"
        )
        results[name] = {
            "regime": case["regime"],
            "strategy": case["strategy"],
            "policy": case["policy"],
            "exposure_barrier": case["exposure_barrier"],
            "cached_tokens": client["summary"]["cached_tokens"],
            "extra_recompute_tokens_vs_control": runtime["cache_loss"][
                "total_extra_recompute_tokens_vs_control"
            ],
            "requests_with_extra_recompute": runtime["cache_loss"][
                "requests_with_extra_recompute"
            ],
            "mean_ttft_seconds": runtime["mean_ttft_seconds"],
            "p95_ttft_seconds": runtime["p95_ttft_seconds"],
            "mean_latency_seconds": runtime["mean_latency_seconds"],
            "full": runtime["pool_metrics"]["full"],
            "swa": runtime["pool_metrics"]["swa"],
            "full_step_kind_distribution": {
                str(key): value for key, value in sorted(full_step_kinds.items(), key=lambda row: str(row[0]))
            },
            "swa_step_kind_distribution": {
                str(key): value for key, value in sorted(swa_step_kinds.items(), key=lambda row: str(row[0]))
            },
            "full_selection_stage_distribution": {
                str(key): value for key, value in sorted(full_selection_stages.items(), key=lambda row: str(row[0]))
            },
            "swa_selection_stage_distribution": {
                str(key): value for key, value in sorted(swa_selection_stages.items(), key=lambda row: str(row[0]))
            },
            "full_chain_selection": selected_same_chain_metrics(
                suite / name, "full"
            ),
            "swa_chain_selection": selected_same_chain_metrics(suite / name, "swa"),
            "full_victim_signature": victim_signature(suite / name, "full"),
            "swa_victim_signature": victim_signature(suite / name, "swa"),
        }

    comparisons = {}
    for regime in ("full_only", "swa_only", "joint"):
        by_strategy = {
            result["strategy"]: result
            for result in results.values()
            if result["regime"] == regime
        }
        lru = by_strategy["lru"]
        barrier = by_strategy["exposure_barrier"]
        slru = by_strategy["slru"]
        comparisons[regime] = {
            "barrier_minus_lru_cached_tokens": barrier["cached_tokens"] - lru["cached_tokens"],
            "barrier_recompute_reduction_vs_lru": lru[
                "extra_recompute_tokens_vs_control"
            ]
            - barrier["extra_recompute_tokens_vs_control"],
            "barrier_full_future_demand_release_reduction_vs_lru": lru["full"][
                "future_demand_released_tokens"
            ]
            - barrier["full"]["future_demand_released_tokens"],
            "barrier_full_exposed_future_demand_release_reduction_vs_lru": lru[
                "full"
            ]["future_demand_exposed_stage_tokens"]
            - barrier["full"]["future_demand_exposed_stage_tokens"],
            "barrier_full_overshoot_reduction_vs_lru": lru["full"]["overshoot_tokens"]
            - barrier["full"]["overshoot_tokens"],
            "barrier_swa_future_demand_release_reduction_vs_lru": lru["swa"][
                "future_demand_released_tokens"
            ]
            - barrier["swa"]["future_demand_released_tokens"],
            "barrier_swa_overshoot_reduction_vs_lru": lru["swa"]["overshoot_tokens"]
            - barrier["swa"]["overshoot_tokens"],
            "barrier_swa_deferred_same_chain_steps": barrier[
                "swa_selection_stage_distribution"
            ].get("deferred_same_chain", 0),
            "barrier_swa_selected_same_chain_pair_reduction_vs_lru": lru[
                "swa_chain_selection"
            ]["selected_same_chain_pairs"]
            - barrier["swa_chain_selection"]["selected_same_chain_pairs"],
            "barrier_full_victims_changed_vs_lru": barrier["full_victim_signature"]
            != lru["full_victim_signature"],
            "barrier_swa_victims_changed_vs_lru": barrier["swa_victim_signature"]
            != lru["swa_victim_signature"],
            "lru_slru_cached_tokens_equal": lru["cached_tokens"] == slru["cached_tokens"],
            "lru_slru_full_victims_equal": lru["full_victim_signature"]
            == slru["full_victim_signature"],
            "lru_slru_swa_victims_equal": lru["swa_victim_signature"]
            == slru["swa_victim_signature"],
        }

    valid = input_traces_identical and all(
        result[pool]["candidate_coverage_complete"]
        and result[pool]["incomplete_decisions"] == 0
        for result in results.values()
        for pool in ("full", "swa")
    )
    return {
        "schema": "agentkv_exposure_barrier_analysis_v1",
        "suite": str(suite),
        "valid_fixed_trace_comparison": valid,
        "input_traces_identical": input_traces_identical,
        "output_traces_identical": output_traces_identical,
        "output_trace_note": (
            "Generated outputs are observed only and do not construct later frozen inputs."
        ),
        "frozen_trace_sha256": manifest["frozen_trace_sha256"],
        "results": results,
        "comparisons": comparisons,
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
