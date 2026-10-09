"""Meaningful admission, pressure, dependency and native replay checks for v2."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from test_bounded_frontier import Cache, CT
from retained_frontier import RetainedFrontier
from run_retained_frontier import ObservedInputReplay


def fixture(**settings):
    cache = Cache()
    frontier = RetainedFrontier(cache, {"enabled": True, "max_units": 8,
                                      "full_budget_tokens": 8, "swa_budget_tokens": 4,
                                      "admission_policy": "retain_existing", **settings},
                                component_types=cache.tree_components)
    cache.frontier = frontier
    events = []
    frontier.event_sink = events.append
    return cache, frontier, events


class RetainedTests(unittest.TestCase):
    def test_rejecting_new_qualification_preserves_old_physical_data(self):
        cache, frontier, events = fixture(full_budget_tokens=4)
        a, b = cache.add([1, 2, 3, 4]), cache.add([5, 6, 7, 8])
        frontier.register(a)
        frontier.register(b)
        self.assertEqual(list(frontier.units), [a.id])
        self.assertIsNotNone(b.component_data[CT.FULL].value)
        self.assertEqual(events[-1]["reason"], "new_boundary_budget")
        tracker = {CT.FULL: 0, CT.SWA: 0}
        frontier.drive_full(4, tracker)
        self.assertEqual(cache.victims, [("atomic", b.id)])
        self.assertEqual(tracker, {CT.FULL: 4, CT.SWA: 4})

    def test_oversized_continuation_keeps_complete_shallow_boundary(self):
        cache, frontier, events = fixture(full_budget_tokens=4)
        first = cache.add([1, 2, 3, 4])
        tail = cache.add([5, 6], first)
        frontier.register(first)
        frontier.register(tail)
        self.assertEqual(list(frontier.units), [first.id])
        self.assertEqual(events[-1]["reason"], "continuation_budget")
        frontier.observe_match(tail, 6)
        self.assertEqual(frontier.counts["observed_unit_reuses"], 1)

    def test_feasible_continuation_migrates_and_shared_dependencies_deduplicate(self):
        cache, frontier, _ = fixture()
        common = cache.add([1, 2, 3, 4])
        left, right = cache.add([5, 6], common), cache.add([7, 8], common)
        frontier.register(common)
        frontier.register(left)
        frontier.register(right)
        self.assertEqual(set(frontier.units), {left.id, right.id})
        self.assertEqual((frontier.full_tokens, frontier.swa_tokens), (8, 4))

    def test_resize_and_pressure_still_revoke_for_progress(self):
        cache, frontier, events = fixture()
        a, b = cache.add([1, 2]), cache.add([3, 4])
        frontier.register(a)
        frontier.register(b)
        tracker = {CT.FULL: 0, CT.SWA: 0}
        frontier.drive_full(4, tracker)
        self.assertEqual(tracker, {CT.FULL: 4, CT.SWA: 4})
        self.assertFalse(frontier.units)
        self.assertTrue(any(e.get("reason") == "pressure_full" for e in events))
        c = cache.add([5, 6])
        frontier.register(c)
        frontier.full_budget = frontier.swa_budget = 0
        frontier.trim_budget()
        self.assertFalse(frontier.units)

    def test_disabled_logging_does_not_need_engine_components(self):
        frontier = RetainedFrontier(None, {"enabled": False})
        frontier.observe_match(None, 0)
        frontier.log_final()

    def test_native_reuse_log_excludes_self_prefill_matches(self):
        engine = ObservedInputReplay(64, 32, page_size=2, window=2, chunk=4,
                                    policy="frontier", max_prompt=64,
                                    frontier_settings={"enabled": True, "max_units": 8,
                                        "full_budget_tokens": 32, "swa_budget_tokens": 8,
                                        "admission_policy": "retain_existing"})
        events = []
        engine.frontier.event_sink = events.append
        engine.frontier.request_index = 0
        first = engine.request({"input_ids": list(range(17))}, 0)
        self.assertEqual(first["matched_tokens"], 0)
        self.assertFalse(any(e["event_type"] == "reuse" for e in events))
        engine.frontier.request_index = 1
        second = engine.request({"input_ids": list(range(19))}, 1)
        self.assertEqual(second["matched_tokens"], 16)
        self.assertEqual(sum(e["event_type"] == "reuse" for e in events), 1)
        engine.assert_integrity()


if __name__ == "__main__":
    unittest.main()
