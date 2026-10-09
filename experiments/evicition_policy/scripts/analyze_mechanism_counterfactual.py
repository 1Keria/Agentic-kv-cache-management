#!/usr/bin/env python3
"""Conservative, equal-release local alternatives in native reclaim states.

Swap one originally legal internal SWA component for another of the exact same
size, preserving every Full free and every other native victim in that drive.
Follow the recorded events only until the FIRST affected match or component
mutation. This counts an earlier harmful replacement demand, not just a later
return to the preserved component. It is a local opportunity audit, not a replay
of a deployable policy or an additive full-workload improvement estimate.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import json
from pathlib import Path

from analyze_mechanism_diagnosis import (
    dist, event_path, load_json, measurement_events, read_events, run_request_map,
)
from prepare_data import ROOT, digest_file, save_json


class PageIndex:
    def __init__(self, events, page_size):
        self.page_size = page_size
        self.previous = {}
        self.depth = {}
        for event in events:
            if event["event_type"] == "page_definitions":
                for page, previous, depth in event["pages"]:
                    if page in self.previous and (self.previous[page], self.depth[page]) != (previous, depth):
                        raise ValueError("Conflicting page definition")
                    self.previous[page], self.depth[page] = previous, depth

    @lru_cache(maxsize=65536)
    def segment(self, end, count):
        pages = []
        for _ in range(count):
            if end not in self.previous:
                raise ValueError("Missing page definition (including pre-flush definitions)")
            pages.append(end)
            end = self.previous[end]
        return tuple(reversed(pages))

    def node_pages(self, node):
        tokens = int(node["logical_tokens"])
        if tokens % self.page_size:
            raise ValueError("Unaligned cache node")
        return self.segment(node["end_page"], tokens // self.page_size)


def joint_match(event, pages, window, preserved=(), removed=()):
    """Run the native node-boundary SWA validator over the observed Full path."""
    preserved, removed = set(preserved), set(removed)
    consecutive = float("inf")
    joint = depth = 0
    full = int(event["inspected_full_tokens"])
    for node in event["resident_path"]:
        count = min(int(node["logical_tokens"]), full - depth)
        if count <= 0:
            break
        segment = pages.node_pages(node)[:count // pages.page_size]
        available = [((int(node["swa_tokens"]) > 0 or page in preserved) and page not in removed)
                     for page in segment]
        # Radix splits can subdivide an affected node; native trees do not merge
        # it with unrelated content. Never invent a partial-component boundary.
        if any(available) and not all(available):
            raise ValueError("Partial component overlay requires an unobserved split")
        depth += count
        if available and all(available):
            consecutive += count
            if consecutive >= window:
                joint = depth
        else:
            consecutive = 0
    if depth != full:
        raise ValueError("Observed Full path length mismatch")
    return joint


def drive_index(events):
    drives = {}
    for offset, event in enumerate(events):
        kind = event["event_type"]
        if kind == "drive_begin":
            drives[(event["reclaim_id"], event["pool"])] = {"begin": event, "steps": [], "frees": []}
        elif kind == "victim_step":
            drives[(event["reclaim_id"], event["pool"])]["steps"].append(event)
        elif kind == "component_free":
            drives[(event["reclaim_id"], event["driver"])]["frees"].append(event)
        elif kind == "drive_end":
            drives[(event["reclaim_id"], event["pool"])].update(end=event, end_offset=offset)
    return drives


def legal_swaps(drive, victim, pages):
    """Initial candidates only; no newly exposed ancestors or size splitting."""
    if drive["begin"]["pool"] != "swa" or victim["pool"] != "swa":
        return []
    node = victim["victim"]
    initial = {candidate["end_page"]: candidate for candidate in drive["begin"]["candidates"]}
    original = initial.get(node["end_page"])
    if (not original or node["full_leaf"] or original["full_leaf"]
            or node["swa_lock_ref"] or original["swa_lock_ref"]
            or victim["released"]["full"] != 0
            or victim["released"]["swa"] != original["swa_tokens"]
            or node["logical_tokens"] != original["logical_tokens"]):
        return []
    preserved = set(pages.node_pages(original))
    freed = set()
    for free in drive["frees"]:
        freed.update(pages.node_pages(free["node"]))
    result = []
    for candidate in drive["begin"]["candidates"]:
        if (candidate["full_leaf"] or candidate["swa_lock_ref"]
                or candidate["full_tokens"] <= 0
                or candidate["swa_tokens"] != original["swa_tokens"]
                or candidate["logical_tokens"] != original["logical_tokens"]):
            continue
        replaced = set(pages.node_pages(candidate))
        if replaced & (freed | preserved):
            continue
        result.append({"preserved": original, "replacement": candidate,
                       "swa_release_unchanged_tokens": original["swa_tokens"],
                       "full_release_delta_tokens": 0,
                       "target_component_locks_zero": True,
                       "both_initial_internal_candidates": True})
    return result


def first_effect(events, drive, swap, pages, window, request_rows, *, rebase_drives=None):
    """Stop before native/alternative execution can require different insertion.

    Until this boundary the allocation difference is exactly +N/-N SWA pages;
    Full residency is unchanged. An overlapping later free invalidates the
    fixed victim continuation; rematerialization/insert stops the comparison
    rather than retaining the preserved pages at somebody else's expense.
    """
    preserve = set(pages.node_pages(swap["preserved"]))
    remove = set(pages.node_pages(swap["replacement"]))
    affected = preserve | remove
    start = drive["end"]
    matches = 0
    rebases = []
    pending = None
    for event in events[drive["end_offset"] + 1:]:
        kind = event["event_type"]
        reason = None
        if rebase_drives is not None and kind == "drive_begin" and event["pool"] == "swa":
            later = rebase_drives[(event["reclaim_id"], "swa")]
            pending = None
            for free in later["frees"]:
                if free["pool"] != "swa" or set(pages.node_pages(free["node"])) != remove:
                    continue
                victim = next((step for step in later["steps"] if step["step"] == free["step"]), None)
                options = legal_swaps(later, victim, pages) if victim else []
                options = [option for option in options if not preserve & set(pages.node_pages(option["replacement"]))]
                if options:
                    pending = (free["event_seq"], options[0]["replacement"])
                break
        if kind == "component_free":
            freed_pages = set(pages.node_pages(event["node"]))
            if pending and pending[0] == event["event_seq"] and not preserve & freed_pages:
                # The original replacement is already absent in the alternative.
                # Its native SWA free therefore releases zero. Remove another
                # initial unlocked internal component of the SAME size in this
                # drive, restoring identical release and occupancy at its end.
                remove = set(pages.node_pages(pending[1]))
                affected = preserve | remove
                rebases.append({"native_free_event_seq": event["event_seq"],
                                "replacement_end_page": pending[1]["end_page"],
                                "exact_additional_swa_release_tokens": len(remove) * pages.page_size})
                pending = None
            elif affected & freed_pages:
                reason = "preserved_component_later_free" if preserve & freed_pages else "replacement_later_free"
        elif kind == "insert":
            for node in event["nodes"]:
                segment = set(pages.node_pages(node))
                if int(node["swa_tokens"]) <= 0:
                    continue
                if preserve & segment:
                    reason = "preserved_component_materialized"
                    break
                # An insert snapshot also traverses old ancestors. The native
                # SWA overlap handler never restores a tombstone entirely
                # outside swa_evicted_seqlen; an unchanged ancestor snapshot
                # is therefore not an insertion into our removed component.
                window_start = int(event.get("swa_evicted_seqlen", 0))
                if any(pages.depth[page] * pages.page_size > window_start for page in remove & segment):
                    reason = "replacement_in_window_insert"
                    break
        elif kind == "flush":
            reason = "flush"
        if reason:
            return {"status": "expired_before_changed_match", "reason": reason,
                    "stop_event_seq": event["event_seq"], "unaffected_matches": matches,
                    "elapsed_seconds": (event["time_unix_ns"] - start["time_unix_ns"]) / 1e9,
                    "net_first_effect_tokens": 0, "rebase_count": len(rebases), "rebases": rebases}
        if kind != "match":
            continue
        matches += 1
        baseline = joint_match(event, pages, window)
        if baseline != event["native_matched_tokens"]:
            raise ValueError("Native match reconstruction disagrees with recorded result")
        hypothetical = joint_match(event, pages, window, preserve, remove)
        if hypothetical == baseline:
            continue
        rescued = max(0, hypothetical - baseline)
        sacrificed = max(0, baseline - hypothetical)
        row = request_rows.get(event["request_id"], {})
        return {"status": "first_changed_match", "first_changed_event_seq": event["event_seq"],
                "request_id": event["request_id"], "session_id": row.get("session_id"),
                "turn_index": row.get("turn_index"), "formal_request": bool(row),
                "native_matched_tokens": baseline, "hypothetical_matched_tokens": hypothetical,
                "preservation_gain_tokens": rescued, "replacement_loss_tokens": sacrificed,
                "net_first_effect_tokens": rescued - sacrificed,
                "unaffected_matches": matches - 1,
                "rebase_count": len(rebases), "rebases": rebases,
                "elapsed_seconds": (event["time_unix_ns"] - start["time_unix_ns"]) / 1e9}
    return {"status": "trace_ended_before_changed_match", "unaffected_matches": matches,
            "net_first_effect_tokens": 0, "rebase_count": len(rebases), "rebases": rebases}


def compact_swap(swap):
    keep = ("node_id", "end_page", "path_tokens", "logical_tokens", "full_lock_ref", "swa_lock_ref", "policy_score")
    return {**{k: v for k, v in swap.items() if k not in ("preserved", "replacement")},
            **{which: {k: swap[which].get(k) for k in keep} for which in ("preserved", "replacement")}}


def effect_counts(rows):
    effects = [row["effect"] for row in rows]
    return {"plans": len(rows), "status_counts": dict(Counter(effect["status"] for effect in effects)),
            "positive_first_effect": sum(effect["net_first_effect_tokens"] > 0 for effect in effects),
            "negative_first_effect": sum(effect["net_first_effect_tokens"] < 0 for effect in effects),
            "unique_positive_first_effect_requests": len({effect["request_id"] for effect in effects
                                                           if effect["net_first_effect_tokens"] > 0}),
            "unique_negative_first_effect_requests": len({effect["request_id"] for effect in effects
                                                           if effect["net_first_effect_tokens"] < 0}),
            "changed_native_terminal_matches": sum(effect.get("native_match_was_request_terminal") is True for effect in effects),
            "zero_or_expired": sum(effect["net_first_effect_tokens"] == 0 for effect in effects),
            "positive_tokens_distribution": dist(effect["net_first_effect_tokens"] for effect in effects
                                                  if effect["net_first_effect_tokens"] > 0),
            "negative_loss_tokens_distribution": dist(-effect["net_first_effect_tokens"] for effect in effects
                                                       if effect["net_first_effect_tokens"] < 0),
            "summing_local_alternatives_as_policy_gain_allowed": False}


def analyze_run(run, policy, cases, window, model_config_sha256):
    all_events = read_events(run)
    page_size = all_events[0]["page_size"]
    pages = PageIndex(all_events, page_size)
    requests = run_request_map(run)
    events, scope = measurement_events(all_events, requests)
    drives = drive_index(events)
    terminal = {event["request_id"]: event for event in events
                if event["event_type"] == "match" and event["request_id"] in requests}
    audit = {"checked_formal_match_events": 0, "native_validator_disagreements": 0}
    for event in events:
        if event["event_type"] == "match" and event["request_id"] in requests:
            audit["checked_formal_match_events"] += 1
            if joint_match(event, pages, window) != event["native_matched_tokens"]:
                audit["native_validator_disagreements"] += 1
    if audit["native_validator_disagreements"]:
        raise ValueError("Cannot evaluate alternatives with incorrect native validator")

    def evaluate(drive, swap, continued=False):
        effect = first_effect(events, drive, swap, pages, window, requests,
                              rebase_drives=drives if continued else None)
        if effect["status"] == "first_changed_match":
            native_terminal = terminal.get(effect["request_id"])
            effect["native_match_was_request_terminal"] = bool(native_terminal and
                                                              native_terminal["event_seq"] == effect["first_changed_event_seq"])
        return effect

    systematic, dispositions = [], Counter()
    for drive in drives.values():
        if drive["begin"]["pool"] != "swa" or not drive["begin"].get("active"):
            continue
        dispositions["active_swa_drives"] += 1
        chosen, choices = None, []
        # Selection uses only the recorded reclaim state, never future demand:
        # preserve the last native eligible step; replace the oldest unselected
        # equal-size internal candidate from the original LRU list.
        for victim in reversed(drive["steps"]):
            options = legal_swaps(drive, victim, pages)
            if options:
                chosen, choices = victim, options
                break
        if chosen is None:
            dispositions["no_legal_exact_size_swap"] += 1
            continue
        swap = choices[0]
        effect = evaluate(drive, swap)
        continued = evaluate(drive, swap, True)
        systematic.append({"reclaim_id": drive["begin"]["reclaim_id"],
                           "drive_begin_event_seq": drive["begin"]["event_seq"],
                           "drive_end_event_seq": drive["end"]["event_seq"],
                           "native_step": chosen["step"], "equal_size_choices": len(choices),
                           "swap": compact_swap(swap), "effect": effect, "continued_equal_budget_effect": continued})

    by_seq = {event["event_seq"]: event for event in events}
    selected = []
    for case in cases:
        request_id = next(rid for rid, row in requests.items()
                          if row["session_id"] == case["session_id"] and int(row["turn_index"]) == case["turn_index"])
        match = terminal[request_id]
        eligible_holes = [hole for hole in match["swa_holes"]
                          if hole["path_tokens"] <= min(match["inspected_full_tokens"], match["historical_joint_tokens"])
                          and hole.get("last_free") and hole["last_free"]["driver"] == "swa"]
        row = {**case, "target_match_event_seq": match["event_seq"],
               "target_native_tokens": match["native_matched_tokens"],
               "target_resident_full_tokens": match["inspected_full_tokens"],
               "selection_uses_target_after_the_fact": True}
        if not eligible_holes:
            selected.append({**row, "status": "no_observed_swa_hole"})
            continue
        hole = eligible_holes[-1]
        free = by_seq[hole["last_free"]["event_seq"]]
        drive = drives[(free["reclaim_id"], free["driver"])]
        victim = next((victim for victim in drive["steps"] if victim["step"] == free["step"]), None)
        options = legal_swaps(drive, victim, pages) if victim else []
        row.update(preserved_path_tokens=hole["path_tokens"], causal_free_event_seq=free["event_seq"],
                   reclaim_id=free["reclaim_id"], legal_equal_size_choices=len(options))
        option_rows = [{"swap": compact_swap(swap),
                        "single_swap_effect": evaluate(drive, swap),
                        "effect": evaluate(drive, swap, True)} for swap in options]
        row["option_summary"] = effect_counts(option_rows)
        row["oldest_equal_size_option"] = option_rows[0] if option_rows else None
        # Preserve negative/expired options as well as positive ones. Hindsight
        # best is evidence of a local opportunity only, never an online rule.
        row["hindsight_best_option"] = max(option_rows, key=lambda option: option["effect"]["net_first_effect_tokens"]) if option_rows else None
        row["status"] = "evaluated" if options else "no_legal_exact_size_swap"
        selected.append(row)
    return {"policy": policy, "event_file": str(event_path(run).relative_to(ROOT)),
            "event_file_sha256": digest_file(event_path(run)), "measurement_scope": scope,
            "page_size": page_size, "sliding_window_size": window,
            "model_config_sha256": model_config_sha256, "native_validator_audit": audit,
            "systematic_selection": "last eligible native internal SWA victim / oldest unselected equal-size initial internal candidate",
            "systematic_dispositions": dict(dispositions),
            "systematic_summary": effect_counts(systematic), "systematic_rows": systematic,
            "systematic_continued_equal_budget_summary": effect_counts(
                [{"effect": row["continued_equal_budget_effect"]} for row in systematic]),
            "preregistered_case_alternatives": selected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.suite = args.suite.resolve()
    state = load_json(args.suite / "suite.json")
    if state["status"] != "completed":
        raise ValueError("Diagnostic suite incomplete")
    config = load_json(args.model_config)
    window = int(config.get("sliding_window", config.get("sliding_window_size", 0)))
    if window <= 0:
        raise ValueError("Missing model sliding window size")
    cases = load_json(args.suite / "selected_cases.json")["cases"]
    reports = []
    for info in state["runs"]:
        reports.append(analyze_run(args.suite / info["path"], info["policy"], cases, window,
                                   digest_file(args.model_config)))
    result = {"schema": "agentkv.mechanism_local_counterfactual.v1", "runs": reports,
              "analyzer_sha256": digest_file(Path(__file__)),
              "scope": "initial legal equal-size SWA internal-component swap; unchanged Full release; first affected match only",
              "finite_memory_difference": "exactly +N/-N SWA tokens until first affected match or mutation; no added cache budget",
              "continued_exchange_rule": "when a later native SWA-only internal free targets the already absent replacement, free the oldest unselected legal equal-size internal component in that same drive; no future demand used",
              "limitations": [
                  "Native later victims are frozen, not rescored; stop before a victim becomes invalid or component state changes.",
                  "First changed match includes replacement loss if it arrives first; later consequences are outside the local window.",
                  "Independent overlapping alternatives cannot be summed into aggregate policy savings.",
                  "Selected cases use hindsight to locate causal holes; systematic victim/replacement selection uses no future demand.",
                  "This diagnoses Full/SWA reuse dependency, not a proposed separate attention-specific policy.",
                  "Time and scheduler feedback require a later implementation experiment.",
              ]}
    save_json(args.output, result)
    print(json.dumps({"output": str(args.output), "summaries": {run["policy"]: run["systematic_continued_equal_budget_summary"] for run in reports}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
