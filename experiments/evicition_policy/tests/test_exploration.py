import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from exploration_gate import validation_errors, verify_release
from prepare_data import canonical_digest, digest_file, save_json
from prepare_exploration import apply_timing_transform, ordered_selection
from shape_warmup import run_shapes, validate_shapes
import run_exploration


def valid_density_result():
    return {"state": {"status": "completed"}, "completed_requests": 2,
            "integrity_audit": {"protocol_integrity_passed": True, "post_flush_native_metrics_empty": True,
                                "cached_tokens_all_known": True},
            "sessions": [{"complete": True}], "owned_gpu_allocations_released": True,
            "native_num_retractions": {"count": 2, "sum": 0, "missing_or_nonfinite": 0},
            "effective_signature": {"server": {"tp_size": 2}},
            "scheduler_queue_histogram_by_rank": [
                {"labels": {"tp_rank": str(rank)}, "measurement_coverage_validated": True,
                 "mean_seconds": .01, "quantile_bucket_bounds": {"0.95": {"upper_seconds": .1}}}
                for rank in range(2)],
            "native_gauges_by_series": [{"name": "sglang:num_queue_reqs", "sample_distribution": {"max": 1}}],
            "client_schedule_lag_seconds": {"p99": .01, "missing_or_nonfinite": 0},
            "observed_counter_windows": [{"name": "sglang:evicted_tokens_total", "monotone": True, "observed_window_raw_delta": 256}],
            "pool_residency_by_series": [{"pool": pool, "accounting_mismatch_samples": 0, "missing_accounting_samples": 0} for pool in ["full", "swa"]],
            "monitor_error_samples": 0}


class ExplorationTest(unittest.TestCase):
    def setUp(self):
        folder = ROOT / "runtime/test_tmp"
        folder.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=folder)
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.criteria = {"max_total_retractions": 0, "max_scheduler_queue_mean_seconds": 1,
                         "max_scheduler_queue_p95_upper_seconds": 5, "max_sampled_queue_requests": 8,
                         "max_client_schedule_lag_p99_seconds": 1, "require_observed_native_eviction_activity": True}

    def test_density_gate_accepts_complete_evidence(self):
        self.assertEqual(validation_errors(valid_density_result(), self.criteria), [])

    def test_density_gate_rejects_missing_rank_and_retraction(self):
        result = valid_density_result()
        result["scheduler_queue_histogram_by_rank"].pop()
        result["native_num_retractions"]["sum"] = 1
        errors = validation_errors(result, self.criteria)
        self.assertIn("queue_rank_coverage_missing", errors)
        self.assertIn("retractions_missing_or_excessive", errors)

    def test_density_gate_rejects_missing_evictions(self):
        result = valid_density_result()
        result["observed_counter_windows"] = []
        self.assertIn("native_eviction_activity_unobserved", validation_errors(result, self.criteria))

    def test_density_gate_rejects_queue_and_incomplete_workload(self):
        result = valid_density_result()
        result["scheduler_queue_histogram_by_rank"][0]["mean_seconds"] = 2
        result["sessions"][0]["complete"] = False
        errors = validation_errors(result, self.criteria)
        self.assertIn("incomplete_sessions", errors)
        self.assertIn("queue_latency_exceeds_release_threshold", errors)

    def test_explicit_arrivals_keep_all_sessions_and_spacing(self):
        entries = [{"session_id": f"session_{index}", "split": "evaluation"} for index in range(4)]
        selection = ordered_selection({"sessions": entries}, "evaluation", "formal")
        self.assertEqual([row["start_offset_seconds"] for row in selection["sessions"]], [0, 90, 180, 270])
        self.assertEqual(selection, ordered_selection({"sessions": list(reversed(entries))}, "evaluation", "formal"))

    def test_complete_session_limit_is_deterministic(self):
        entries = [{"session_id": f"session_{index}", "split": "evaluation"} for index in range(4)]
        full = ordered_selection({"sessions": entries}, "evaluation", "formal")
        limited = ordered_selection({"sessions": list(reversed(entries))}, "evaluation", "formal", 27.0, 2)
        self.assertEqual(limited["sessions"], [
            {**entry, "start_offset_seconds": index * 27.0}
            for index, entry in enumerate(full["sessions"][:2])
        ])

    def test_accelerated_arrivals_and_gaps_keep_coverage(self):
        entries = [{"session_id": f"session_{index}", "split": "evaluation"} for index in range(4)]
        selection = ordered_selection({"sessions": entries}, "evaluation", "formal", 27.0)
        self.assertEqual([row["start_offset_seconds"] for row in selection["sessions"]], [0, 27, 54, 81])
        workload = {"purpose": "formal", "sessions": selection["sessions"], "requests": 4}
        apply_timing_transform(workload, 0.30, 90)
        self.assertEqual(workload["timing_transform"]["inter_request_gap_scale"], 0.30)
        self.assertTrue(workload["timing_transform"]["preserves_all_sessions_and_requests"])
        self.assertEqual(len(workload["sessions"]), 4)

    def test_density_gate_requires_eviction_volume_and_pool_pressure(self):
        result = valid_density_result()
        result["pool_residency_by_series"] = [
            {"pool": pool, "accounting_mismatch_samples": 0, "missing_accounting_samples": 0,
             "resident_fraction_sample_distribution": {"p95": p95}}
            for pool, p95 in [("full", .96), ("swa", .91)]]
        criteria = {**self.criteria, "require_cache_pressure": True,
                    "min_full_resident_fraction_p95": .95, "min_swa_resident_fraction_p95": .90,
                    "min_observed_native_eviction_raw_delta": 1000}
        errors = validation_errors(result, criteria)
        self.assertIn("native_eviction_activity_below_pressure_floor", errors)
        result["observed_counter_windows"][0]["observed_window_raw_delta"] = 2000
        result["pool_residency_by_series"][0]["resident_fraction_sample_distribution"]["p95"] = .5
        errors = validation_errors(result, criteria)
        self.assertNotIn("native_eviction_activity_below_pressure_floor", errors)
        self.assertIn("full_cache_pressure_unobserved", errors)

    def shape_plan(self):
        tokens = [10, 20, 30]
        return {"purpose": "engineering_shape_warmup_only", "passes": 2,
                "cases": [{"case_id": "first", "input_ids": tokens, "input_ids_sha256": canonical_digest(tokens),
                           "output_tokens": 2, "source": {"split": "calibration"}}], "groups": [["first"]]}

    def test_shape_hash_and_groups_checked(self):
        plan = self.shape_plan()
        info = {"context_length": 4096, "max_total_num_tokens": 4096, "page_size": 256}
        validate_shapes(plan, info)
        plan["groups"].append(["first"])
        with self.assertRaises(ValueError):
            validate_shapes(plan, info)
        plan = self.shape_plan()
        plan["cases"][0]["input_ids"][0] = 1
        with self.assertRaises(ValueError):
            validate_shapes(plan, info)

    def test_shape_warmup_saves_native_input_echo(self):
        asyncio.run(self.mock_shape(False))

    def test_shape_warmup_failure_is_retained(self):
        asyncio.run(self.mock_shape(True))

    async def mock_shape(self, wrong_echo):
        import aiohttp
        async def generate(request):
            payload = await request.json()
            return web.json_response({"prompt_token_ids": [0] if wrong_echo else payload["input_ids"],
                                      "output_ids": [40, 41], "meta_info": {"prompt_tokens": 3,
                                      "completion_tokens": 2, "finish_reason": {"type": "length"}}})
        application = web.Application()
        application.router.add_post("/generate", generate)
        runner = web.AppRunner(application)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        destination = self.folder / "warmup"
        try:
            async with aiohttp.ClientSession() as client:
                if wrong_echo:
                    with self.assertRaises(RuntimeError):
                        await run_shapes(client, f"http://127.0.0.1:{port}", self.shape_plan(), destination)
                    self.assertEqual(json.loads((destination / "summary.json").read_text())["status"], "failed")
                else:
                    result = await run_shapes(client, f"http://127.0.0.1:{port}", self.shape_plan(), destination)
                    self.assertEqual(result["completed_requests"], 1)
                    self.assertTrue(json.loads((destination / "first.json").read_text())["native_input_echo_exact_match"])
        finally:
            await runner.cleanup()

    def test_release_rejects_input_drift_extra_policies_and_failed_validation(self):
        artifact = self.folder / "artifact.json"
        save_json(artifact, {"fixed": True})
        results = self.folder / "results"
        results.mkdir()
        release_path = results / "release.json"
        release = {"status": "passed", "validation_errors": [], "policies": ["lru", "lfu", "slru"],
                   "repeats_per_policy": 1, "input_sha256": {name: digest_file(artifact) for name in ["config", "workload", "protocol_warmup", "shape_warmup"]},
                   "evidence_sha256": {}, "script_sha256": {}}
        save_json(release_path, release)
        with mock.patch("exploration_gate.ROOT", self.folder):
            verify_release(release_path, artifact, artifact, artifact, artifact, ["lru", "lfu", "slru"])
            with self.assertRaises(ValueError):
                verify_release(release_path, artifact, artifact, artifact, artifact, ["lru", "lfu", "slru", "lru"])
            save_json(artifact, {"drift": True})
            with self.assertRaises(ValueError):
                verify_release(release_path, artifact, artifact, artifact, artifact, ["lru", "lfu", "slru"])
            release["status"] = "failed"
            save_json(release_path, release)
            with self.assertRaises(ValueError):
                verify_release(release_path, artifact, artifact, artifact, artifact, ["lru", "lfu", "slru"])

    def test_controller_waits_for_validation_before_starting_three_policies(self):
        asyncio.run(self.mock_controller(False))

    def test_controller_never_starts_policies_after_failed_validation(self):
        asyncio.run(self.mock_controller(True))

    async def mock_controller(self, fail_validation):
        prepared = self.folder / "prepared"
        prepared.mkdir()
        for filename in ["server.json", "evaluation.json", "shape_warmup.json"]:
            save_json(prepared / filename, {})
        save_json(prepared / "criteria.json", self.criteria)
        output = self.folder / "controller"
        output.mkdir()
        validation_suite = self.folder / "pilot"
        run = validation_suite / "01_lru"
        (run / "measurement").mkdir(parents=True)
        for filename in ["state.json", "cleanup.json", "effective_signature.json", "protocol.json", "metrics_before.prom", "measurement/summary.json", "measurement/requests.jsonl"]:
            (run / filename).write_text("{}")
        for pass_index in [1, 2]:
            save_json(run / f"shape_pass_{pass_index}" / "summary.json", {
                "status": "completed", "completed_requests": 12, "maximum_prompt_tokens": 172032})
        result = valid_density_result()
        if fail_validation:
            result["native_num_retractions"]["sum"] = 1
        mocked_suite = mock.AsyncMock(side_effect=[validation_suite, self.folder / "evaluation"])
        prepared_metadata = {"timing_transform": "uniform_accelerated_replay_v1",
                             "inter_request_gap_scale": 0.30, "target_experiment_seconds": 3600}
        with mock.patch.object(run_exploration, "check_prepared", return_value=prepared_metadata), \
             mock.patch.object(run_exploration, "verify_environment", return_value={}), \
             mock.patch.object(run_exploration, "suite", mocked_suite), \
             mock.patch.object(run_exploration, "summarize_run", return_value=result), \
             mock.patch.object(run_exploration, "write_comparison"):
            if fail_validation:
                with self.assertRaisesRegex(ValueError, "Validation failed"):
                    await run_exploration.execute(prepared, output)
                self.assertEqual(mocked_suite.await_count, 1)
            else:
                await run_exploration.execute(prepared, output)
                self.assertEqual(mocked_suite.await_count, 2)
                evaluation_args = mocked_suite.await_args_list[1].args[0]
                self.assertEqual(evaluation_args.policies, ["lru", "lfu", "slru"])
                self.assertEqual(json.loads(evaluation_args.release.read_text())["status"], "passed")


if __name__ == "__main__":
    unittest.main()
