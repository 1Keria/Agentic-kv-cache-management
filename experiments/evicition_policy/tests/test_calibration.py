import json
import pickle
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_admission import output_limit, validate_admission
from analyze_calibration import counter_deltas, metric_samples, observed_counter_windows, pool_observations, queue_histogram_deltas
from prepare_calibration import select_sessions
from estimate_formal_budget import estimate
from server_command import build_command


class CalibrationTest(unittest.TestCase):
    def test_page_alignment_is_part_of_output_limit(self):
        self.assertEqual(output_limit(513, 4096, 1024, 256), 0)
        self.assertEqual(output_limit(512, 4096, 1024, 256), 255)

    def test_context_keeps_native_two_token_margin(self):
        self.assertEqual(output_limit(100, 108, 4096, 256), 6)

    def test_input_guard_is_checked_independently(self):
        self.assertEqual(output_limit(103, 108, 4096, 256), 0)

    def test_requested_output_at_boundary_is_allowed(self):
        loaded = [({"session_id": "test"}, [{"turn_index": 0, "prompt_tokens": 512, "output_tokens": 255}])]
        result = validate_admission(loaded, {}, {"context_length": 4096, "max_total_num_tokens": 1024, "page_size": 256})
        self.assertEqual(result["minimum_output_headroom_tokens"], 0)

    def test_would_shorten_is_rejected(self):
        loaded = [({"session_id": "test"}, [{"turn_index": 0, "prompt_tokens": 512, "output_tokens": 256}])]
        with self.assertRaisesRegex(ValueError, "would shorten"):
            validate_admission(loaded, {}, {"context_length": 4096, "max_total_num_tokens": 1024, "page_size": 256})

    def test_smoke_limit_uses_actual_target(self):
        loaded = [({"session_id": "test"}, [{"turn_index": 0, "prompt_tokens": 512, "output_tokens": 400}])]
        result = validate_admission(loaded, {"output_token_cap": 32},
                                    {"context_length": 4096, "max_total_num_tokens": 1024, "page_size": 256})
        self.assertEqual(result["minimum_output_headroom_tokens"], 223)

    def test_selection_is_stable_and_task_disjoint(self):
        entries = [{"task_id": f"task_{task}", "session_id": f"session_{task}_{trial}",
                    "split": "calibration", "max_prompt_plus_output_tokens": task * 100 + trial}
                   for task in range(12) for trial in range(2)]
        entries.append({"task_id": "evaluation", "session_id": "evaluation", "split": "evaluation"})
        selected = select_sessions(entries)
        self.assertEqual(selected, select_sessions(list(reversed(entries))))
        self.assertEqual(len({entry["task_id"] for entry in selected}), 8)
        self.assertEqual({entry["split"] for entry in selected}, {"calibration"})

    def test_high_capacity_changes_no_other_server_flag(self):
        smoke = json.loads((ROOT / "configs/smoke_server.json").read_text())
        high = json.loads((ROOT / "configs/calibration_high_server.json").read_text())
        high["max_total_tokens"] = smoke["max_total_tokens"]
        self.assertEqual(build_command(smoke, "lru"), build_command(high, "lru"))

    def test_eviction_counter_is_raw_not_divided_by_ranks(self):
        before = metric_samples('sglang:evicted_tokens_total{cache_type="UnifiedRadixCache"} 16\n')
        after = metric_samples('sglang:evicted_tokens_total{cache_type="UnifiedRadixCache"} 80\n')
        self.assertEqual(counter_deltas(before, after)[0]["raw_delta"], 64)

    def test_missing_counter_baseline_is_not_zero(self):
        after = metric_samples('sglang:evicted_tokens_total{cache_type="UnifiedRadixCache"} 80\n')
        self.assertIsNone(counter_deltas({}, after)[0]["raw_delta"])

    def test_counter_reset_is_not_negative_eviction(self):
        before = metric_samples('sglang:evicted_tokens_total 80\n')
        after = metric_samples('sglang:evicted_tokens_total 16\n')
        self.assertIsNone(counter_deltas(before, after)[0]["raw_delta"])

    def test_observed_window_does_not_claim_full_measurement(self):
        result = observed_counter_windows({("sglang:evicted_tokens_total", ()): [("first", 16), ("last", 80)]})[0]
        self.assertEqual(result["observed_window_raw_delta"], 64)
        self.assertFalse(result["covers_entire_measurement"])

    def test_observed_window_counter_reset_is_not_summed(self):
        result = observed_counter_windows({("sglang:evicted_tokens_total", ()): [("first", 80), ("second", 8), ("last", 96)]})[0]
        self.assertIsNone(result["observed_window_raw_delta"])
        self.assertFalse(result["monotone"])

    def test_residency_includes_evictable_without_summing_ranks(self):
        raw = '\n'.join(f'sglang:kv_{name}_tokens{{tp_rank="{rank}"}} {value}'
                        for rank in [0, 1] for name, value in [("available", 25), ("used", 25), ("evictable", 50)])
        observations = pool_observations(metric_samples(raw), {"full_tokens": 100, "swa_tokens": 10})
        self.assertEqual(len(observations), 2)
        for row in observations:
            self.assertEqual(row["resident_fraction"], .75)
            self.assertEqual(row["accounting_residual_tokens"], 0)

    def test_missing_pool_components_remain_unknown(self):
        raw = 'sglang:kv_available_tokens{tp_rank="0"} 25\n'
        observed = pool_observations(metric_samples(raw), {"full_tokens": 100, "swa_tokens": 10})[0]
        self.assertIsNone(observed["accounting_residual_tokens"])
        self.assertIsNone(observed["evictable_tokens"])

    def test_native_response_timing_is_lost_after_two_ipc_hops(self):
        from sglang.srt.observability.req_time_stats import SchedulerReqTimeStats
        original = SchedulerReqTimeStats(enable_metrics=True, wait_queue_entry_time=10.0, forward_entry_time=12.0)
        first = pickle.loads(pickle.dumps(original))
        second = pickle.loads(pickle.dumps(first))
        self.assertEqual(first.convert_to_output_meta_info()["queue_time"], 2)
        self.assertEqual(second.convert_to_output_meta_info()["queue_time"], 0)
        self.assertNotIn("forward_entry_time", second.convert_to_output_meta_info())

    def test_queue_histogram_uses_deltas_and_bucket_bounds(self):
        before = metric_samples('\n'.join([
            'sglang:queue_time_seconds_count{tp_rank="0"} 1',
            'sglang:queue_time_seconds_sum{tp_rank="0"} 0.1',
            'sglang:queue_time_seconds_bucket{tp_rank="0",le="0.1"} 1',
            'sglang:queue_time_seconds_bucket{tp_rank="0",le="1"} 1',
            'sglang:queue_time_seconds_bucket{tp_rank="0",le="+Inf"} 1']))
        after = metric_samples('\n'.join([
            'sglang:queue_time_seconds_count{tp_rank="0"} 3',
            'sglang:queue_time_seconds_sum{tp_rank="0"} 0.6',
            'sglang:queue_time_seconds_bucket{tp_rank="0",le="0.1"} 2',
            'sglang:queue_time_seconds_bucket{tp_rank="0",le="1"} 3',
            'sglang:queue_time_seconds_bucket{tp_rank="0",le="+Inf"} 3']))
        result = queue_histogram_deltas(before, after, 2)[0]
        self.assertTrue(result["measurement_coverage_validated"])
        self.assertEqual(result["mean_seconds"], .25)
        self.assertEqual(result["quantile_bucket_bounds"]["0.95"]["upper_seconds"], 1)
        self.assertFalse(queue_histogram_deltas(before, after, 3)[0]["measurement_coverage_validated"])

    def test_budget_keeps_long_waits_and_is_not_a_runtime_limit(self):
        result = estimate({"test": {"task_id": "task", "wait_seconds": 3601, "output_tokens": 100}}, .1, 90, 1)
        self.assertEqual(result["estimated_makespan_hours"], 3611 / 3600)
        self.assertEqual(result["schedule"][0]["source_wait_seconds"], 3601)

    def test_budget_schedule_does_not_depend_on_input_order(self):
        sessions = {f"session_{index}": {"task_id": f"task_{index}", "wait_seconds": index, "output_tokens": 100}
                    for index in range(5)}
        self.assertEqual(estimate(sessions, .1, 90, 1), estimate(dict(reversed(list(sessions.items()))), .1, 90, 1))


if __name__ == "__main__":
    unittest.main()
