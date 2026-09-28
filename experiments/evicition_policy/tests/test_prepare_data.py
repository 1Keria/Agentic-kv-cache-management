from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


SPEC = importlib.util.spec_from_file_location(
    "prepare_data", Path(__file__).resolve().parents[1] / "scripts/prepare_data.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareDataTest(unittest.TestCase):
    def setUp(self):
        temporary_root = MODULE.ROOT / "runtime/test_tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.relative = MODULE.CONFIG_PREFIX + MODULE.CONFIGS[0] + "/run/task-one__trial/trajectory/llm_trajectory.jsonl"
        self.path = self.root / self.relative
        self.path.parent.mkdir(parents=True)
        self.row = {
            "request": {"timestamp": "2026-06-09T00:00:00+00:00", "body": {
                "model": "deepseek/deepseek-v4-flash",
                "messages": [{"role": "system", "content": "synthetic test"},
                             {"role": "assistant", "content": "test", "reasoning_content": "retained"}],
                "tools": [{"type": "function", "function": {"name": "test_tool"}}],
            }},
            "response": {"timestamp": "2026-06-09T00:00:10+00:00", "body": {
                "usage": {"completion_tokens": 5}, "choices": [{"message": {"role": "assistant", "content": "test"}}],
            }},
            "duration_ms": 10000,
        }
        metadata = {"agent": "openhands", "model": "deepseek/deepseek-v4-flash",
                    "partial_trajectory": False, "error": "task failed", "rewards": {"reward": 0}}
        (self.path.parent.parent / "result.json").write_text(json.dumps(metadata))

    def trace(self, rows):
        self.path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return MODULE.audit_trace(self.path, self.relative)

    def test_failed_task_and_full_request_are_preserved(self):
        summary, rows = self.trace([self.row])
        self.assertTrue(summary["structural_candidate"])
        self.assertTrue(summary["task_error_recorded"])
        self.assertFalse(summary["ready_for_gpu"])
        self.assertEqual(rows[0]["request_body"], self.row["request"]["body"])
        self.assertFalse(rows[0]["time_semantics_verified"])

    def test_missing_time_and_usage_are_not_invented(self):
        row = copy.deepcopy(self.row)
        del row["response"]["timestamp"]
        del row["response"]["body"]["usage"]
        summary, rows = self.trace([row, self.row])
        self.assertIsNone(rows[0]["completion_tokens_source_usage"])
        self.assertIsNone(rows[1]["wait_after_previous_response_candidate_seconds"])
        self.assertIn("missing_response_time", summary["issues"])
        self.assertIn("missing_or_nonpositive_output_tokens", summary["issues"])

    def test_negative_wait_remains_negative(self):
        summary, rows = self.trace([self.row, self.row])
        self.assertEqual(rows[1]["wait_after_previous_response_candidate_seconds"], -10)
        self.assertIn("overlap_or_clock_error", summary["issues"])

    def test_long_wait_is_not_capped(self):
        second = copy.deepcopy(self.row)
        second["request"]["timestamp"] = "2026-06-09T00:12:10+00:00"
        second["response"]["timestamp"] = "2026-06-09T00:12:20+00:00"
        _, rows = self.trace([self.row, second])
        self.assertEqual(rows[1]["wait_after_previous_response_candidate_seconds"], 720)

    def test_bad_line_breaks_dependency(self):
        self.path.write_text(json.dumps(self.row) + "\nBAD\n" + json.dumps(self.row) + "\n")
        summary, rows = MODULE.audit_trace(self.path, self.relative)
        self.assertEqual(summary["issues"]["malformed_json_line"], 1)
        self.assertEqual(rows[1]["source_line"], 3)
        self.assertIsNone(rows[1]["wait_after_previous_response_candidate_seconds"])

    def test_unknown_clock_is_flagged(self):
        row = copy.deepcopy(self.row)
        row["request"]["timestamp"] = "2026-06-09 00:00:00"
        row["response"]["timestamp"] = "2026-06-09 00:00:10"
        summary, _ = self.trace([row])
        self.assertIn("naive_clock_unverified", summary["issues"])

    def test_path_escape_rejected(self):
        for name in ("../../outside", "/tmp/outside", "a/../../b", "a\\b"):
            with self.assertRaises(ValueError):
                MODULE.scoped_path(self.root, name)

    def test_model_mismatch_is_flagged(self):
        row = copy.deepcopy(self.row)
        row["request"]["body"]["model"] = "another-model"
        summary, _ = self.trace([row])
        self.assertIn("request_model_unverified", summary["issues"])

    def test_nontext_payload_is_not_silently_removed(self):
        row = copy.deepcopy(self.row)
        row["request"]["body"]["messages"][1]["content"] = [{"type": "image_url", "image_url": {"url": "test"}}]
        summary, rows = self.trace([row])
        self.assertIn("nontext_content_requires_validation", summary["issues"])
        self.assertEqual(rows[0]["request_body"], row["request"]["body"])

    def test_source_checksum_is_not_size_only(self):
        self.path.write_bytes(b"test")
        entry = {"expected_size": 4, "sha256": hashlib.sha256(b"test").hexdigest()}
        self.assertTrue(MODULE.verified_file(self.path, entry))
        self.path.write_bytes(b"fail")
        self.assertFalse(MODULE.verified_file(self.path, entry))

    def test_splits_are_stable_and_shared_sequences_stay_together(self):
        sessions = [{"task_id": f"task-{index}", "request_sequence_sha256": str(index)} for index in range(10)]
        sessions.append({"task_id": "alias", "request_sequence_sha256": "0"})
        first = MODULE.split_tasks(sessions)
        second = MODULE.split_tasks(list(reversed(sessions)))
        self.assertEqual(first["assignments"]["task-0"], first["assignments"]["alias"])
        self.assertEqual(first["assignments"], second["assignments"])
        self.assertEqual(first["calibration_groups"], 2)

    def test_nonfinite_numbers_rejected(self):
        for content in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(ValueError):
                MODULE.strict_json(content)

    def test_local_restore_requires_upstream_checksum(self):
        payload = b"{\"test\":true}\n"
        self.path.write_bytes(payload)
        destination = self.root / "output"
        lock = {"dataset": MODULE.DATASET, "revision": "a" * 40, "files": [
            {"path": self.relative, "expected_size": len(payload),
             "sha256": hashlib.sha256(payload).hexdigest()},
        ]}
        MODULE.save_json(destination / "data/source_lock.json", lock)
        with patch.object(MODULE, "get_response", side_effect=AssertionError("No network expected")):
            result = MODULE.download(destination, None, "main", 1, self.root)
        self.assertEqual(result["verified"], 1)
        self.assertEqual((destination / "data/raw/skillsbench" / self.relative).read_bytes(), payload)

    def test_audit_missing_files_cannot_be_ready(self):
        MODULE.save_json(self.root / "download_manifest.json", [[self.relative, 100]])
        destination = self.root / "output"
        result = MODULE.audit(destination, self.root)
        self.assertEqual(result["status"], "blocked_missing_raw_data")
        self.assertEqual(result["filter_counts"], {"raw_file_missing": 1})
        self.assertFalse(result["ready_for_gpu"])

    def test_normalized_duplicate_keeps_distinct_timing(self):
        self.trace([self.row])
        first_summary, _ = MODULE.audit_trace(self.path, self.relative)
        second = copy.deepcopy(self.row)
        second["response"]["timestamp"] = "2026-06-09T00:00:20+00:00"
        second_summary, _ = self.trace([second])
        self.assertNotEqual(first_summary["canonical_trace_sha256"], second_summary["canonical_trace_sha256"])
        self.assertEqual(first_summary["request_sequence_sha256"], second_summary["request_sequence_sha256"])

    def test_observation_end_is_not_task_end(self):
        metadata = self.path.parent.parent / "result.json"
        metadata.unlink()
        summary, _ = self.trace([self.row])
        self.assertIsNone(summary["observed_partial_trajectory"])
        self.assertIn("agent_model_metadata_unverified", summary["issues"])

    def test_paginated_tree_does_not_rely_on_truncated_repository_listing(self):
        revision = "a" * 40
        metadata = {"sha": revision, "siblings": [], "cardData": {"license": "apache-2.0"}}
        first_entry = {"type": "file", "path": self.relative, "size": 10,
                       "oid": "b" * 40, "lfs": {"oid": "c" * 64, "size": 10}}
        config_name = str(Path(self.relative).parents[1] / "config.json")
        second_entry = {"type": "file", "path": config_name, "size": 5, "oid": "d" * 40}
        directory = MODULE.CONFIG_PREFIX + MODULE.CONFIGS[0]
        next_url = f"https://huggingface.co/api/datasets/{MODULE.DATASET}/tree/{revision}/{directory}?cursor=next"

        def response(payload, next_page=None):
            result = MagicMock()
            result.__enter__.return_value = result
            result.json.return_value = payload
            result.links = {"next": {"url": next_page}} if next_page else {}
            return result

        responses = [response(metadata), response([first_entry], next_url), response([second_entry]),
                     response([]), response([])]
        with patch.object(MODULE, "get_response", side_effect=responses) as fetch:
            lock = MODULE.source_lock(self.root / "output", None, "main", "https://hf-mirror.com")
        self.assertEqual(lock["trace_count"], 1)
        self.assertEqual(len(lock["files"]), 2)
        self.assertTrue(all(call.args[0].startswith("https://hf-mirror.com/") for call in fetch.call_args_list))
        trace_entry = next(entry for entry in lock["files"] if entry["path"] == self.relative)
        self.assertEqual(trace_entry["sha256"], "c" * 64)


if __name__ == "__main__":
    unittest.main()
