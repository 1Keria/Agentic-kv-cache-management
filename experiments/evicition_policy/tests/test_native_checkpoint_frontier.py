"""Checkpoint discovery cannot alter compressed native radix boundaries."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_checkpoint_frontier as runner
from native_checkpoint_frontier import NativeCheckpointFrontier


class NativeCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.original = runner.RetainedFrontier
        runner.RetainedFrontier = NativeCheckpointFrontier

    def tearDown(self):
        runner.RetainedFrontier = self.original

    def test_exact_endpoint_keeps_actual_window_cost_and_never_splits(self):
        engine = runner.ObservedInputReplay(64, 32, page_size=2, window=2, chunk=8,
            policy="frontier", max_prompt=64, frontier_settings={
                "enabled": True, "max_units": 8, "full_budget_tokens": 32,
                "swa_budget_tokens": 8, "admission_policy": "retain_existing",
                "partial_checkpoints": True, "resident_downgrade": True})
        engine.request({"input_ids": list(range(25))}, 0)
        frontier, cache = engine.frontier, engine.cache
        key = engine.native.Key(list(range(24)), None).page_aligned(2)
        original_split = cache._split_node
        cache._split_node = lambda *args, **kwargs: self.fail("Boundary discovery called native split")
        try:
            anchor = frontier.input_anchor(key, 24)
            self.assertIsNotNone(anchor)
            self.assertIsNotNone(frontier.dependencies(anchor))
            # Search existing compressed nodes for a target strictly inside one.
            path = list(reversed(frontier.path(anchor)))
            depth = 0
            interior = None
            for node in path:
                if len(node.key) > 2:
                    interior = depth + 2
                    break
                depth += len(node.key)
            self.assertIsNotNone(interior)
            self.assertIsNone(frontier.input_anchor(key, interior))
        finally:
            cache._split_node = original_split
        self.assertEqual(frontier.counts.get("window_tail_splits", 0), 0)
        self.assertEqual(frontier.counts.get("input_boundary_splits", 0), 0)
        engine.assert_integrity()

    def test_native_partial_reuse_survives_real_shrink(self):
        engine = runner.ObservedInputReplay(64, 32, page_size=2, window=2, chunk=4,
            policy="frontier", max_prompt=64, frontier_settings={
                "enabled": True, "max_units": 8, "full_budget_tokens": 32,
                "swa_budget_tokens": 8, "admission_policy": "retain_existing",
                "partial_checkpoints": True, "resident_downgrade": True})
        row = {"input_ids": list(range(25))}
        engine.request(row, 0)
        self.assertTrue(engine.update_budget(32, 16, 0)["complete"])
        result = engine.request(row, 1)
        self.assertGreater(result["matched_tokens"], 0)
        self.assertLessEqual(result["after"]["resident"]["full"], 32)
        self.assertEqual(engine.frontier.counts.get("window_tail_splits", 0), 0)
        self.assertEqual(engine.frontier.counts.get("input_boundary_splits", 0), 0)
        engine.assert_integrity()


if __name__ == "__main__":
    unittest.main()
