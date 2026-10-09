"""Legal resident checkpoint, native lock and capacity-downgrade regression tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from test_bounded_frontier import Cache, CT
from checkpoint_frontier import CheckpointFrontier
from run_checkpoint_frontier import ObservedInputReplay


def fixture(**settings):
    cache = Cache()
    frontier = CheckpointFrontier(cache, {"enabled": True, "max_units": 8,
        "full_budget_tokens": 64, "swa_budget_tokens": 16,
        "admission_policy": "retain_existing", "partial_checkpoints": True,
        "resident_downgrade": True, **settings}, component_types=cache.tree_components)
    cache.frontier = frontier
    events = []
    frontier.event_sink = events.append
    return cache, frontier, events


class CheckpointTests(unittest.TestCase):
    def test_budget_downgrade_requires_real_swa_and_preserves_retention_order(self):
        cache, f, events = fixture()
        a = cache.add([1, 2])
        b = cache.add([3, 4], a)
        c = cache.add([5, 6], b)
        other = cache.add([7, 8])
        f.register(c)
        f.register(other)
        f.full_budget = 6
        f.trim_budget()
        self.assertEqual(list(f.units), [b.id, other.id])
        self.assertEqual(f.full_tokens, 6)
        self.assertEqual(f.counts['resident_downgrades_budget'], 1)
        self.assertTrue(any(e.get('downgrade_reason') == 'budget' for e in events))
        f.full_budget = 4
        b.component_data[CT.SWA].value = None
        a.component_data[CT.SWA].value = None
        f.trim_budget()
        self.assertEqual(list(f.units), [other.id])

    def test_pressure_downgrade_unlocks_deep_suffix_without_freeing_ancestor(self):
        cache, f, _ = fixture()
        head = cache.add([1, 2])
        tail = cache.add([3, 4], head)
        f.register(tail)
        tracker = {CT.FULL: 0, CT.SWA: 0}
        f.drive_full(2, tracker)
        self.assertEqual(tracker, {CT.FULL: 2, CT.SWA: 2})
        self.assertEqual(list(f.units), [head.id])
        self.assertEqual(f.counts['resident_downgrades_pressure_full'], 1)
        self.assertIsNotNone(head.component_data[CT.FULL].value)

    def test_missing_swa_prevents_invented_checkpoint(self):
        cache, f, _ = fixture()
        head = cache.add([1, 2])
        tail = cache.add([3, 4], head)
        head.component_data[CT.SWA].value = None
        f.register(tail)
        f.full_budget = 2
        f.trim_budget()
        self.assertFalse(f.units)
        self.assertEqual(f.counts['resident_downgrades_budget'], 0)

    def test_shared_ancestor_downgrade_never_overwrites_live_unit(self):
        cache, f, events = fixture()
        head = cache.add([1, 2])
        left, right = cache.add([3, 4], head), cache.add([5, 6], head)
        f.register(left)
        f.register(right)
        dependency = f.dependencies(head)
        f.move_to_ancestor(left.id, head, dependency, 'test')
        head_unit = f.units[head.id]['tick']
        self.assertFalse(list(f.alternatives(f.units[right.id])))
        self.assertEqual(f.units[head.id]['tick'], head_unit)
        self.assertEqual(set(f.units), {head.id, right.id})

    def test_downgrade_cannot_move_to_expensive_swa_component(self):
        cache, f, _ = fixture(swa_budget_tokens=2)
        head = cache.add(list(range(6)))
        tail = cache.add([6, 7], head)
        f.register(tail)
        tracker = {CT.FULL: 0, CT.SWA: 0}
        f.drive_full(2, tracker)
        self.assertEqual(f.counts['resident_downgrades_pressure_full'], 0)
        self.assertGreaterEqual(tracker[CT.FULL], 2)

    def test_native_partial_checkpoints_survive_shrink_and_use_real_slots(self):
        engine = ObservedInputReplay(64, 32, page_size=2, window=2, chunk=4,
            policy='frontier', max_prompt=64, frontier_settings={
                'enabled': True, 'max_units': 8, 'full_budget_tokens': 16,
                'swa_budget_tokens': 8, 'admission_policy': 'retain_existing',
                'partial_checkpoints': True, 'resident_downgrade': True})
        root = engine.cache.root_node
        events = []
        engine.frontier.event_sink = events.append
        first = engine.request({'input_ids': list(range(25))}, 0)
        self.assertEqual(first['matched_tokens'], 0)
        self.assertGreater(engine.frontier.counts['partial_checkpoint_stages'], 0)
        self.assertTrue(engine.frontier.units)
        for unit in engine.frontier.units.values():
            self.assertLessEqual(sum(len(n.key) for n in unit['dependencies'][0]), 16)
        receipt = engine.update_budget(32, 16, 0)
        self.assertTrue(receipt['complete'])
        second = engine.request({'input_ids': list(range(27))}, 1)
        self.assertGreater(second['matched_tokens'], 0)
        self.assertTrue(second['budget_checks_complete'])
        self.assertIs(engine.cache.root_node, root)
        engine.assert_integrity()


if __name__ == '__main__':
    unittest.main()
