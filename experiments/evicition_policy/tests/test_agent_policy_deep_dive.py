import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT = SCRIPT_DIR / "analyze_agent_policy_deep_dive.py"
SPEC = importlib.util.spec_from_file_location("analyze_agent_policy_deep_dive", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AgentPolicyDeepDiveTest(unittest.TestCase):
    def test_availability_state_boundaries(self):
        self.assertEqual(MODULE.availability_state(4096, 4096), "small_reference")
        self.assertEqual(MODULE.availability_state(10000, 1000), "low")
        self.assertEqual(MODULE.availability_state(10000, 9000), "high")
        self.assertEqual(MODULE.availability_state(10000, 5000), "mid")

    def test_interval_sum_excludes_boundaries(self):
        times = [1.0, 2.0, 3.0, 4.0]
        prefix = [0, 2, 5, 10, 17]
        self.assertEqual(MODULE.interval_sum(times, prefix, 1.0, 4.0), 8)

    def test_case_tags_are_exact(self):
        row = {"case_tags": "slru_policy_cliff_win;slru_large_win"}
        self.assertIn("slru_policy_cliff_win", MODULE.exact_tags(row))
        self.assertNotIn("lru_policy_cliff_win", MODULE.exact_tags(row))

    def test_pearson_correlation(self):
        self.assertEqual(MODULE.pearson_correlation([(1.0, -1.0), (2.0, -2.0), (3.0, -3.0)]), -1.0)
        self.assertIsNone(MODULE.pearson_correlation([(1.0, 2.0)]))

    def test_cliff_context_counts_inflight_competition(self):
        row = {
            "submission_rank_delta_slru_minus_lru": "1",
            "submitted_seconds_delta_slru_minus_lru": "-2.5",
            "intervening_submitted_request_count_lru": "0",
            "intervening_submitted_request_count_slru": "0",
            "active_other_requests_at_previous_completion_lru": "3",
            "active_other_requests_at_previous_completion_slru": "4",
            "effective_gap_seconds": "0.04",
            "previous_availability_state_lru": "high",
            "previous_availability_state_slru": "high",
        }
        stats = MODULE.cliff_context_stats([row])
        self.assertEqual(stats["submission_rank_absolute_delta_at_most_2"], 1)
        self.assertEqual(stats["zero_submissions_with_inflight_others_both_policies"], 1)
        self.assertEqual(stats["effective_gap_under_100ms"], 1)
        self.assertEqual(stats["previous_state_high_under_both_policies"], 1)


if __name__ == "__main__":
    unittest.main()
