"""Exercise changing budgets on the complete official CPU cache implementation."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from replay_resizable_native import HistoryPrefixIndex, NativeInputReplay, budget_for_profile


def row(tokens, turn=0):
    return {"input_ids": tokens, "session_id": "micro", "task_id": "micro",
            "turn_index": turn}


def replay(policy="frontier", full=64, swa=32):
    return NativeInputReplay(full, swa, page_size=2, window=2, chunk=4,
                             policy=policy, max_prompt=64,
                             frontier_settings={"enabled": True, "max_units": 8,
                                                "full_budget_tokens": 32,
                                                "swa_budget_tokens": 8})


class NativeReplayTests(unittest.TestCase):
    def test_history_is_exact_page_aligned_and_namespace_specific(self):
        history = HistoryPrefixIndex(2)
        history.insert([1, 2, 3, 4, 5], "a")
        self.assertEqual(history.match([1, 2, 3, 4, 5], "a"), 4)
        self.assertEqual(history.match([1, 2, 3, 7, 5], "a"), 2)
        self.assertEqual(history.match([1, 2, 3, 4], "b"), 0)

    def test_official_chunk_finish_reuses_real_prefix_and_frees_partial_page(self):
        for policy in ("lru", "frontier"):
            with self.subTest(policy=policy):
                engine = replay(policy)
                first = engine.request(row(list(range(17))), 0)
                second = engine.request(row(list(range(19))), 1)
                self.assertEqual(first["matched_tokens"], 0)
                self.assertEqual(second["matched_tokens"], 16)
                self.assertEqual(second["history_match_tokens"], 16)
                self.assertEqual(second["capacity_loss_tokens"], 0)
                self.assertEqual(second["after"]["resident"]["full"], 18)
                self.assertTrue(second["physical_accounting_ok"])
                if policy == "frontier":
                    self.assertEqual(engine.frontier.counts["input_boundary_splits"], 0)
                    self.assertEqual(engine.frontier.counts["window_tail_splits"], 0)
                engine.assert_integrity()

    def test_continuous_shrink_restore_never_resets_native_instance(self):
        for policy in ("lru", "frontier"):
            with self.subTest(policy=policy):
                engine = replay(policy)
                root = engine.cache.root_node
                for index in range(12):
                    if index in (0, 3, 6, 9):
                        full, swa, version = budget_for_profile("shrink_restore", index, 64, 32, 2, [3, 6, 9])
                        receipt = engine.update_budget(full, swa, version)
                        self.assertTrue(receipt["complete"])
                        self.assertTrue(receipt["accounting_ok"])
                    result = engine.request(row(list(range(index % 4 * 100, index % 4 * 100 + 11)), index), index)
                    self.assertTrue(result["budget_checks_complete"])
                    self.assertLessEqual(result["after"]["resident"]["full"], engine.controller.hard_budget.full)
                    self.assertLessEqual(result["after"]["resident"]["swa"], engine.controller.hard_budget.swa)
                    self.assertIs(engine.cache.root_node, root)
                self.assertGreater(engine.eviction_free["full"], 0)

    def test_swa_pressure_retains_full_but_joint_match_can_be_shallower(self):
        engine = replay("lru", full=128, swa=8)
        engine.request(row(list(range(17))), 0)
        engine.request(row(list(range(100, 117))), 1)
        result = engine.request(row(list(range(19))), 2)
        self.assertEqual(result["history_match_tokens"], 16)
        self.assertGreaterEqual(result["full_resident_match_tokens"], 14)
        self.assertGreater(result["full_resident_but_joint_unavailable_tokens"], 0)
        self.assertGreater(engine.eviction_free["swa"], 0)

    def test_zero_protection_budget_releases_real_pages_then_restores_no_units(self):
        engine = replay()
        engine.request(row(list(range(9))), 0)
        self.assertGreater(len(engine.frontier.units), 0)
        receipt = engine.update_budget(0, 0, 0)
        self.assertTrue(receipt["complete"])
        self.assertEqual(receipt["after"]["resident"], {"full": 0, "swa": 0})
        self.assertFalse(engine.frontier.units)
        engine.update_budget(64, 32, 1)
        self.assertFalse(engine.frontier.units)
        result = engine.request(row(list(range(9))), 1)
        self.assertEqual(result["matched_tokens"], 0)
        self.assertEqual(result["history_match_tokens"], 8)
        self.assertGreater(len(engine.frontier.units), 0)

    def test_native_lock_causes_explicit_debt_then_unlock_retry_completes(self):
        engine = replay()
        engine.request(row(list(range(13))), 0)
        match = engine.cache.match_prefix(engine.native.MatchParams(key=engine.native.Key(list(range(12)), None)))
        lock = engine.cache.inc_lock_ref(match.last_device_node)
        receipt = engine.update_budget(4, 2, 0)
        self.assertFalse(receipt["complete"])
        self.assertEqual(receipt["stop_reason"], "locked_or_active")
        self.assertEqual(receipt["after"]["resident"]["full"], 12)
        engine.cache.dec_lock_ref(match.last_device_node, lock.to_dec_params())
        retried = engine.controller.enforce()
        self.assertTrue(retried["complete"])
        self.assertTrue(retried["accounting_ok"])
        engine.assert_integrity()

    def test_rejects_single_input_larger_than_logical_admission(self):
        engine = replay()
        engine.update_budget(8, 4, 0)
        with self.assertRaisesRegex(RuntimeError, "cannot fit"):
            engine.request(row(list(range(17))), 0)


if __name__ == "__main__":
    unittest.main()
