from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPECIFICATION = importlib.util.spec_from_file_location("check_readiness", ROOT / "scripts/check_readiness.py")
MODULE = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(MODULE)


class ReadinessTest(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / "runtime/test_tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_statistics_include_count_and_extremes(self):
        self.assertEqual(MODULE.statistics([]), {"count": 0})
        result = MODULE.statistics([10, 0, 5])
        self.assertEqual(result["min"], 0)
        self.assertEqual(result["max"], 10)
        self.assertEqual(result["median"], 5)

    def test_candidate_conversion_does_not_modify_original(self):
        body = {"messages": [{"role": "system", "content": "test"}],
                "tools": [{"type": "function", "function": {"name": "test"}}]}
        original = copy.deepcopy(body)
        messages = MODULE.candidate_messages(body)
        self.assertEqual(body, original)
        self.assertEqual(messages[0]["tools"], body["tools"])

    def test_unverified_structured_content_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.candidate_messages({"messages": [{"role": "system", "content": [{"type": "text", "text": "test"}]}]})

    def test_session_counts_field_names_not_field_values(self):
        messages = [{"role": "system", "content": "test"}, {"role": "user", "content": "test"}]
        record = {
            "request": {"timestamp": "2026-06-09T00:00:00", "path": "/v1/chat/completions",
                        "body": {"model": "deepseek-v4-flash", "messages": messages,
                                 "input": messages, "tools": [], "stream": True}},
            "response": {"timestamp": "2026-06-09T00:00:01", "status_code": 200,
                         "body": {"usage": {"prompt_tokens": 2, "completion_tokens": 3},
                                  "choices": [{"finish_reason": "stop", "message": {"content": "test"}}]}},
            "duration_ms": 1000,
        }
        path = self.root / "data/raw/skillsbench/trace.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(record) + "\n")
        session = {"session_id": "test", "task_id": "test", "source_path": "trace.jsonl",
                   "source_sha256": MODULE.digest_file(path)}
        encoder = types.SimpleNamespace(encode_messages=lambda *args, **kwargs: "test")
        tokenizer = types.SimpleNamespace(encode=lambda *args, **kwargs: types.SimpleNamespace(ids=[1, 2]))
        with patch.object(MODULE, "ROOT", self.root), patch.object(MODULE, "load_encoder", return_value=(encoder, tokenizer)):
            result = MODULE.inspect_session(session)
        self.assertEqual(result["body_fields"]["messages"], 1)
        self.assertEqual(result["message_fields"]["role"], 2)
        self.assertEqual(result["duration_abs_error_ms"], [0])
        self.assertEqual(result["counts"]["input_equals_messages"], 1)
        self.assertEqual(len(result["candidate_encoding_checks"]), 3)
        self.assertTrue(all(check["encoding_succeeded"] for check in result["candidate_encoding_checks"]))


if __name__ == "__main__":
    unittest.main()
