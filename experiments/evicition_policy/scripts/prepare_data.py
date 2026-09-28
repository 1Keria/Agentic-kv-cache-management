#!/usr/bin/env python3
"""Restore and audit pinned OpenHands/V4-Flash traces without inventing data."""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import random
import shutil
import time
from urllib.parse import quote, urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
DATASET = "benchflow/skillsbench-leaderboard"
CONFIG_PREFIX = "submissions/skillsbench/v1.1/"
CONFIGS = (
    "openhands-with-skills__deepseek-deepseek-v4-flash-src-runner03",
    "openhands-with-skills__deepseek-deepseek-v4-flash-src-runner05-20260610",
    "openhands-with-skills__deepseek-deepseek-v4-flash",
)
HISTORICAL_ROOT = REPOSITORY / "third_party/skillsbench"


def digest_file(path: Path, git_blob: bool = False) -> str:
    digest = hashlib.sha1() if git_blob else hashlib.sha256()
    if git_blob:
        digest.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def strict_json(text: str) -> object:
    def reject_constant(value: str):
        raise ValueError(f"Non-finite JSON number: {value}")

    return json.loads(text, parse_constant=reject_constant)


def scoped_path(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or "\\" in relative:
        raise ValueError("Unsafe source path")
    destination = root / relative
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError("Source path escapes its root")
    return destination


def selected_path(relative: str) -> bool:
    return any(relative.startswith(CONFIG_PREFIX + config + "/") for config in CONFIGS)


def task_name(relative: str) -> str:
    return PurePosixPath(relative).parents[1].name.rsplit("__", 1)[0]


def historical_manifest(source_root: Path) -> list[dict]:
    rows = strict_json((source_root / "download_manifest.json").read_text())
    return [{"path": name, "expected_size": size, "task_id": task_name(name)}
            for name, size in rows if selected_path(name) and name.endswith("/llm_trajectory.jsonl")]


def inventory(root: Path, source_root: Path) -> dict:
    entries = historical_manifest(source_root)
    for entry in entries:
        source = scoped_path(source_root, entry["path"])
        restored = scoped_path(root / "data/raw/skillsbench", entry["path"])
        entry["original_present"] = source.is_file()
        entry["restored_present"] = restored.is_file()
        entry["metadata_present"] = [name for name in ("config.json", "result.json")
                                     if (source.parent.parent / name).is_file()]
    result = {
        "status": "historical_manifest_only_not_frozen_dataset",
        "dataset": DATASET,
        "source_manifest": str(source_root / "download_manifest.json"),
        "source_manifest_sha256": digest_file(source_root / "download_manifest.json"),
        "revision": None,
        "historical_file_entries": len(entries),
        "historical_task_names": len({entry["task_id"] for entry in entries}),
        "historical_expected_bytes": sum(entry["expected_size"] for entry in entries),
        "original_files_present": sum(entry["original_present"] for entry in entries),
        "restored_files_present": sum(entry["restored_present"] for entry in entries),
        "ready_for_gpu": False,
        "files": entries,
    }
    save_json(root / "data/historical_source_manifest.json", result)
    return result


def get_response(url: str, proxy: str | None, stream: bool = False):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, proxies=proxies, timeout=(8, 60), stream=stream,
                                    headers={"User-Agent": "agentkv-eviction-data/1.0"})
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            last_error = type(error).__name__
            if getattr(error, "response", None) is not None:
                error.response.close()
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError(f"Download failed ({last_error}); no credentials or response body logged")


def source_lock(root: Path, proxy: str | None, revision: str,
                endpoint: str = "https://huggingface.co") -> dict:
    lock_path = root / "data/source_lock.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        if lock["dataset"] != DATASET or (revision != "main" and revision != lock["revision"]):
            raise ValueError("Existing source lock differs; use a new output directory")
        return lock
    url = f"{endpoint}/api/datasets/{DATASET}/revision/{quote(revision, safe='')}?blobs=true"
    with get_response(url, proxy) as response:
        metadata = response.json()
    resolved = metadata.get("sha", "")
    if len(resolved) != 40 or any(character not in "0123456789abcdef" for character in resolved):
        raise ValueError("Dataset revision is not an immutable commit")
    siblings = {entry["rfilename"]: entry for entry in metadata.get("siblings", [])
                if entry["rfilename"] == "README.md"}
    for config in CONFIGS:
        directory = CONFIG_PREFIX + config
        url = f"{endpoint}/api/datasets/{DATASET}/tree/{resolved}/{quote(directory, safe='/')}?recursive=true&limit=1000"
        seen_pages = set()
        while url:
            if url in seen_pages:
                raise ValueError("Repeated dataset tree pagination cursor")
            seen_pages.add(url)
            with get_response(url, proxy) as response:
                page = response.json()
                next_url = response.links.get("next", {}).get("url")
            if not isinstance(page, list):
                raise ValueError("Expected dataset tree listing")
            for entry in page:
                if entry.get("type") != "file":
                    continue
                name = entry["path"]
                if not name.startswith(directory + "/"):
                    raise ValueError("Dataset tree entry outside selected directory")
                siblings[name] = {**entry, "rfilename": name, "blobId": entry.get("oid")}
            if next_url:
                parsed = urlparse(next_url)
                if parsed.hostname not in {"huggingface.co", "hf-mirror.com"} or not parsed.path.startswith(
                    f"/api/datasets/{DATASET}/tree/{resolved}/"
                ):
                    raise ValueError("Unexpected dataset pagination destination")
                url = endpoint + parsed.path + ("?" + parsed.query if parsed.query else "")
            else:
                url = None
    traces = sorted(name for name in siblings if selected_path(name) and name.endswith("/llm_trajectory.jsonl"))
    if not traces:
        raise ValueError("No selected traces at this revision")
    names = set(traces)
    for name in traces:
        trial = PurePosixPath(name).parents[1]
        names.update(str(trial / kind) for kind in ("config.json", "result.json", "timing.json")
                     if str(trial / kind) in siblings)
    names.update(CONFIG_PREFIX + config + "/metadata.yaml" for config in CONFIGS
                 if CONFIG_PREFIX + config + "/metadata.yaml" in siblings)
    if "README.md" in siblings:
        names.add("README.md")
    files = []
    for name in sorted(names):
        source = siblings[name]
        lfs = source.get("lfs") or {}
        checksum = lfs.get("sha256") or lfs.get("oid")
        size = source.get("size", lfs.get("size"))
        blob = source.get("blobId")
        if not isinstance(size, int) or size < 0 or not (checksum or blob):
            raise ValueError("Missing upstream file size/checksum; cannot verify download")
        files.append({"path": name, "expected_size": size, "sha256": checksum,
                      "git_blob_sha1": blob if not checksum else None})
    lock = {"dataset": DATASET, "revision": resolved, "configs": list(CONFIGS),
            "metadata_endpoint": endpoint,
            "license_declared": (metadata.get("cardData") or {}).get("license"),
            "trace_count": len(traces), "files": files}
    save_json(lock_path, lock)
    return lock


def verified_file(path: Path, entry: dict) -> bool:
    if not path.is_file() or path.stat().st_size != entry["expected_size"]:
        return False
    expected = entry.get("sha256") or entry.get("git_blob_sha1")
    if not expected:
        return False
    return digest_file(path, git_blob=not bool(entry.get("sha256"))) == expected


def download(root: Path, proxy: str | None, revision: str, workers: int,
             local_source: Path | None = None, endpoint: str = "https://huggingface.co") -> dict:
    lock = source_lock(root, proxy, revision, endpoint)
    raw_root = root / "data/raw/skillsbench"
    started = time.monotonic()
    print(json.dumps({"event": "download_plan", "revision": lock["revision"],
                      "endpoint": endpoint, "files": len(lock["files"]),
                      "bytes": sum(entry["expected_size"] for entry in lock["files"])},
                     ensure_ascii=False), flush=True)

    def restore(entry: dict) -> dict:
        target = scoped_path(raw_root, entry["path"])
        try:
            if not verified_file(target, entry):
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".part")
                local = scoped_path(local_source, entry["path"]) if local_source else None
                if local and verified_file(local, entry):
                    shutil.copyfile(local, temporary)
                else:
                    url = f"{endpoint}/datasets/{DATASET}/resolve/{lock['revision']}/{quote(entry['path'], safe='/')}"
                    with get_response(url, proxy, stream=True) as response, temporary.open("wb") as output:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            output.write(chunk)
                if not verified_file(temporary, entry):
                    raise ValueError("Downloaded file checksum mismatch")
                temporary.replace(target)
            return {"path": entry["path"], "status": "verified", "sha256": digest_file(target)}
        except (OSError, ValueError, RuntimeError, requests.RequestException) as error:
            return {"path": entry["path"], "status": "failed", "error_type": type(error).__name__}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(restore, entry) for entry in lock["files"]]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            progress = {"event": "download_progress", "revision": lock["revision"],
                        "endpoint": endpoint, "completed": len(results), "total": len(futures),
                        "verified": sum(entry["status"] == "verified" for entry in results),
                        "failed": sum(entry["status"] == "failed" for entry in results),
                        "elapsed_seconds": round(time.monotonic() - started, 1)}
            save_json(root / "results/audit/download_progress.json", progress)
            if len(results) % 10 == 0 or len(results) == len(futures):
                print(json.dumps(progress, ensure_ascii=False), flush=True)
    results.sort(key=lambda entry: entry["path"])
    result = {"revision": lock["revision"], "endpoint": endpoint, "files": results,
              "verified": sum(entry["status"] == "verified" for entry in results),
              "failed": sum(entry["status"] == "failed" for entry in results)}
    save_json(root / "results/audit/download_status.json", result)
    return result


def parse_timestamp(value: object) -> tuple[datetime.datetime | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, None
    return parsed, "offset_aware" if parsed.utcoffset() is not None else "naive_clock_unverified"


def interval_seconds(end: object, start: object) -> float | None:
    previous, previous_basis = parse_timestamp(end)
    current, current_basis = parse_timestamp(start)
    if previous is None or current is None or previous_basis != current_basis:
        return None
    return (current - previous).total_seconds()


def audit_trace(path: Path, relative: str) -> tuple[dict, list[dict]]:
    issues = collections.Counter()
    records = []
    previous_end = None
    with path.open() as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = strict_json(line)
                if not isinstance(row, dict):
                    raise ValueError("Expected object")
            except (json.JSONDecodeError, ValueError):
                issues["malformed_json_line"] += 1
                previous_end = None
                continue
            request = row.get("request") if isinstance(row.get("request"), dict) else {}
            response = row.get("response") if isinstance(row.get("response"), dict) else {}
            body = request.get("body")
            response_body = response.get("body")
            usage = response_body.get("usage") if isinstance(response_body, dict) else None
            completion = usage.get("completion_tokens") if isinstance(usage, dict) else None
            messages = body.get("messages") if isinstance(body, dict) else None
            if isinstance(body, dict) and body.get("model") not in ("deepseek/deepseek-v4-flash", "deepseek-v4-flash"):
                issues["request_model_unverified"] += 1
            if isinstance(body, dict) and "tools" in body and not isinstance(body["tools"], list):
                issues["invalid_tools"] += 1
            if not isinstance(messages, list) or not messages or any(
                not isinstance(message, dict) or message.get("role") not in
                {"system", "developer", "user", "assistant", "tool", "function"} for message in messages
            ):
                issues["invalid_messages"] += 1
            if isinstance(messages, list):
                for message in messages:
                    if not isinstance(message, dict):
                        continue
                    content = message.get("content")
                    if isinstance(content, list) and any(not isinstance(part, dict) or part.get("type") != "text" for part in content):
                        issues["nontext_content_requires_validation"] += 1
            if not isinstance(completion, int) or isinstance(completion, bool) or completion <= 0:
                issues["missing_or_nonpositive_output_tokens"] += 1
                completion = None
            if not isinstance(response_body, dict) or response_body.get("error"):
                issues["invalid_or_error_response"] += 1
            choices = response_body.get("choices") if isinstance(response_body, dict) else None
            if not isinstance(choices, list) or not choices or any(
                not isinstance(choice, dict) or not isinstance(choice.get("message"), dict) for choice in choices
            ):
                issues["incomplete_response_choices"] += 1
            response_status = response.get("status_code")
            if isinstance(response_status, int) and response_status >= 400:
                issues["http_error_response"] += 1
            start = request.get("timestamp")
            end = response.get("timestamp")
            if parse_timestamp(start)[0] is None:
                issues["missing_request_time"] += 1
            if parse_timestamp(end)[0] is None:
                issues["missing_response_time"] += 1
            if parse_timestamp(start)[1] == "naive_clock_unverified" or parse_timestamp(end)[1] == "naive_clock_unverified":
                issues["naive_clock_unverified"] += 1
            request_elapsed = interval_seconds(start, end)
            if request_elapsed is None:
                issues["unknown_request_elapsed"] += 1
            elif request_elapsed < 0:
                issues["negative_request_elapsed"] += 1
            wait = interval_seconds(previous_end, start) if records else None
            if records and wait is None:
                issues["unknown_inter_request_gap"] += 1
            elif wait is not None and wait < 0:
                issues["overlap_or_clock_error"] += 1
            records.append({
                "source_line": line_number, "turn_index": len(records),
                "request_body": body, "response_body": response_body,
                "request_timestamp": start, "response_timestamp": end,
                "duration_ms_raw": row.get("duration_ms"),
                "completion_tokens_source_usage": completion,
                "wait_after_previous_response_candidate_seconds": wait,
                "time_semantics_verified": False,
            })
            previous_end = end
    if not records:
        issues["empty_trace"] += 1
    result_path = path.parent.parent / "result.json"
    metadata = strict_json(result_path.read_text()) if result_path.is_file() else {}
    if not isinstance(metadata, dict):
        metadata = {}
    if metadata.get("agent") != "openhands" or metadata.get("model") != "deepseek/deepseek-v4-flash":
        issues["agent_model_metadata_unverified"] += 1
    partial = metadata.get("partial_trajectory")
    if partial is None:
        trajectory_summary = metadata.get("trajectory_summary")
        partial = trajectory_summary.get("partial_trajectory") if isinstance(trajectory_summary, dict) else None
    rewards = metadata.get("rewards")
    summary = {
        "source_path": relative, "source_sha256": digest_file(path),
        "task_id": task_name(relative), "requests": len(records),
        "observed_partial_trajectory": partial,
        "task_error_recorded": bool(metadata.get("error")),
        "reward": rewards.get("reward") if isinstance(rewards, dict) else None,
        "request_sequence_sha256": canonical_digest([record["request_body"] for record in records]),
        "canonical_trace_sha256": canonical_digest(records),
        "issues": dict(issues), "structural_candidate": not issues,
        "ready_for_gpu": False,
    }
    return summary, records


def split_tasks(sessions: list[dict], seed: int = 42) -> dict:
    parents = {session["task_id"]: session["task_id"] for session in sessions}

    def representative(task: str) -> str:
        while parents[task] != task:
            task = parents[task]
        return task

    fingerprints = {}
    for session in sessions:
        task = session["task_id"]
        signature = session["request_sequence_sha256"]
        if signature in fingerprints:
            roots = sorted((representative(task), representative(fingerprints[signature])))
            parents[roots[1]] = roots[0]
        fingerprints[signature] = task
    groups = sorted({representative(task) for task in parents})
    random.Random(seed).shuffle(groups)
    calibration_count = max(1, round(len(groups) * 0.2)) if len(groups) > 1 else 0
    calibration = set(groups[:calibration_count])
    assignments = {task: "calibration" if representative(task) in calibration else "evaluation"
                   for task in sorted(parents)}
    return {"seed": seed, "unit": "task_union_identical_request_sequence", "assignments": assignments,
            "groups": len(groups), "calibration_groups": len(calibration),
            "status": "candidate_partition_not_serving_workload"}


def audit(root: Path, source_root: Path) -> dict:
    lock_path = root / "data/source_lock.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else None
    entries = lock["files"] if lock else historical_manifest(source_root)
    entries = [entry for entry in entries if entry["path"].endswith("/llm_trajectory.jsonl")]
    raw_root = root / "data/raw/skillsbench"
    sessions = []
    split_population = []
    filters = []
    seen = {}
    for entry in entries:
        relative = entry["path"]
        source = scoped_path(raw_root, relative)
        if not source.is_file():
            filters.append({"path": relative, "reason": "raw_file_missing"})
            continue
        if lock and not verified_file(source, entry):
            filters.append({"path": relative, "reason": "upstream_checksum_mismatch"})
            continue
        try:
            summary, records = audit_trace(source, relative)
        except (OSError, UnicodeError, ValueError, TypeError) as error:
            filters.append({"path": relative, "reason": "unreadable_trace_or_metadata",
                            "error_type": type(error).__name__})
            continue
        split_population.append(summary)
        signature = summary["canonical_trace_sha256"]
        if signature in seen:
            filters.append({"path": relative, "reason": "duplicate_canonical_trace",
                            "duplicate_of": seen[signature], "task_id": summary["task_id"]})
            continue
        seen[signature] = relative
        session_id = "openhands_" + summary["source_sha256"]
        summary["session_id"] = session_id
        normalized = root / "data/normalized" / f"{session_id}.jsonl.gz"
        normalized.parent.mkdir(parents=True, exist_ok=True)
        with normalized.with_suffix(".part").open("wb") as stream:
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as output:
                for record in records:
                    record["session_id"] = session_id
                    output.write((json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode())
        normalized.with_suffix(".part").replace(normalized)
        summary["normalized_path"] = str(normalized.relative_to(root))
        summary["normalized_sha256"] = digest_file(normalized)
        sessions.append(summary)
    save_json(root / "data/normalized/session_index.json", sessions)
    save_json(root / "data/normalized/task_split.json", split_tasks(split_population))
    save_json(root / "results/audit/filter_log.json", filters)
    filter_counts = dict(collections.Counter(item["reason"] for item in filters))
    status = "audited_not_serving_ready" if sessions else "blocked_no_parseable_traces"
    if filter_counts.get("raw_file_missing"):
        status = "blocked_missing_raw_data"
    remaining_gates = ["request_response_timestamp_semantics", "target_model_encoding_and_length_audit",
                       "server_input_token_equivalence", "calibration_and_frozen_arrival_schedule"]
    if not lock or not entries or any(filter_counts.get(reason) for reason in
                                     ("raw_file_missing", "upstream_checksum_mismatch")):
        remaining_gates.insert(0, "complete_pinned_source_restore")
    result = {
        "status": status,
        "revision": lock["revision"] if lock else None,
        "expected_raw_files": len(entries), "unique_parsed_sessions": len(sessions),
        "parsed_requests": sum(session["requests"] for session in sessions),
        "tasks": len({session["task_id"] for session in sessions}),
        "structural_candidates": sum(session["structural_candidate"] for session in sessions),
        "filter_counts": filter_counts,
        "issue_counts": dict(sum((collections.Counter(session["issues"]) for session in sessions), collections.Counter())),
        "ready_for_gpu": False,
        "remaining_gates": remaining_gates,
        "source_model_token_counts_are_not_target_service_measurements": True,
    }
    save_json(root / "results/audit/data_inventory.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("inventory", "download", "audit"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-root", type=Path, default=HISTORICAL_ROOT)
    parser.add_argument("--revision", default="main")
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--endpoint", choices=("https://huggingface.co", "https://hf-mirror.com"),
                        default="https://huggingface.co")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("workers must be between 1 and 16")
    if args.root.resolve() == args.source_root.resolve():
        parser.error("Output root must not replace the original source directory")
    if args.proxy and (urlparse(args.proxy).username or urlparse(args.proxy).password):
        parser.error("Do not place proxy credentials in command-line arguments")
    os.umask(0o077)
    try:
        if args.stage == "inventory":
            result = inventory(args.root, args.source_root)
        elif args.stage == "download":
            result = download(args.root, args.proxy, args.revision, args.workers, args.source_root, args.endpoint)
        else:
            result = audit(args.root, args.source_root)
    except (OSError, ValueError, RuntimeError, requests.RequestException) as error:
        result = {"status": "blocked", "stage": args.stage, "error_type": type(error).__name__,
                  "ready_for_gpu": False, "message": "Inspect connectivity/source schema; no workload has been frozen."}
        save_json(args.root / f"results/audit/{args.stage}_status.json", result)
        print(json.dumps(result, ensure_ascii=False))
        return 1
    print(json.dumps({key: value for key, value in result.items() if key not in {"files"}}, ensure_ascii=False))
    if args.stage == "download" and result["failed"]:
        return 1
    if args.stage == "audit" and (not result["unique_parsed_sessions"] or result["filter_counts"].get("raw_file_missing")):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
