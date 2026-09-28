#!/usr/bin/env python3
"""Read-only CPU preflight; never launches serving or executes recorded tools."""

from __future__ import annotations

import collections
import concurrent.futures
import copy
import datetime
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

from prepare_data import ROOT, digest_file, interval_seconds, save_json, verified_file


MODEL = Path("/inspire/hdd/global_public/public_models/deepseek-ai/deepSeek-V4-Flash")


def statistics(values: list[float]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0}

    def quantile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    return {"count": len(ordered), "min": ordered[0], "median": quantile(0.5),
            "p95": quantile(0.95), "p99": quantile(0.99), "max": ordered[-1]}


def load_encoder():
    specification = importlib.util.spec_from_file_location(
        "readiness_model_encoder", MODEL / "encoding/encoding_dsv4.py"
    )
    encoder = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(encoder)
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
    return encoder, tokenizer


def candidate_messages(body: dict) -> list[dict]:
    messages = copy.deepcopy(body["messages"])
    if any(not isinstance(message.get("content"), (str, type(None))) for message in messages):
        raise ValueError("Structured content requires verified serving conversion")
    if body.get("response_format") or body.get("tool_choice"):
        raise ValueError("Additional prompt conversion requires verification")
    if not messages or messages[0].get("role") != "system":
        raise ValueError("No existing system message for tools placement")
    if body.get("tools"):
        messages[0]["tools"] = copy.deepcopy(body["tools"])
    return messages


def inspect_session(session: dict) -> dict:
    encoder, tokenizer = load_encoder()
    source = ROOT / "data/raw/skillsbench" / session["source_path"]
    counts = collections.Counter()
    body_fields = collections.Counter()
    message_fields = collections.Counter()
    models = collections.Counter()
    paths = collections.Counter()
    statuses = collections.Counter()
    finish_reasons = collections.Counter()
    waits = []
    elapsed_values = []
    duration_errors = []
    prompts = []
    completions = []
    previous_end = None
    previous_messages = None
    first_record = None
    largest_record = None
    largest_prompt = -1
    with source.open() as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            request = record["request"]
            response = record["response"]
            body = request["body"]
            response_body = response["body"]
            usage = response_body.get("usage") or {}
            counts["requests"] += 1
            body_fields.update(body.keys())
            models[str(body.get("model"))] += 1
            paths[str(request.get("path"))] += 1
            statuses[str(response.get("status_code"))] += 1
            counts["input_equals_messages"] += body.get("input") == body["messages"]
            counts["request_explicit_thinking"] += "thinking" in body
            counts["request_explicit_reasoning_effort"] += "reasoning_effort" in body
            counts["request_explicit_template_kwargs"] += "chat_template_kwargs" in body
            counts["streaming_requests"] += bool(body.get("stream"))
            for message in body["messages"]:
                message_fields.update(message.keys())
                counts["message_content_type_" + type(message.get("content")).__name__] += 1
            for choice in response_body.get("choices") or []:
                finish_reasons[str(choice.get("finish_reason"))] += 1
                counts["responses_with_reasoning_content"] += bool((choice.get("message") or {}).get("reasoning_content"))
            elapsed = interval_seconds(request.get("timestamp"), response.get("timestamp"))
            if elapsed is not None:
                elapsed_values.append(elapsed)
                counts["negative_elapsed"] += elapsed < 0
                duration = record.get("duration_ms")
                if isinstance(duration, (float, int)):
                    duration_errors.append(abs(elapsed * 1000 - duration))
            else:
                counts["unknown_elapsed"] += 1
            if previous_end is not None:
                wait = interval_seconds(previous_end, request.get("timestamp"))
                if wait is not None:
                    waits.append(wait)
                    counts["negative_wait"] += wait < 0
                else:
                    counts["unknown_wait"] += 1
            current_messages = body["messages"]
            if previous_messages is not None:
                counts["message_sequence_append"] += current_messages[:len(previous_messages)] == previous_messages
                counts["message_sequence_changed"] += current_messages[:len(previous_messages)] != previous_messages
            previous_messages = current_messages
            previous_end = response.get("timestamp")
            prompt_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            if isinstance(prompt_tokens, int):
                prompts.append(prompt_tokens)
                if prompt_tokens > largest_prompt:
                    largest_prompt = prompt_tokens
                    largest_record = (line_number, record)
            if isinstance(output_tokens, int):
                completions.append(output_tokens)
            if first_record is None:
                first_record = (line_number, record)
    token_checks = []
    samples = dict(item for item in [first_record, largest_record] if item is not None)
    for line_number, record in samples.items():
        for mode, effort in [("chat", None), ("thinking", None), ("thinking", "max")]:
            check = {"source_line": line_number, "thinking_mode": mode, "reasoning_effort": effort,
                     "sample_rule": "first_or_largest_source_prompt", "source_usage_prompt_tokens":
                     record["response"]["body"].get("usage", {}).get("prompt_tokens")}
            try:
                messages = candidate_messages(record["request"]["body"])
                rendered = encoder.encode_messages(messages, thinking_mode=mode, reasoning_effort=effort)
                token_ids = tokenizer.encode(rendered, add_special_tokens=False).ids
                check["candidate_prompt_tokens"] = len(token_ids)
                check["token_ids_sha256"] = hashlib.sha256(json.dumps(token_ids, separators=(",", ":")).encode()).hexdigest()
                source_tokens = check["source_usage_prompt_tokens"]
                check["token_difference_from_source_usage"] = len(token_ids) - source_tokens if isinstance(source_tokens, int) else None
                output_tokens = record["response"]["body"].get("usage", {}).get("completion_tokens")
                check["candidate_total_tokens"] = len(token_ids) + output_tokens if isinstance(output_tokens, int) else None
                check["encoding_succeeded"] = True
            except (ValueError, TypeError, KeyError, AssertionError, NotImplementedError) as error:
                check["encoding_succeeded"] = False
                check["error_type"] = type(error).__name__
            token_checks.append(check)
    return {"session_id": session["session_id"], "task_id": session["task_id"],
            "source_sha256_matches_index": digest_file(source) == session["source_sha256"],
            "counts": dict(counts), "body_fields": dict(body_fields), "message_fields": dict(message_fields),
            "models": dict(models), "paths": dict(paths), "statuses": dict(statuses),
            "finish_reasons": dict(finish_reasons), "waits": waits, "elapsed": elapsed_values,
            "duration_abs_error_ms": duration_errors, "source_prompt_tokens": prompts,
            "source_completion_tokens": completions, "candidate_encoding_checks": token_checks}


def command(arguments: list[str]) -> dict:
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=25)
        return {"returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()[:1000]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error_type": type(error).__name__}


def environment() -> dict:
    specification = importlib.util.find_spec("sglang")
    origin = specification.origin if specification else None
    source_root = Path(origin).parents[2] if origin else None
    source_runtime = Path(origin).parent / "srt" if origin else None
    version_names = ["torch", "transformers", "tokenizers", "sglang", "sgl-kernel"]
    versions = {}
    for name in version_names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    policy_text = (source_runtime / "mem_cache/evict_policy.py").read_text() if source_runtime else ""
    model_config = json.loads((MODEL / "config.json").read_text())
    index = json.loads((MODEL / "model.safetensors.index.json").read_text())
    shard_names = sorted(set(index["weight_map"].values()))
    return {
        "hostname": command(["hostname"]), "packages": versions, "sglang_origin": origin,
        "sglang_git_head": command(["git", "-C", str(source_root), "rev-parse", "HEAD"]) if source_root else None,
        "sglang_tracked_status": command(["git", "-C", str(source_root), "status", "--porcelain", "--untracked-files=no"]) if source_root else None,
        "default_engine_model_file_exists": (source_runtime / "models/deepseek_v4.py").is_file() if source_runtime else False,
        "default_engine_scorers": {name: name in policy_text for name in ["LRUStrategy", "LFUStrategy", "SLRUStrategy", "TLRUStrategy"]},
        "official_isolated_environment_lock_exists": (ROOT / "configs/environment.lock.json").is_file(),
        "gpu": command(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv"]),
        "gpu_compute_processes": command(["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv"]),
        "tmux": command(["tmux", "-V"]), "free_disk_bytes": shutil.disk_usage(ROOT).free,
        "model": {"path": str(MODEL), "model_type": model_config.get("model_type"),
                  "context_limit": model_config.get("max_position_embeddings"), "shards": len(shard_names),
                  "missing_shards": [name for name in shard_names if not (MODEL / name).is_file()],
                  "shard_bytes": sum((MODEL / name).stat().st_size for name in shard_names if (MODEL / name).is_file()),
                  "weight_shards_full_hash_verified": False,
                  "file_sha256": {name: digest_file(MODEL / name) for name in
                                  ["config.json", "tokenizer.json", "tokenizer_config.json", "encoding/encoding_dsv4.py"]}},
        "implemented_scripts": sorted(path.name for path in (ROOT / "scripts").glob("*")),
        "frozen_experiment_config_exists": (ROOT / "configs/experiment.yaml").is_file(),
        "frozen_workload_exists": (ROOT / "data/workloads").is_dir(),
        "gpu_serving_launched_by_preflight": False,
    }


def main() -> int:
    os.umask(0o077)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = ROOT / "results/audit" / ("static_preflight_" + stamp)
    root.mkdir(parents=True, exist_ok=False)
    environment_result = environment()
    save_json(root / "environment.json", environment_result)
    lock = json.loads((ROOT / "data/source_lock.json").read_text())
    invalid = [entry["path"] for entry in lock["files"]
               if not verified_file(ROOT / "data/raw/skillsbench" / entry["path"], entry)]
    save_json(root / "source_integrity.json", {"files_checked": len(lock["files"]), "invalid": invalid,
                                              "revision": lock["revision"]})
    sessions = json.loads((ROOT / "data/normalized/session_index.json").read_text())
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as executor:
        for result in executor.map(inspect_session, sessions):
            results.append(result)
            if len(results) % 10 == 0 or len(results) == len(sessions):
                print(json.dumps({"sessions_checked": len(results), "total": len(sessions)}), flush=True)
    save_json(root / "session_checks.json", results)
    combined = {}
    for field in ["counts", "body_fields", "message_fields", "models", "paths", "statuses", "finish_reasons"]:
        combined[field] = dict(sum((collections.Counter(result[field]) for result in results), collections.Counter()))
    for field in ["waits", "elapsed", "duration_abs_error_ms", "source_prompt_tokens", "source_completion_tokens"]:
        combined[field] = statistics([value for result in results for value in result[field]])
    checks = [check for result in results for check in result["candidate_encoding_checks"]]
    candidate_summaries = {}
    for mode, effort in [("chat", None), ("thinking", None), ("thinking", "max")]:
        group = [check for check in checks if check["thinking_mode"] == mode and check["reasoning_effort"] == effort]
        successful = [check for check in group if check["encoding_succeeded"]]
        candidate_summaries[f"{mode}:{effort}"] = {
            "samples": len(group), "succeeded": len(successful),
            "source_length_exact_match": sum(check["token_difference_from_source_usage"] == 0 for check in successful),
            "candidate_prompt_tokens": statistics([check["candidate_prompt_tokens"] for check in successful]),
            "difference_from_source_usage": statistics([check["token_difference_from_source_usage"] for check in successful
                                                        if check["token_difference_from_source_usage"] is not None]),
            "over_model_context": sum(check["candidate_total_tokens"] > environment_result["model"]["context_limit"]
                                      for check in successful if check["candidate_total_tokens"] is not None),
        }
    combined["candidate_encoding"] = candidate_summaries
    combined["encoding_is_diagnostic_sample_not_frozen_input"] = True
    combined["timestamps_naive_do_not_alone_invalidate_relative_intervals"] = True
    combined["timing_semantics_proven_by_collector_source"] = False
    combined["source_usage_is_not_local_service_measurement"] = True
    save_json(root / "data_checks.json", combined)
    result = {
        "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "ready_for_formal_experiment": False, "gpu_service_started_by_this_command": False,
        "source_files_verified": len(lock["files"]) - len(invalid), "source_files_invalid": len(invalid),
        "sessions_checked": len(results), "requests_checked": combined["counts"].get("requests"),
        "scope": "static_data_diagnostics_only_not_live_runtime_readiness",
        "runtime_environment_lock_present": (ROOT / "configs/environment.lock.json").is_file(),
        "encoded_pool_present": (ROOT / "data/encoded/sglang_0513_thinking_max_v1/manifest_all.json").is_file(),
        "not_certified_by_this_command": ["collector_exact_historical_version", "gpu_backend_and_graphs",
                                           "capacity_calibration", "formal_workload_and_arrival_plan"],
        "note": "Static check only. See current preparation report and suite audits; no hard-coded claims about missing runtime scripts.",
    }
    save_json(root / "readiness.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
