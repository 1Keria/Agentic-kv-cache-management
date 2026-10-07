import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/analyze_agent_policy_insights.py"
SPEC = importlib.util.spec_from_file_location("analyze_agent_policy_insights", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AgentPolicyInsightsTest(unittest.TestCase):
    def test_lcp_shortfall_proxy_is_page_aligned_and_clamped(self):
        self.assertEqual(MODULE.previous_input_lcp_shortfall_proxy(None, 0), 0)
        self.assertEqual(MODULE.previous_input_lcp_shortfall_proxy(1000, 512), 256)
        self.assertEqual(MODULE.previous_input_lcp_shortfall_proxy(1000, 900), 0)

    def test_bins_have_stable_boundaries(self):
        self.assertEqual(MODULE.gap_bin(None), "first_request")
        self.assertEqual(MODULE.gap_bin(0.1), "[0.1,1)")
        self.assertEqual(MODULE.growth_bin(1024), "[1024,4096)")
        self.assertEqual(MODULE.turn_bin(100), "turn_100_plus")
        self.assertEqual(MODULE.lcp_bin(131072), "[128K,+inf)")
        self.assertEqual(MODULE.competition_count_bin(0), "0")
        self.assertEqual(MODULE.competition_prompt_bin(1_000_000), "[1M,4M)")

    def test_intervening_submission_proxy_uses_previous_completion(self):
        rows = {
            ("s1", 0): {"submitted_seconds": 0.0, "completed_seconds": 2.0, "prompt_tokens": 100},
            ("s2", 0): {"submitted_seconds": 2.5, "completed_seconds": 3.0, "prompt_tokens": 200},
            ("s2", 1): {"submitted_seconds": 3.5, "completed_seconds": 4.0, "prompt_tokens": 300},
            ("s1", 1): {"submitted_seconds": 5.0, "completed_seconds": 6.0, "prompt_tokens": 400},
        }
        proxies = MODULE.intervening_submission_proxies(rows)
        self.assertEqual(proxies[("s1", 0)], (None, None))
        self.assertEqual(proxies[("s1", 1)], (2, 500))

    def test_build_request_rows_rejects_input_drift(self):
        def record(policy, digest):
            return {
                "policy": policy,
                "session_id": "s",
                "task_id": "t",
                "turn_index": 0,
                "input_ids_sha256": digest,
                "prompt_tokens": 100,
                "cached_tokens": 0,
                "submitted_seconds": 0.0,
                "completed_seconds": 1.0,
                "ttft_seconds": 0.1,
                "latency_seconds": 1.0,
            }
        records = {
            "lru": {("s", 0): record("lru", "a")},
            "lfu": {("s", 0): record("lfu", "b")},
            "slru": {("s", 0): record("slru", "a")},
        }
        with self.assertRaisesRegex(ValueError, "Input hash drift"):
            MODULE.build_request_rows(records)

    def test_candidate_cases_rank_largest_policy_difference_first(self):
        rows = [
            {
                "cached_delta_slru_minus_lru": 256,
                "cached_delta_lfu_minus_lru": 0,
                "previous_input_lcp_shortfall_proxy_tokens_lru": 0,
                "prompt_tokens": 1000,
            },
            {
                "cached_delta_slru_minus_lru": -4096,
                "cached_delta_lfu_minus_lru": 512,
                "previous_input_lcp_shortfall_proxy_tokens_lru": 2048,
                "prompt_tokens": 8000,
            },
        ]
        ranked = MODULE.build_candidate_cases(rows)
        self.assertEqual(ranked[0]["cached_delta_slru_minus_lru"], -4096)
        self.assertEqual(ranked[0]["case_type"], "slru_loss")
        self.assertTrue(ranked[0]["requires_kv_event_trace_for_causal_attribution"])

    def test_case_tag_matching_does_not_use_substrings(self):
        row = {"case_tags": "slru_policy_cliff_win;slru_large_win"}
        self.assertTrue(MODULE.has_case_tag(row, "slru_policy_cliff_win"))
        self.assertFalse(MODULE.has_case_tag(row, "lru_policy_cliff_win"))


if __name__ == "__main__":
    unittest.main()
