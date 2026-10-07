import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "frontier_statistics", ROOT / "scripts/analyze_agent_frontier_statistics.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def input_fixture(sequences, session="test"):
    return {
        (session, turn): {
            "session_id": session, "turn_index": turn, "task_id": "fixture",
            "pages": MODULE.prefix_pages(tokens), "prompt_tokens": len(tokens),
            "is_last_observed_session_request": turn == len(sequences) - 1,
            "is_strict_append_from_previous": None if turn == 0 else MODULE.lcp(sequences[turn - 1], tokens) == len(sequences[turn - 1]),
        }
        for turn, tokens in enumerate(sequences)
    }


class AgentFrontierStatisticsTest(unittest.TestCase):
    def test_page_identity_includes_ancestors_and_allows_shared_prefixes(self):
        first = MODULE.prefix_pages([1, 2, 3, 4], 2)
        other = MODULE.prefix_pages([9, 8, 3, 4], 2)
        self.assertNotEqual(first[-1], other[-1])
        self.assertEqual(first, MODULE.prefix_pages([1, 2, 3, 4], 2))
        inputs = {**input_fixture([[1] * 256], "a"), **input_fixture([[1] * 256], "b")}
        summary, *_ = MODULE.input_demand_evidence(inputs)
        self.assertEqual(summary["unique_complete_input_content_pages"], 1)
        self.assertEqual(summary["pages_referenced_by_multiple_sessions"], 1)
        self.assertEqual(summary["pages_with_at_least_two_observed_request_demands"], 1)

    def test_append_chain_birth_cohort_and_terminal_unknown(self):
        a, b, c = [1] * 256, [2] * 256, [3] * 256
        inputs = input_fixture([a, a + b, a + b + c])
        summary, histogram, sessions, cohorts, _, _ = MODULE.input_demand_evidence(inputs)
        self.assertEqual(summary["unique_complete_input_content_pages"], 3)
        self.assertEqual(summary["page_request_references"], 6)
        self.assertEqual(summary["pages_with_at_least_two_observed_request_demands"], 2)
        self.assertEqual(summary["singleton_pages_first_seen_in_last_observed_session_request"], 1)
        self.assertEqual(summary["next_request_cohort"]["new_to_session_complete_pages"], 2)
        self.assertEqual(summary["next_request_cohort"]["pages_demanded_in_next_request"], 2)
        self.assertFalse(cohorts[-1]["has_observed_next_session_request"])
        tree = MODULE.InputHistoryTree()
        for row in inputs.values():
            state = tree.add_request(row["pages"])
        self.assertEqual(state["history_tree_leaf_pages"], 1)
        self.assertEqual(state["history_tree_leaf_pages_one_observed_demand"], 1)
        self.assertEqual(sorted(tree.demands.values()), [1, 2, 3])

    def test_rewrite_then_return_is_not_permanent_one_shot(self):
        a, b, c = [1] * 256, [2] * 256, [3] * 256
        inputs = input_fixture([a + b, a + c, a + b])
        summary, _, _, cohorts, _, _ = MODULE.input_demand_evidence(inputs)
        self.assertEqual(cohorts[0]["new_pages_demanded_by_next_session_request"], 1)
        self.assertEqual(cohorts[0]["new_pages_demanded_by_any_later_observed_session_request"], 2)
        self.assertEqual(summary["singleton_pages_despite_later_observed_session_requests"], 1)
        self.assertIn("unknown future", summary["censoring"])
        tree = MODULE.InputHistoryTree()
        for row in inputs.values():
            state = tree.add_request(row["pages"])
        self.assertEqual(state["history_tree_leaf_pages"], 2)
        self.assertEqual(state["history_tree_leaf_pages_repeated_demand"], 1)

    def test_subpage_growth_can_repeat_same_logical_leaf(self):
        tree = MODULE.InputHistoryTree()
        tree.add_request(MODULE.prefix_pages([1, 2, 3, 4, 5], 4))
        state = tree.add_request(MODULE.prefix_pages([1, 2, 3, 4, 5, 6], 4))
        self.assertEqual(state["history_tree_leaf_pages_repeated_demand"], 1)

    def test_generation_mixed_page_counts_only_output_overlap(self):
        pages = MODULE.generated_page_overlaps([1, 2, 3], [4, 5, 6], 4)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0][1], 1)
        self.assertEqual(pages[0][0], MODULE.prefix_pages([1, 2, 3, 4], 4)[0])

    def test_generation_aligned_and_uncovered_tail(self):
        pages = MODULE.generated_page_overlaps([1, 2, 3, 4], [5, 6, 7, 8, 9], 4)
        self.assertEqual(len(pages), 1)
        self.assertEqual(sum(overlap for _, overlap in pages), 4)
        self.assertEqual(MODULE.generated_page_overlaps([1], [2], 4), [])
        self.assertEqual(MODULE.format_percent(0, 0), "未知")

    def test_generation_requires_matching_whole_prefix(self):
        good = MODULE.generated_page_overlaps([1, 2, 3], [4], 4)[0][0]
        wrong = MODULE.prefix_pages([8, 2, 3, 4], 4)[0]
        self.assertNotEqual(good, wrong)
        self.assertEqual(MODULE.generation_next_overlap([1, 2], [3, 4], [1, 9, 3, 4]), 0)
        self.assertEqual(MODULE.generation_next_overlap([1, 2], [3, 4], [1, 2, 3, 8]), 1)

    def test_cross_session_future_requires_after_completion(self):
        page = MODULE.prefix_pages([1, 2, 3, 4], 4)[0]
        outputs = {p: [{
            "policy": p, "session_id": "source", "turn_index": 0, "task_id": "test",
            "output_tokens": 1, "completed_seconds": 10.0,
            "has_observed_next_session_request": False,
            "next_input_raw_output_prefix_tokens": None, "pages": [(page, 1)],
        }] for p in MODULE.POLICIES}
        global_visits = {page: [("other", 0)]}
        local_visits = {"source": {}}
        records = {p: {("other", 0): {"submitted_seconds": 9.0}} for p in MODULE.POLICIES}
        summaries, _ = MODULE.output_demand_evidence(outputs, {}, global_visits, local_visits, records)
        for p in MODULE.POLICIES:
            self.assertEqual(summaries[p]["all_observed_requests"]["page_occurrences_matched_in_later_any_session_input_after_completion"], 0)
            self.assertEqual(summaries[p]["requests_with_next_session_input"]["requests"], 0)
            self.assertEqual(summaries[p]["last_observed_session_requests_future_unknown"]["requests"], 1)
            records[p][("other", 0)]["submitted_seconds"] = 11.0
        summaries, _ = MODULE.output_demand_evidence(outputs, {}, global_visits, local_visits, records)
        self.assertEqual(summaries["lru"]["all_observed_requests"]["output_tokens_in_pages_matched_in_later_any_session_input_after_completion"], 1)

    def test_loader_rejects_measured_output_hash_mismatch(self):
        ids = [1] * 256
        row = {"session_id": "test", "turn_index": 0, "task_id": "fixture", "input_ids": ids,
               "input_ids_sha256": MODULE.canonical_digest(ids)}
        records = {p: {("test", 0): {
            "input_ids_sha256": row["input_ids_sha256"], "prompt_tokens": len(ids),
            "output_ids": [2], "actual_output_tokens": 1,
            "output_ids_sha256": "incorrect", "completed_seconds": 1.0,
        }} for p in MODULE.POLICIES}
        workload = {"sessions": [{"path": "data/test.jsonl.gz"}], "requests": 1}
        with patch.object(MODULE, "read_rows", return_value=[row]):
            with self.assertRaisesRegex(ValueError, "Output hash"):
                MODULE.load_content(workload, records)


if __name__ == "__main__":
    unittest.main()
