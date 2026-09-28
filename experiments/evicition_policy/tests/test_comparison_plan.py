import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ComparisonPlanTest(unittest.TestCase):
    def setUp(self):
        self.policies = json.loads((ROOT / "configs/policies.json").read_text())
        self.status = json.loads((ROOT / "reports/preparation_status.json").read_text())
        self.matrix = self.status["formal_matrix"]

    def test_single_pass_order_matches_status(self):
        order = [policy for group in self.policies["formal_order_candidate_not_started"] for policy in group]
        self.assertEqual(order, ["lru", "lfu", "slru"])
        self.assertEqual(order, self.matrix["run_order"])
        self.assertEqual(self.policies["planned_runs"], len(order))
        self.assertEqual(self.matrix["runs"], len(order))
        self.assertEqual(self.policies["repeats_per_policy"], 1)
        self.assertEqual(self.matrix["repeats_per_policy"], 1)

    def test_exploratory_plan_does_not_auto_repeat(self):
        self.assertEqual(self.policies["comparison_stage"], "single_pass_exploratory")
        self.assertEqual(self.matrix["stage"], self.policies["comparison_stage"])
        self.assertFalse(self.policies["automatic_additional_repeats"])
        self.assertFalse(self.matrix["automatic_additional_repeats"])
        self.assertFalse(self.matrix["run_to_run_variability_estimable"])

    def test_one_hour_sample_keeps_complete_sessions_and_controls(self):
        self.assertEqual(self.status["formal_coverage_target"]["candidate_sessions"], 83)
        self.assertEqual(self.status["formal_coverage_target"]["selected_complete_sessions"], 20)
        self.assertEqual(self.status["formal_coverage_target"]["requests"], 1206)
        self.assertFalse(self.status["formal_coverage_target"]["requests_or_outputs_truncated"])
        self.assertTrue(self.matrix["same_complete_workload_for_each_policy"])
        self.assertTrue(self.matrix["restart_service_between_runs"])
        self.assertFalse(self.matrix["previous_calibration_counts_as_comparison"])


if __name__ == "__main__":
    unittest.main()
