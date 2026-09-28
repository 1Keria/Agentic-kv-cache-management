import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_results import audit_run
from prepare_data import canonical_digest, digest_file, save_json
from profile_agent import distribution
import test_replay_pipeline


class AnalysisTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_replay_pipeline.PipelineTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.folder = self.fixture.folder / "analysis_run"
        self.folder.mkdir()
        (self.folder / "measurement").mkdir()
        save_json(self.folder / "state.json", {"status": "completed", "policy": "lru"})
        save_json(self.folder / "workload.json", self.fixture.workload)
        self.records = [{"session_id": "test", "turn_index": row["turn_index"],
                         "status": "completed", "input_ids_sha256": row["input_ids_sha256"],
                         "output_ids": [40, 41], "output_ids_sha256": canonical_digest([40, 41]),
                         "actual_output_tokens": 2, "actual_gap_seconds": 0.05,
                         "source_gap_seconds": row["wait_after_previous_response_seconds"],
                         "effective_gap_seconds": row["wait_after_previous_response_seconds"],
                         "prompt_tokens": 3, "ttft_seconds": 0.1, "latency_seconds": 0.2,
                         "cached_tokens": None} for row in self.fixture.rows]
        save_json(self.folder / "effective_signature.json", {"capacity": 256})
        save_json(self.folder / "cleanup.json", {"remaining_group_members": []})
        save_json(self.folder / "flush.json", {"success": True})
        (self.folder / "metrics_before.prom").write_text("")
        self.write_records()

    def write_records(self):
        path = self.folder / "measurement/requests.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in self.records))
        save_json(self.folder / "measurement/summary.json", {
            "status": "completed", "request_log_sha256": digest_file(path),
            "workload_sha256": canonical_digest(self.fixture.workload)})

    def test_profile_empty_is_not_zero(self):
        self.assertEqual(distribution([]), {"count": 0})

    def test_profile_quantiles(self):
        self.assertEqual(distribution([30, 10, 20])["p50"], 20)
        self.assertEqual(distribution([30, 10, 20])["sum"], 60)

    def test_unknown_cache_remains_unknown_and_smoke_not_ranked(self):
        result = audit_run(self.folder)
        self.assertTrue(result["protocol_integrity_passed"])
        self.assertIsNone(result["token_weighted_cache_hit_fraction"])
        self.assertFalse(result["post_flush_native_metrics_empty"])
        self.assertFalse(result["performance_claim_allowed"])

    def test_duplicate_and_missing_requests_fail(self):
        self.records[1] = copy.deepcopy(self.records[0])
        self.write_records()
        self.assertIn("duplicate_or_missing_requests", audit_run(self.folder)["integrity_errors"])

    def test_shortened_wait_fails(self):
        self.records[1]["actual_gap_seconds"] = 0.01
        self.write_records()
        self.assertIn("dependency_wait_shortened", audit_run(self.folder)["integrity_errors"])

    def test_timing_transform_drift_fails(self):
        self.records[1]["effective_gap_seconds"] = 0.01
        self.write_records()
        self.assertIn("timing_transform_drift", audit_run(self.folder)["integrity_errors"])

    def test_input_hash_change_fails(self):
        self.records[1]["input_ids_sha256"] = "bad"
        self.write_records()
        self.assertIn("input_hash_drift", audit_run(self.folder)["integrity_errors"])

    def test_log_drift_fails(self):
        with (self.folder / "measurement/requests.jsonl").open("a") as stream:
            stream.write(json.dumps(self.records[0]) + "\n")
        self.assertIn("request_log_hash_drift", audit_run(self.folder)["integrity_errors"])


if __name__ == "__main__":
    unittest.main()
