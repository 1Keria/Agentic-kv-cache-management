import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_mechanism_diagnosis import chain_followups, match_decomposition, measurement_events
from analyze_mechanism_counterfactual import PageIndex, first_effect, joint_match, legal_swaps


def definitions():
    rows = []
    for prefix in ("a", "b", "c"):
        for depth in range(1, 41):
            rows.append([f"{prefix}{depth}", f"{prefix}{depth - 1}", depth])
    return [{"event_type": "page_definitions", "pages": rows}]


def node(end, count=256, swa=256, full_leaf=False, full_lock=0, swa_lock=0):
    return {"end_page": end, "logical_tokens": count, "swa_tokens": swa, "full_tokens": count,
            "full_leaf": full_leaf, "full_lock_ref": full_lock, "swa_lock_ref": swa_lock}


def request(prefix, length, native, tail_present):
    path = []
    if length > 256:
        path.append(node(f"{prefix}{length // 256 - 1}", length - 256, swa=0))
    path.append(node(f"{prefix}{length // 256}", swa=256 if tail_present else 0))
    return {"event_type": "match", "event_seq": 10, "time_unix_ns": 10_000_000_000,
            "request_id": prefix, "inspected_full_tokens": length, "resident_path": path,
            "native_matched_tokens": native}


class MechanismAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.pages = PageIndex(definitions(), 256)
        self.swap = {"preserved": node("a40"), "replacement": node("b3")}
        self.drive = {"end_offset": 0, "end": {"event_seq": 1, "time_unix_ns": 1_000_000_000}}

    def test_measurement_boundary_excludes_warmup_but_keeps_old_definitions(self):
        events = [{"event_type": "observer_start", "event_seq": 1},
                  {**definitions()[0], "event_seq": 2},
                  {"event_type": "flush", "event_seq": 3},
                  {"event_type": "match", "request_id": "warmup", "event_seq": 4},
                  {"event_type": "reclaim_begin", "event_seq": 5},
                  {"event_type": "flush", "event_seq": 6},
                  {"event_type": "match", "request_id": "formal", "event_seq": 7}]
        measured, scope = measurement_events(events, {"formal": {}})
        self.assertEqual([event["event_seq"] for event in measured], [7])
        self.assertEqual(scope["flush_event_seq"], 6)
        self.assertEqual(PageIndex(events, 256).segment("a40", 2), ("a39", "a40"))

    def test_pool_step_numbers_do_not_interleave_full_followup(self):
        steps = [{"pool": "full", "event_seq": 1, "step": 1, "victim": {"end_page": "child"},
                  "parent_exposed": True, "exposed_parent": {"end_page": "parent"}},
                 {"pool": "full", "event_seq": 2, "step": 2, "victim": {"end_page": "parent"}},
                 {"pool": "swa", "event_seq": 3, "step": 1, "victim": {"end_page": "other"}}]
        immediate, eventual = chain_followups({1: {"steps": steps}})
        self.assertEqual([event["event_seq"] for event in immediate], [2])
        self.assertEqual([event["event_seq"] for event in eventual], [2])

    def test_full_vs_joint_decomposition_is_not_full_eviction_label(self):
        event = {"historical_joint_tokens": 121088, "inspected_full_tokens": 120832, "native_matched_tokens": 0}
        self.assertEqual(match_decomposition(event), {"history_beyond_resident_full": 256,
                                                    "resident_full_without_joint_match": 120832})
        with self.assertRaises(ValueError):
            match_decomposition({**event, "native_matched_tokens": 122000})

    def test_small_window_rescues_long_full_prefix_with_one_page(self):
        match = request("a", 10240, 0, False)
        self.assertEqual(joint_match(match, self.pages, 128), 0)
        self.assertEqual(joint_match(match, self.pages, 128, {"a40"}), 10240)
        self.assertEqual(joint_match(match, self.pages, 512, {"a40"}), 0)

    def test_replacement_loss_arriving_first_is_negative(self):
        harmful = request("b", 768, 768, True)
        helpful = request("a", 10240, 0, False)
        effect = first_effect([{}, harmful, helpful], self.drive, self.swap, self.pages, 128, {"a": {}, "b": {}})
        self.assertEqual(effect["request_id"], "b")
        self.assertEqual(effect["replacement_loss_tokens"], 768)
        self.assertEqual(effect["net_first_effect_tokens"], -768)

    def test_positive_comparison_does_not_add_capacity(self):
        effect = first_effect([{}, request("a", 10240, 0, False)], self.drive, self.swap, self.pages, 128, {"a": {}})
        self.assertEqual(effect["net_first_effect_tokens"], 10240)
        self.assertEqual(len(self.pages.node_pages(self.swap["preserved"])),
                         len(self.pages.node_pages(self.swap["replacement"])))

    def test_comparison_expires_on_replacement_insert_or_later_free(self):
        for mutation in ({"event_type": "insert", "nodes": [node("b3")]},
                         {"event_type": "component_free", "pool": "full", "node": node("a40")}):
            with self.subTest(kind=mutation["event_type"]):
                mutation.update(event_seq=2, time_unix_ns=2_000_000_000)
                effect = first_effect([{}, mutation, request("a", 10240, 0, False)],
                                      self.drive, self.swap, self.pages, 128, {"a": {}})
                self.assertEqual(effect["status"], "expired_before_changed_match")
                self.assertEqual(effect["net_first_effect_tokens"], 0)

    def test_unchanged_old_ancestor_insert_snapshot_is_not_rematerialization(self):
        old = {"event_type": "insert", "nodes": [node("b3")], "swa_evicted_seqlen": 768,
               "event_seq": 2, "time_unix_ns": 2_000_000_000}
        query = request("a", 10240, 0, False)
        effect = first_effect([{}, old, query], self.drive, self.swap, self.pages, 128, {})
        self.assertEqual(effect["net_first_effect_tokens"], 10240)
        old["swa_evicted_seqlen"] = 512
        effect = first_effect([{}, old, query], self.drive, self.swap, self.pages, 128, {})
        self.assertEqual(effect["status"], "expired_before_changed_match")

    def test_target_component_lock_and_leaf_cascade_constrain_swap(self):
        original = node("a40")
        replacement = node("b3", full_lock=8)
        invalid_leaf = node("c40", full_leaf=True)
        invalid_locked = node("c39", swa_lock=1)
        victim = {"pool": "swa", "victim": original, "released": {"full": 0, "swa": 256}}
        drive = {"begin": {"pool": "swa", "candidates": [original, replacement, invalid_leaf, invalid_locked]},
                 "frees": [{"node": original}]}
        options = legal_swaps(drive, victim, self.pages)
        self.assertEqual([option["replacement"]["end_page"] for option in options], ["b3"])
        # Full lock is compatible with internal SWA-only eviction; an atomic
        # device leaf free is not this conservative alternative.
        bad = copy.deepcopy(victim)
        bad["released"]["full"] = 256
        self.assertEqual(legal_swaps(drive, bad, self.pages), [])

    def test_continued_exchange_pays_later_release_and_counts_new_replacement_loss(self):
        original = node("b3")
        replacement = node("c4")
        begin = {"event_type": "drive_begin", "event_seq": 2, "pool": "swa", "reclaim_id": 2,
                 "candidates": [original, replacement]}
        free = {"event_type": "component_free", "event_seq": 3, "pool": "swa", "driver": "swa",
                "node": original, "step": 1, "time_unix_ns": 3_000_000_000}
        victim = {"event_type": "victim_step", "event_seq": 4, "pool": "swa", "step": 1,
                  "victim": original, "released": {"full": 0, "swa": 256}}
        end = {"event_type": "drive_end", "event_seq": 5}
        later = {"begin": begin, "frees": [free], "steps": [victim], "end": end}
        events = [{}, begin, free, victim, end]
        for query, expected in ((request("a", 10240, 0, False), 10240),
                                (request("c", 1024, 1024, True), -1024)):
            with self.subTest(expected=expected):
                effect = first_effect(events + [query], self.drive, self.swap, self.pages, 128, {},
                                      rebase_drives={(2, "swa"): later})
                self.assertEqual(effect["rebase_count"], 1)
                self.assertEqual(effect["rebases"][0]["exact_additional_swa_release_tokens"], 256)
                self.assertEqual(effect["net_first_effect_tokens"], expected)


if __name__ == "__main__":
    unittest.main()
