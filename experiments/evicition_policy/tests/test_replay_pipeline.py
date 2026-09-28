import asyncio
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_workload import build, effective_gap_seconds, read_rows, timing_scale
from prepare_data import canonical_digest, digest_file
from replay_agent import generation_payload, replay, update_output, validate_workload
from run_suite import cache_is_empty, pool_capacities, stop_owned, wait_gpu_release
from server_command import build_command


class PipelineTest(unittest.TestCase):
    def setUp(self):
        folder = ROOT / "runtime/test_tmp"
        folder.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=folder)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.rows = [{"session_id": "test", "task_id": "task", "turn_index": turn,
                      "input_ids": [10, 20, 30 + turn], "input_ids_sha256": canonical_digest([10, 20, 30 + turn]),
                      "prompt_tokens": 3, "output_tokens": 2,
                      "wait_after_previous_response_seconds": None if turn == 0 else 0.05} for turn in range(2)]
        path = self.folder / "tokens.jsonl.gz"
        with gzip.open(path, "wt") as stream:
            for row in self.rows:
                stream.write(json.dumps(row) + "\n")
        self.entry = {"session_id": "test", "task_id": "task", "path": str(path.relative_to(ROOT)),
                      "sha256": digest_file(path), "requests": 2, "split": "calibration"}
        self.pool = {"sessions": [self.entry]}
        self.selection = {"purpose": "smoke", "sessions": [{"session_id": "test", "start_offset_seconds": 0}]}
        self.workload = build(self.pool, self.selection, "poolhash")

    def test_hash_drift_rejected(self):
        self.entry["sha256"] = "wrong"
        with self.assertRaises(ValueError):
            read_rows(self.entry)

    def test_duplicate_session_rejected(self):
        self.selection["sessions"] *= 2
        with self.assertRaises(ValueError):
            build(self.pool, self.selection, "poolhash")

    def test_wrong_split_rejected(self):
        self.selection["purpose"] = "formal"
        with self.assertRaises(ValueError):
            build(self.pool, self.selection, "poolhash")

    def test_formal_is_gated(self):
        self.workload["purpose"] = "formal"
        with self.assertRaises(ValueError):
            validate_workload(self.workload)

    def test_calibration_cannot_truncate(self):
        self.workload["purpose"] = "calibration"
        with self.assertRaises(ValueError):
            validate_workload(self.workload)

    def test_payload_has_no_identity_or_partition(self):
        payload = generation_payload(self.rows[0], self.workload)
        self.assertEqual(set(payload), {"input_ids", "stream", "sampling_params"})
        self.assertTrue(payload["sampling_params"]["ignore_eos"])

    def test_timing_scale_changes_wait_without_changing_source_row(self):
        self.workload["timing_transform"] = {"inter_request_gap_scale": 0.25}
        self.assertEqual(timing_scale(self.workload), 0.25)
        self.assertEqual(effective_gap_seconds(self.rows[1], self.workload), 0.0125)
        self.assertEqual(self.rows[1]["wait_after_previous_response_seconds"], 0.05)

    def test_invalid_timing_scale_is_rejected(self):
        self.workload["timing_transform"] = {"inter_request_gap_scale": 0}
        with self.assertRaises(ValueError):
            validate_workload(self.workload)

    def test_output_prefix_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            update_output([1, 2], {"output_ids": [1]})

    def test_empty_chunk_is_not_token(self):
        self.assertEqual(update_output([], {"text": "", "meta_info": {}}), [])

    def test_server_error_is_not_success(self):
        with self.assertRaises(RuntimeError):
            update_output([], {"error": {"message": "OOM"}})

    def test_last_pool_capacity_per_rank_is_used(self):
        logs = "\n".join(f"TP{rank}] DSV4 pool sizes: full={full}, swa=256, c4=512, c128=16, c4_state=16, c128_state=256"
                         for full in [4096, 2048] for rank in [0, 1])
        self.assertEqual(pool_capacities(logs, 2)["full_tokens"], 2048)

    def test_missing_pool_rank_rejected(self):
        with self.assertRaises(ValueError):
            pool_capacities("TP0] DSV4 pool sizes: full=2048, swa=256, c4=512, c128=16, c4_state=16, c128_state=256", 2)

    def test_missing_cache_metrics_are_not_zero(self):
        self.assertFalse(cache_is_empty(""))

    def test_flush_requires_empty_swa_and_full(self):
        metrics = "\n".join(name + '{tp_rank="0"} 0' for name in [
            "sglang:num_running_reqs", "sglang:num_queue_reqs", "sglang:kv_evictable_tokens",
            "sglang:kv_used_tokens", "sglang:swa_evictable_tokens"])
        self.assertTrue(cache_is_empty(metrics))
        self.assertFalse(cache_is_empty(metrics.replace('swa_evictable_tokens{tp_rank="0"} 0',
                                                         'swa_evictable_tokens{tp_rank="0"} 256')))

    def test_nonpolicy_arguments_unchanged(self):
        config = json.loads((ROOT / "configs/smoke_server.json").read_text())
        commands = [build_command(config, policy) for policy in ["lru", "lfu", "slru"]]
        for command in commands:
            command[command.index("--radix-eviction-policy") + 1] = "POLICY"
        self.assertEqual(commands[0], commands[1])
        self.assertEqual(commands[0], commands[2])

    def test_owned_process_stop_leaves_unrelated_process(self):
        owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
        try:
            with mock.patch("run_suite.gpu_processes", return_value=""):
                result = stop_owned(owned)
            self.assertEqual(result["remaining_group_members"], [])
            self.assertIsNone(unrelated.poll())
        finally:
            if owned.poll() is None:
                owned.kill()
            unrelated.terminate()
            owned.wait()
            unrelated.wait()

    def test_gpu_release_waits_only_for_owned_pids(self):
        with mock.patch("run_suite.gpu_processes", side_effect=["101, [No data], 100 MiB\n202, other, 100 MiB", "202, other, 100 MiB"]), mock.patch("run_suite.time.sleep"):
            samples = wait_gpu_release([101])
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[-1]["owned_gpu_rows"], [])

    def test_streaming_success_preserves_wait_and_lengths(self):
        asyncio.run(self.run_mock(False))

    def test_streaming_failure_is_persisted(self):
        asyncio.run(self.run_mock(True))

    def test_streaming_records_accelerated_and_source_waits(self):
        self.workload["timing_transform"] = {"inter_request_gap_scale": 0.25}
        asyncio.run(self.run_mock(False, expected_gap=0.0125))

    async def run_mock(self, fail, expected_gap=0.05):
        async def generate(request):
            payload = await request.json()
            response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            chunks = [{"output_ids": [], "meta_info": {"prompt_tokens": 3}}]
            if fail:
                chunks.append({"error": {"message": "test failure"}})
            else:
                chunks.extend([{"output_ids": [40], "meta_info": {"prompt_tokens": 3, "completion_tokens": 1}},
                               {"output_ids": [40, 41], "meta_info": {"prompt_tokens": 3, "completion_tokens": 2,
                                                                       "finish_reason": {"type": "length"}}}])
            for chunk in chunks:
                await response.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            await response.write(b"data: [DONE]\n\n")
            return response
        application = web.Application()
        application.router.add_post("/generate", generate)
        runner = web.AppRunner(application)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        output = self.folder / "result"
        try:
            if fail:
                with self.assertRaises(RuntimeError):
                    await replay(f"http://127.0.0.1:{port}", self.workload, output)
                self.assertEqual(json.loads((output / "summary.json").read_text())["status"], "failed")
            else:
                summary = await replay(f"http://127.0.0.1:{port}", self.workload, output)
                self.assertEqual(summary["completed_requests"], 2)
                records = [json.loads(line) for line in (output / "requests.jsonl").read_text().splitlines()]
                self.assertGreaterEqual(records[1]["actual_gap_seconds"], expected_gap)
                self.assertEqual(records[1]["source_gap_seconds"], 0.05)
                self.assertEqual(records[1]["effective_gap_seconds"], expected_gap)
                self.assertEqual(records[1]["actual_output_tokens"], 2)
                self.assertIsNone(records[0]["cached_tokens"])
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    unittest.main()
