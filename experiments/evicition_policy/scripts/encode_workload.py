#!/usr/bin/env python3
"""Encode historical content with the pinned official target-serving renderer."""

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
from pathlib import Path
import types

from prepare_data import ROOT, canonical_digest, digest_file, save_json

MODEL = Path("/inspire/hdd/global_public/public_models/deepseek-ai/deepSeek-V4-Flash")


def renderer():
    import sglang
    from transformers import AutoTokenizer
    from sglang.srt.entrypoints.openai.serving_chat import OpenAIServingChat

    if not Path(sglang.__file__).resolve().is_relative_to(ROOT / "runtime/venv"):
        raise RuntimeError("Only the isolated official engine may encode this workload")
    serving = OpenAIServingChat.__new__(OpenAIServingChat)
    serving.template_manager = types.SimpleNamespace(jinja_template_content_format="string")
    serving.tokenizer_manager = types.SimpleNamespace(
        tokenizer=AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True)
    )
    serving.chat_encoding_spec = "dsv4"
    return serving


def encode_body(serving, body: dict) -> list[int]:
    from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest

    allowed = {"model", "messages", "input", "tools", "stream"}
    if set(body) - allowed or body.get("input") != body["messages"]:
        raise ValueError("Unexpected source payload; review conversion before dropping fields")
    request = ChatCompletionRequest(
        model="deepseek-v4-flash", messages=body["messages"], tools=body["tools"],
        reasoning_effort="max", chat_template_kwargs={"thinking": True},
    )
    return serving._apply_jinja_template(request, None, False).prompt_ids


def encode_session(arguments: tuple[dict, str]) -> dict:
    session, destination = arguments
    serving = renderer()
    output_path = Path(destination) / f"{session['session_id']}.jsonl.gz"
    source = ROOT / session["normalized_path"]
    if digest_file(source) != session["normalized_sha256"]:
        raise ValueError("Normalized source hash drift")
    previous_ids = []
    rows = []
    largest_total = 0
    with gzip.open(source, "rt") as stream:
        for line in stream:
            record = json.loads(line)
            token_ids = encode_body(serving, record["request_body"])
            output_length = record["completion_tokens_source_usage"]
            if not isinstance(output_length, int) or output_length <= 0:
                raise ValueError("No valid recorded output length")
            gap = record["wait_after_previous_response_candidate_seconds"]
            if record["turn_index"] > 0 and (gap is None or gap < 0):
                raise ValueError("Missing or negative dependency gap")
            prefix = 0
            for current, previous in zip(token_ids, previous_ids):
                if current != previous:
                    break
                prefix += 1
            rows.append({"session_id": session["session_id"], "task_id": session["task_id"],
                         "turn_index": record["turn_index"], "source_line": record["source_line"],
                         "input_ids": token_ids, "input_ids_sha256": canonical_digest(token_ids),
                         "prompt_tokens": len(token_ids), "output_tokens": output_length,
                         "wait_after_previous_response_seconds": gap,
                         "same_session_previous_input_lcp_tokens": prefix,
                         "source_prompt_tokens": record["response_body"]["usage"].get("prompt_tokens"),
                         "time_basis": "recorded_callback_relative_interval_version_unverified",
                         "historical_provider_template_reproduced": False})
            previous_ids = token_ids
            largest_total = max(largest_total, len(token_ids) + output_length)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".part")
    with temporary.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
        for row in rows:
            stream.write((json.dumps(row, separators=(",", ":")) + "\n").encode())
    temporary.replace(output_path)
    return {"session_id": session["session_id"], "task_id": session["task_id"],
            "requests": len(rows), "path": str(output_path.relative_to(ROOT)),
            "sha256": digest_file(output_path), "max_prompt_plus_output_tokens": largest_total,
            "model_context_eligible": largest_total <= 1048576,
            "source_normalized_sha256": session["normalized_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["calibration", "evaluation", "all"], default="all")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    os.umask(0o077)
    sessions = json.loads((ROOT / "data/normalized/session_index.json").read_text())
    assignments = json.loads((ROOT / "data/normalized/task_split.json").read_text())["assignments"]
    selected = [session for session in sessions if args.split == "all" or assignments[session["task_id"]] == args.split]
    output = ROOT / "data/encoded/sglang_0513_thinking_max_v1"
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / f"manifest_{args.split}.json"
    if manifest_path.exists():
        raise FileExistsError("Encoded manifest already exists; verify it or create a new named version")
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(encode_session, [(session, str(output)) for session in selected]):
            result["split"] = assignments[result["task_id"]]
            results.append(result)
            print(json.dumps({"encoded_sessions": len(results), "total": len(selected)}), flush=True)
    import sglang
    import importlib.metadata

    package = Path(sglang.__file__).parent
    manifest = {"schema": 1, "purpose": "encoded_pool_not_frozen_formal_workload",
                "split": args.split, "sessions": results, "requests": sum(result["requests"] for result in results),
                "encoder": {"sglang_version": importlib.metadata.version("sglang"),
                            "serving_chat_sha256": digest_file(package / "srt/entrypoints/openai/serving_chat.py"),
                            "encoding_sha256": digest_file(package / "srt/entrypoints/openai/encoding_dsv4.py"),
                            "tokenizer_sha256": digest_file(MODEL / "tokenizer.json"),
                            "thinking": True, "reasoning_effort": "max",
                            "rule": "official_ChatCompletionRequest_and_apply_jinja_template"},
                "source_template_reproduced": False, "data_volume_selected": False,
                "time_semantics_exact_collector_version_verified": False,
                "input_encoding_vs_running_server_verified": False,
                "ready_for_formal_experiment": False}
    save_json(manifest_path, manifest)
    print(json.dumps({"manifest": str(manifest_path), "sessions": len(results), "requests": manifest["requests"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
