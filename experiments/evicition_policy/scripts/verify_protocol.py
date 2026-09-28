#!/usr/bin/env python3
"""Verify the frozen encoder against online tokenization and native generation."""

import argparse
import gzip
import json
import os
from pathlib import Path
import urllib.request

from build_workload import read_rows
from prepare_data import ROOT, canonical_digest, digest_file, save_json


def http_json(base_url: str, endpoint: str, payload=None):
    request = urllib.request.Request(base_url + endpoint,
                                     data=None if payload is None else json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def verify(base_url: str, workload: dict) -> dict:
    source_index = {entry["session_id"]: entry for entry in json.loads(
        (ROOT / "data/normalized/session_index.json").read_text())}
    info = http_json(base_url, "/server_info")
    if info.get("version") != "0.5.13.post1":
        raise ValueError("Unexpected running engine")
    checks = []
    for entry in workload["sessions"]:
        source = source_index[entry["session_id"]]
        source_path = ROOT / source["normalized_path"]
        if digest_file(source_path) != source["normalized_sha256"]:
            raise ValueError("Normalized input hash drift")
        encoded = read_rows(entry)[:entry["replay_requests"]]
        with gzip.open(source_path, "rt") as stream:
            for target, line in zip(encoded, stream):
                body = json.loads(line)["request_body"]
                payload = {"model": info["served_model_name"], "messages": body["messages"],
                           "tools": body["tools"], "chat_template_kwargs": {"thinking": True}}
                online = http_json(base_url, "/tokenize", payload)
                match = online["tokens"] == target["input_ids"] and online["count"] == target["prompt_tokens"]
                checks.append({"session_id": entry["session_id"], "turn_index": target["turn_index"],
                               "expected_ids_sha256": target["input_ids_sha256"],
                               "online_ids_sha256": canonical_digest(online["tokens"]),
                               "online_prompt_tokens": online["count"], "exact_match": match})
    first_entry = workload["sessions"][0]
    first = read_rows(first_entry)[0]
    generated = http_json(base_url, "/generate", {
        "input_ids": first["input_ids"], "return_prompt_token_ids": True,
        "sampling_params": {"temperature": 0, "max_new_tokens": 2, "ignore_eos": True, "sampling_seed": 42}})
    native_match = generated.get("prompt_token_ids") == first["input_ids"]
    output_match = len(generated.get("output_ids", [])) == generated["meta_info"]["completion_tokens"] == 2
    return {"status": "passed" if checks and all(item["exact_match"] for item in checks) and native_match and output_match else "failed",
            "checks": checks, "native_input_ids_echo_exact_match": native_match,
            "native_output_length_exact_match": output_match, "native_meta_info": generated["meta_info"],
            "tokenize_reasoning_effort_source": "locked_server_env_SGLANG_DSV4_REASONING_EFFORT=max",
            "note": "TokenizeRequest excludes top-level max; server default max is locked. This does not prove the historical provider template.",
            "historical_template_reproduced": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:31080")
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if not args.output.resolve().is_relative_to(ROOT) or args.output.exists():
        raise ValueError("Use a new result path inside this experiment")
    result = verify(args.base_url, json.loads(args.workload.read_text()))
    save_json(args.output, result)
    print(json.dumps({"status": result["status"], "checks": len(result["checks"])}))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
