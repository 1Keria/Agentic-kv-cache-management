#!/usr/bin/env python3
"""Analyze observation-only Full/SWA reclaim traces.

The analysis reports what the runtime observer actually saw. It does not use
future demand to score a victim and never turns a historical shortfall into an
avoidable-loss claim without a legal same-state counterfactual.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime
import hashlib
import json
from pathlib import Path
import statistics

from prepare_data import ROOT, digest_file, save_json


def load_json(path):
    return json.loads(path.read_text())


def dist(values):
    values = [float(v) for v in values]
    if not values:
        return {"count": 0, "min": None, "p50": None, "p95": None, "max": None, "mean": None}
    ordered = sorted(values)
    def percentile(q):
        index = (len(ordered) - 1) * q
        low, high = int(index), min(int(index) + 1, len(ordered) - 1)
        return ordered[low] + (ordered[high] - ordered[low]) * (index - low)
    return {"count": len(ordered), "min": ordered[0], "p50": percentile(.5),
            "p95": percentile(.95), "max": ordered[-1], "mean": statistics.mean(ordered)}


def event_path(run):
    files = sorted((run / "runtime_events").glob("events.rank0.pid*.jsonl"))
    if len(files) != 1:
        raise ValueError(f"Expected one rank-zero event file in {run}, found {len(files)}")
    return files[0]


def read_events(run):
    events = []
    previous = 0
    with event_path(run).open() as stream:
        for line in stream:
            event = json.loads(line)
            if event.get("event_seq", 0) != previous + 1:
                raise ValueError(f"Missing or non-monotonic observer event sequence in {run}")
            previous = event["event_seq"]
            events.append(event)
    if not events or events[0]["event_type"] != "observer_start":
        raise ValueError(f"Missing observer_start in {run}")
    return events


def run_request_map(run):
    rows = {}
    with (run / "measurement/requests.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            key = row.get("meta_info", {}).get("id")
            if key:
                rows[str(key)] = row
    return rows


def measurement_events(events, request_rows):
    """Exclude protocol/shape warmup from *all* mechanism aggregates.

    Page definitions are deliberately read from the unsliced stream by offline
    consumers: a flush resets materialization history, not page identities.
    """
    first = next(event for event in events if event["event_type"] == "match"
                 and event["request_id"] in request_rows)
    flushes = [event for event in events if event["event_type"] == "flush"
               and event["event_seq"] < first["event_seq"]]
    if not flushes:
        raise ValueError("No empty-cache boundary before formal measurement")
    boundary = flushes[-1]["event_seq"]
    measured = [event for event in events if event["event_seq"] > boundary]
    if any(event["event_type"] == "flush" for event in measured):
        raise ValueError("Unexpected flush inside/after the measurement window")
    return measured, {"flush_event_seq": boundary,
                      "first_formal_match_event_seq": first["event_seq"],
                      "last_event_seq": events[-1]["event_seq"],
                      "excluded_pre_measurement_events": sum(event["event_seq"] <= boundary for event in events)}


def match_decomposition(event):
    history = int(event.get("historical_joint_tokens", 0))
    full = int(event.get("inspected_full_tokens", 0))
    native = int(event.get("native_matched_tokens", 0))
    if history < native or full < native:
        raise ValueError("Materialization/reference or resident Full shorter than native match")
    return {"history_beyond_resident_full": max(0, history - full),
            "resident_full_without_joint_match": min(history, full) - native}


def chain_followups(reclaims):
    immediate, eventually = [], []
    for reclaim in reclaims.values():
        for pool in ("full", "swa"):
            previous = None
            exposed_pages = set()
            for event in sorted((step for step in reclaim["steps"] if step["pool"] == pool),
                                key=lambda item: item["event_seq"]):
                victim_end = event["victim"].get("end_page")
                if victim_end in exposed_pages:
                    eventually.append(event)
                if previous and previous.get("parent_exposed"):
                    exposed = previous.get("exposed_parent") or {}
                    if victim_end == exposed.get("end_page"):
                        immediate.append(event)
                if event.get("parent_exposed"):
                    exposed_pages.add(event["exposed_parent"]["end_page"])
                previous = event
    return immediate, eventually


def event_summary(run, policy, selected):
    request_rows = run_request_map(run)
    all_events = read_events(run)
    events, scope = measurement_events(all_events, request_rows)
    counts = Counter(event["event_type"] for event in events)
    by_request = defaultdict(list)
    reclaims = {}
    drives = {}
    component_frees = []
    victims = []
    matches = []
    drive_candidates = defaultdict(list)
    drive_candidate_tokens = defaultdict(list)
    drive_candidate_locked = Counter()
    drive_candidate_other_locked = Counter()
    for event in events:
        kind = event["event_type"]
        if kind == "match":
            matches.append(event)
            by_request[event["request_id"]].append(event)
        elif kind == "reclaim_begin":
            reclaims[event["reclaim_id"]] = {"begin": event, "drives": {}, "steps": []}
        elif kind == "drive_begin":
            drives[(event["reclaim_id"], event["pool"])] = event
            reclaims.setdefault(event["reclaim_id"], {"begin": None, "drives": {}, "steps": []})["drives"][event["pool"]] = {"begin": event}
            if event.get("active"):
                candidates = event.get("candidates", [])
                pool = event["pool"]
                drive_candidates[pool].append(len(candidates))
                drive_candidate_tokens[pool].append(sum(int(item.get("logical_tokens", 0)) for item in candidates))
                drive_candidate_locked[pool] += sum(
                    int(item.get(pool + "_lock_ref", 0)) > 0
                    for item in candidates
                )
                other = "swa" if pool == "full" else "full"
                drive_candidate_other_locked[pool] += sum(
                    int(item.get(other + "_lock_ref", 0)) > 0 for item in candidates
                )
        elif kind == "victim_step":
            victims.append(event)
            reclaims.setdefault(event["reclaim_id"], {"begin": None, "drives": {}, "steps": []})["steps"].append(event)
        elif kind == "component_free":
            component_frees.append(event)
        elif kind == "drive_end":
            drives.setdefault((event["reclaim_id"], event["pool"]), {})["end"] = event
            reclaim = reclaims.setdefault(event["reclaim_id"], {"begin": None, "drives": {}, "steps": []})
            reclaim["drives"].setdefault(event["pool"], {})["end"] = event
        elif kind == "reclaim_end":
            reclaims.setdefault(event["reclaim_id"], {"begin": None, "drives": {}, "steps": []})["end"] = event

    request_count = len(request_rows)
    matched_request_ids = {event["request_id"] for event in matches if event["request_id"] in request_rows}
    # The scheduler may call match_prefix more than once for one request while
    # it revisits the waiting/running path. For request-level accounting use
    # the final observed match event; retain the raw event count separately.
    terminal_matches = {}
    for event in matches:
        terminal_matches[event["request_id"]] = event
    # The observer also sees protocol/shape-warmup requests. Restrict all
    # request-level totals to the formal measurement request IDs.
    terminal_matches = [event for request_id, event in terminal_matches.items()
                        if request_id in request_rows]
    full_steps = [event for event in victims if event["pool"] == "full"]
    swa_steps = [event for event in victims if event["pool"] == "swa"]
    repeated_chain = [event for event in victims if event.get("parent_exposed")]
    # A victim is an ancestor exposed by an earlier deletion in the same reclaim
    # when its parent end page equals a previous victim end page. This is a
    # structural fact, independent of any future request.
    same_chain, later_same_chain = chain_followups(reclaims)

    overshoot = []
    reclaim_rows = []
    for reclaim_id, reclaim in sorted(reclaims.items()):
        begin = reclaim.get("begin") or {}
        requested = {"full": int(begin.get("requested_full_tokens", 0)),
                     "swa": int(begin.get("requested_swa_tokens", 0))}
        released = (reclaim.get("end") or {}).get("released", {})
        released = {"full": int(released.get("full", 0)), "swa": int(released.get("swa", 0))}
        for pool in ("full", "swa"):
            if requested[pool] > 0:
                overshoot.append(max(0, released[pool] - requested[pool]))
        reclaim_rows.append({"reclaim_id": reclaim_id, "requested": requested, "released": released,
                             "overshoot": {pool: max(0, released[pool] - requested[pool]) for pool in requested},
                             "steps": len(reclaim["steps"]),
                             "full_steps": sum(step["pool"] == "full" for step in reclaim["steps"]),
                             "swa_steps": sum(step["pool"] == "swa" for step in reclaim["steps"])})

    free_by_pool = defaultdict(int)
    free_by_driver = defaultdict(int)
    free_sizes = defaultdict(list)
    for event in component_frees:
        pool = event["pool"]
        tokens = int(event["freed_tokens"])
        free_by_pool[pool] += tokens
        free_by_driver[(event.get("driver"), pool)] += tokens
        free_sizes[pool].append(tokens)

    hist_shortfalls = [int(event.get("history_shortfall_tokens", 0)) for event in terminal_matches]
    hist_joint = [int(event.get("historical_joint_tokens", 0)) for event in terminal_matches]
    native = [int(event.get("native_matched_tokens", 0)) for event in terminal_matches]
    decomposed = [match_decomposition(event) for event in terminal_matches]
    all_formal_matches = [event for event in matches if event["request_id"] in request_rows]
    client_differences = Counter(int(event["native_matched_tokens"]) - int(request_rows[event["request_id"]]["cached_tokens"])
                                 for event in terminal_matches)
    audit = {
        "all_formal_inspected_native_agreements": sum(event.get("inspected_match_agrees") is True for event in all_formal_matches),
        "all_formal_match_events": len(all_formal_matches),
        "terminal_inspected_native_disagreements": sum(event.get("inspected_match_agrees") is not True for event in terminal_matches),
        "terminal_client_cached_token_deltas": dict(client_differences),
        "history_below_native_count": sum(event["historical_joint_tokens"] < event["native_matched_tokens"] for event in terminal_matches),
        "resident_full_below_native_count": sum(event["inspected_full_tokens"] < event["native_matched_tokens"] for event in terminal_matches),
        "reclaim_begin_end_complete": all(reclaim.get("begin") and reclaim.get("end") for reclaim in reclaims.values()),
        "drive_begin_end_complete": all(drive.get("begin") and drive.get("end") for reclaim in reclaims.values()
                                        for drive in reclaim["drives"].values()),
        "component_free_matches_reclaim_released": all(
            free_by_pool[pool] == sum(row["released"][pool] for row in reclaim_rows) for pool in ("full", "swa")),
        "victim_step_matches_reclaim_released": all(
            sum(int(step["released"][pool]) for step in reclaim["steps"]) == int(reclaim["end"]["released"][pool])
            for reclaim in reclaims.values() for pool in ("full", "swa")),
        "formal_requests_with_finished_commit": len({event["request_id"] for event in events
                                                     if event["event_type"] == "request_commit" and event["finished"]
                                                     and event["request_id"] in request_rows}),
    }
    missing_cause = Counter()
    missing_cause_driver = Counter()
    for event in terminal_matches:
        for key, value in (event.get("missing_full_cause_tokens") or {}).items():
            missing_cause[key] += int(value)
            try:
                missing_cause_driver[json.loads(key).get("driver", "unknown")] += int(value)
            except json.JSONDecodeError:
                missing_cause_driver["unknown"] += int(value)
    terminal_by_key = {}
    for request_id, event in ((event["request_id"], event) for event in terminal_matches):
        row = request_rows[request_id]
        key = f"{row['session_id']}:{int(row['turn_index'])}"
        terminal_by_key[key] = {
            "native": int(event.get("native_matched_tokens", 0)),
            "historical_joint": int(event.get("historical_joint_tokens", 0)),
            "shortfall": int(event.get("history_shortfall_tokens", 0)),
            "resident_full": int(event.get("inspected_full_tokens", 0)),
            **match_decomposition(event),
        }

    # Locate the deepest missing joint-match boundary for each request. Old
    # tombstones far above a surviving window need not explain a hit loss.
    by_seq = {event["event_seq"]: event for event in events}
    boundary_counts = Counter()
    boundary_driver_gaps = Counter()
    boundary_free_sizes, boundary_waits = [], []
    for event in terminal_matches:
        if event["history_shortfall_tokens"] <= 0:
            continue
        boundary_counts["requests_with_shortfall"] += 1
        desired = min(event["historical_joint_tokens"], event["inspected_full_tokens"])
        missing = [node for node in event["resident_path"]
                   if event["native_matched_tokens"] < node["path_tokens"] <= desired and node["swa_tokens"] == 0]
        if not missing:
            boundary_counts["no_missing_resident_node_boundary"] += 1
            continue
        deepest = missing[-1]
        hole = next(hole for hole in event["swa_holes"] if hole["end_page"] == deepest["end_page"])
        cause = hole.get("last_free")
        if not cause:
            boundary_counts["deepest_boundary_without_observed_free"] += 1
            continue
        free = by_seq.get(cause["event_seq"])
        if not free or free["event_type"] != "component_free" or free["pool"] != "swa":
            raise ValueError("SWA boundary cause does not identify a measurement component free")
        boundary_counts["deepest_boundary_with_observed_swa_free"] += 1
        boundary_counts["driver_" + str(free["driver"])] += 1
        boundary_driver_gaps[free["driver"]] += deepest["path_tokens"] - event["native_matched_tokens"]
        boundary_free_sizes.append(free["freed_tokens"])
        boundary_waits.append((event["time_unix_ns"] - free["time_unix_ns"]) / 1e9)

    selected_rows = []
    for case in selected:
        key = next((rid for rid, row in request_rows.items()
                    if row["session_id"] == case["session_id"] and int(row["turn_index"]) == case["turn_index"]), None)
        observations = by_request.get(key, []) if key else []
        terminal = observations[-1:] if observations else []
        selected_match_rows = []
        for event in terminal:
            holes = event.get("swa_holes", [])
            selected_match_rows.append({"native": event["native_matched_tokens"],
                                        "historical_joint": event["historical_joint_tokens"],
                                        "shortfall": event["history_shortfall_tokens"],
                                        "resident_full": event["inspected_full_tokens"],
                                        **match_decomposition(event),
                                        "missing_full_cause_tokens": sum((event.get("missing_full_cause_tokens") or {}).values()),
                                        "swa_hole_count": len(holes),
                                        "swa_hole_examples": [
                                            {"end_page": hole.get("end_page"), "path_tokens": hole.get("path_tokens"),
                                             "last_free": hole.get("last_free")}
                                            for hole in holes[:3]
                                        ]})
        selected_rows.append({**case, "request_id_observed": key, "match_event_count": len(observations),
                              "terminal_match_used": bool(terminal),
                              "matches": selected_match_rows})

    return {
        "policy": policy, "event_file": str(event_path(run).relative_to(ROOT)),
        "event_file_sha256": digest_file(event_path(run)), "requests": request_count,
        "request_ids_with_observed_match": len(matched_request_ids),
        "match_event_count": len(matches),
        "terminal_match_count": len(terminal_matches),
        "measurement_scope": scope, "audit": audit,
        "match_request_coverage": len(matched_request_ids) / request_count if request_count else None,
        "event_counts": dict(counts),
        "reclaims": len(reclaims), "reclaim_rows": reclaim_rows,
        "reclaim_requested_tokens": {"full": sum(row["requested"]["full"] for row in reclaim_rows),
                                     "swa": sum(row["requested"]["swa"] for row in reclaim_rows)},
        "reclaim_released_tokens": {"full": sum(row["released"]["full"] for row in reclaim_rows),
                                     "swa": sum(row["released"]["swa"] for row in reclaim_rows)},
        "overshoot_tokens": {"full": sum(row["overshoot"]["full"] for row in reclaim_rows),
                              "swa": sum(row["overshoot"]["swa"] for row in reclaim_rows)},
        "victims": {"full_steps": len(full_steps), "swa_steps": len(swa_steps),
                    "parent_exposed_steps": len(repeated_chain),
                    "same_chain_followup_steps": len(same_chain),
                    "same_chain_followup_by_pool": dict(Counter(event["pool"] for event in same_chain)),
                    "same_chain_eventually_selected_by_pool": dict(Counter(event["pool"] for event in later_same_chain)),
                    "full_parent_exposed_steps": sum(event["pool"] == "full" for event in repeated_chain),
                    "swa_parent_exposed_steps": sum(event["pool"] == "swa" for event in repeated_chain),
                    "full_victim_tokens": sum(int(event["victim"].get("logical_tokens", 0)) for event in full_steps),
                    "swa_victim_tokens": sum(int(event["victim"].get("logical_tokens", 0)) for event in swa_steps)},
        "component_free_tokens": dict(free_by_pool),
        "component_free_tokens_by_driver": {f"{driver}:{pool}": value for (driver, pool), value in free_by_driver.items()},
        "component_free_size_distribution": {pool: dist(values) for pool, values in free_sizes.items()},
        "active_drive_candidate_counts": {pool: dist(values) for pool, values in drive_candidates.items()},
        "active_drive_candidate_logical_tokens": {pool: dist(values) for pool, values in drive_candidate_tokens.items()},
        "active_drive_candidate_locked_entries": dict(drive_candidate_locked),
        "active_drive_candidate_other_component_locked_entries": dict(drive_candidate_other_locked),
        "match_tokens": {"native": sum(native), "historical_joint": sum(hist_joint),
                          "observed_materialization_shortfall": sum(hist_shortfalls),
                          "history_beyond_resident_full": sum(row["history_beyond_resident_full"] for row in decomposed),
                          "resident_full_without_joint_match": sum(row["resident_full_without_joint_match"] for row in decomposed),
                          "resident_full_without_joint_share": sum(row["resident_full_without_joint_match"] for row in decomposed) / sum(hist_shortfalls),
                          "native_hit_rate_over_prompt": sum(native) / sum(row["prompt_tokens"] for row in request_rows.values())},
        "request_level_match_observations": terminal_by_key,
        "deepest_missing_joint_boundary": {"counts": dict(boundary_counts),
                                          "potential_boundary_tokens_by_free_driver": dict(boundary_driver_gaps),
                                          "original_swa_free_size_tokens": dist(boundary_free_sizes),
                                          "time_since_free_seconds": dist(boundary_waits),
                                          "is_avoidable_loss_estimate": False},
        "match_shortfall_distribution": dist(hist_shortfalls),
        "missing_full_cause_tokens_by_event": dict(missing_cause),
        "missing_full_cause_tokens_by_driver": dict(missing_cause_driver),
        "selected_case_observations": selected_rows,
        "limitations": [
            "Observer is rank-zero and records the official cache's native decisions without changing them.",
            "A match event is emitted only when the scheduler passes a request object; coverage is reported explicitly.",
            "Historical materialization uses page-aligned observer state since the last flush; it is not an infinite oracle and is not an avoidable-recompute label.",
            "Resident Full/reference decomposition describes present availability, not loss avoidable by a finite-budget policy.",
            "Legal equal-release local alternatives are analyzed separately, not used as aggregate policy improvement.",
            "Time in this diagnosis is not a policy-ranking measurement because observation logging changes overhead.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    suite = args.suite.resolve()
    selected = load_json(suite / "selected_cases.json")["cases"]
    state = load_json(suite / "suite.json")
    if state.get("status") != "completed":
        raise ValueError("Mechanism suite is not complete")
    reports = []
    for run_info in state["runs"]:
        run = suite / run_info["path"]
        reports.append(event_summary(run, run_info["policy"], selected))
    by_policy = {report["policy"]: report for report in reports}
    paired = {}
    if {"lru", "slru"} <= set(by_policy):
        lru, slru = by_policy["lru"], by_policy["slru"]
        paired = {
            "policy_event_counts_equal": lru["event_counts"] == slru["event_counts"],
            "match_coverage": {"lru": lru["match_request_coverage"], "slru": slru["match_request_coverage"]},
            "parent_exposed_steps": {"lru": lru["victims"]["parent_exposed_steps"], "slru": slru["victims"]["parent_exposed_steps"]},
            "same_chain_followup_steps": {"lru": lru["victims"]["same_chain_followup_steps"], "slru": slru["victims"]["same_chain_followup_steps"]},
            "observed_materialization_shortfall_tokens": {"lru": lru["match_tokens"]["observed_materialization_shortfall"],
                                                            "slru": slru["match_tokens"]["observed_materialization_shortfall"]},
            "component_free_tokens": {"lru": lru["component_free_tokens"], "slru": slru["component_free_tokens"]},
        }
        lru_requests = lru["request_level_match_observations"]
        slru_requests = slru["request_level_match_observations"]
        common_keys = sorted(set(lru_requests) & set(slru_requests))
        common_shortfall = [
            (lru_requests[key]["shortfall"], slru_requests[key]["shortfall"])
            for key in common_keys
        ]
        paired["request_level_shortfall"] = {
            "paired_request_keys": len(common_keys),
            "lru_at_least_8192": sum(left >= 8192 for left, _ in common_shortfall),
            "slru_at_least_8192": sum(right >= 8192 for _, right in common_shortfall),
            "both_at_least_8192": sum(left >= 8192 and right >= 8192 for left, right in common_shortfall),
            "both_minimum_shortfall_tokens": sum(min(left, right) for left, right in common_shortfall),
            "both_at_least_8192_minimum_shortfall_tokens": sum(min(left, right) for left, right in common_shortfall
                                                              if left >= 8192 and right >= 8192),
            "lru_sum": sum(left for left, _ in common_shortfall),
            "slru_sum": sum(right for _, right in common_shortfall),
            "native_token_delta_slru_minus_lru": sum(
                slru_requests[key]["native"] - lru_requests[key]["native"] for key in common_keys
            ),
        }
        sequences = {}
        run_paths = {entry["policy"]: suite / entry["path"] for entry in state["runs"]}
        for policy in ("lru", "slru"):
            measured, _ = measurement_events(read_events(run_paths[policy]), run_request_map(run_paths[policy]))
            sequence = [(event["pool"], event["victim"].get("end_page"))
                        for event in measured
                        if event["event_type"] == "victim_step"]
            encoded = json.dumps(sequence, separators=(",", ":")).encode()
            sequences[policy] = {"count": len(sequence), "sha256": hashlib.sha256(encoded).hexdigest()}
        paired["victim_sequence_fingerprint"] = sequences
        paired["same_event_end_page_sequence_equal"] = sequences["lru"] == sequences["slru"]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {"schema": "agentkv.mechanism_diagnosis.v1", "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "suite": str(suite.relative_to(ROOT)), "native_decisions_unchanged": True,
              "latency_ranking_allowed": False, "runs": reports, "paired": paired,
              "selection": load_json(suite / "selected_cases.json"),
              "conclusion_guard": "descriptive mechanism evidence only; no avoidable-loss or policy-net-benefit claim",
              "analyzer_sha256": None}
    save_json(output, result)
    result["analyzer_sha256"] = digest_file(Path(__file__).resolve())
    save_json(output, result)
    print(json.dumps({"output": str(output), "policies": list(by_policy), "event_files": [report["event_file"] for report in reports]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
