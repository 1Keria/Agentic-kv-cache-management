#!/usr/bin/env python3
"""Replay immutable token inputs without labels, partitions or tool execution."""

import argparse
import asyncio
import datetime
import json
import os
from pathlib import Path
import time

import aiohttp

from build_workload import effective_gap_seconds, read_rows, timing_scale
from prepare_data import ROOT, canonical_digest, digest_file, save_json


def validate_workload(workload: dict) -> list[tuple[dict, list[dict]]]:
    if workload.get("frozen") is not True:
        raise ValueError("Workload must be explicitly frozen")
    purpose = workload.get("purpose")
    if purpose not in {"smoke", "calibration", "formal"}:
        raise ValueError("Unknown purpose")
    if purpose == "formal" and workload.get("formal_protocol_accepted") is not True:
        raise ValueError("Formal protocol has not been accepted/frozen")
    if purpose != "smoke" and (workload.get("output_token_cap") is not None or not workload.get("complete_sessions")):
        raise ValueError("Partial sessions/output caps are restricted to smoke tests")
    timing_scale(workload)
    seen = set()
    loaded = []
    for entry in workload["sessions"]:
        if entry["session_id"] in seen:
            raise ValueError("Duplicate session")
        seen.add(entry["session_id"])
        rows = read_rows(entry)
        count = entry["replay_requests"]
        if not 0 < count <= len(rows) or (purpose != "smoke" and count != len(rows)):
            raise ValueError("Invalid session truncation")
        offset = entry["start_offset_seconds"]
        if not isinstance(offset, (int, float)) or not 0 <= offset < float("inf"):
            raise ValueError("Invalid session start")
        split = "evaluation" if purpose == "formal" else "calibration"
        if entry["split"] != split:
            raise ValueError("Unexpected split")
        loaded.append((entry, rows[:count]))
    if sum(len(rows) for _, rows in loaded) != workload["requests"]:
        raise ValueError("Workload count mismatch")
    return loaded


def generation_payload(row: dict, workload: dict) -> dict:
    target = row["output_tokens"]
    cap = workload.get("output_token_cap")
    if cap is not None:
        if workload["purpose"] != "smoke" or type(cap) is not int or cap <= 0:
            raise ValueError("Invalid output cap")
        target = min(target, cap)
    return {"input_ids": row["input_ids"], "stream": True,
            "sampling_params": {"temperature": workload["temperature"],
                                "sampling_seed": workload["sampling_seed"],
                                "max_new_tokens": target, "ignore_eos": workload["ignore_eos"]}}


def update_output(previous: list[int], chunk: dict) -> list[int]:
    if "error" in chunk:
        raise RuntimeError(str(chunk["error"]))
    current = chunk.get("output_ids", previous)
    if not isinstance(current, list) or any(type(token) is not int for token in current):
        raise ValueError("Missing/invalid output token IDs")
    if current[:len(previous)] != previous:
        raise ValueError("Expected cumulative, prefix-consistent output IDs")
    return current


async def sse_events(response):
    data = []
    async for raw in response.content:
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line and data:
            yield "\n".join(data)
            data = []
    if data:
        yield "\n".join(data)


def append_record(stream, record: dict, durable: bool = False) -> None:
    stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    stream.flush()
    if durable:
        os.fsync(stream.fileno())


async def replay(base_url: str, workload: dict, destination: Path, request_timeout: float = 1800, context=None) -> dict:
    loaded = validate_workload(workload)
    destination.mkdir(parents=True, exist_ok=False)
    save_json(destination / "workload.json", workload)
    start = time.perf_counter()
    started_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    outcomes = []
    status = "running"
    error_text = None
    context = context or {"run_id": destination.name, "policy": "external_service_unverified", "phase": "smoke"}
    # Avoid reusing a server-side idle keep-alive socket after long waits.
    connector = aiohttp.TCPConnector(limit=0, force_close=True)
    timeout = aiohttp.ClientTimeout(total=request_timeout, sock_read=None)
    with (destination / "requests.jsonl").open("x") as requests, (destination / "events.jsonl").open("x") as events:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, read_bufsize=2 ** 22) as client:
            async def run_session(entry: dict, rows: list[dict]) -> None:
                previous_completion = None
                previous_row = None
                previous_output = []
                for row in rows:
                    source_gap = row["wait_after_previous_response_seconds"]
                    gap = effective_gap_seconds(row, workload)
                    due = start + entry["start_offset_seconds"] if previous_completion is None else previous_completion + gap
                    await asyncio.sleep(max(0, due - time.perf_counter()))
                    payload = generation_payload(row, workload)
                    submitted = time.perf_counter()
                    record = {**context, "session_id": row["session_id"], "task_id": row["task_id"],
                              "turn_index": row["turn_index"], "input_ids_sha256": row["input_ids_sha256"],
                              "prompt_tokens": row["prompt_tokens"], "source_output_tokens": row["output_tokens"],
                              "expected_output_tokens": payload["sampling_params"]["max_new_tokens"],
                              "scheduled_seconds": due - start, "submitted_seconds": submitted - start,
                              "schedule_lag_seconds": submitted - due,
                              "source_gap_seconds": source_gap,
                              "effective_gap_seconds": gap,
                              "timing_scale": timing_scale(workload),
                              "actual_gap_seconds": None if previous_completion is None else submitted - previous_completion,
                              "first_token_seconds": None, "status": "running"}
                    if previous_row is not None:
                        continuation = previous_row["input_ids"] + previous_output
                        prefix = 0
                        for actual, historical in zip(continuation, row["input_ids"]):
                            if actual != historical:
                                break
                            prefix += 1
                        record["previous_local_continuation_lcp_tokens"] = prefix
                        record["previous_local_output_fully_matches_next_input"] = prefix == len(continuation)
                        record["previous_input_lcp_tokens"] = row.get("same_session_previous_input_lcp_tokens")
                    append_record(events, {**record, "event": "submitted"})
                    output = []
                    meta = {}
                    done = False
                    try:
                        async with client.post(base_url + "/generate", json=payload) as response:
                            response.raise_for_status()
                            async for event in sse_events(response):
                                observed = time.perf_counter()
                                if event == "[DONE]":
                                    done = True
                                    break
                                chunk = json.loads(event)
                                current = update_output(output, chunk)
                                delta = current[len(output):]
                                if delta:
                                    if record["first_token_seconds"] is None:
                                        record["first_token_seconds"] = observed - start
                                    append_record(events, {"event": "tokens", "session_id": row["session_id"],
                                                           "turn_index": row["turn_index"],
                                                           "observed_seconds": observed - start, "delta_ids": delta})
                                output = current
                                meta.update(chunk.get("meta_info", {}))
                            completed = time.perf_counter()
                        if not done or not isinstance(meta.get("finish_reason"), dict) or meta["finish_reason"].get("type") != "length":
                            raise ValueError("Stream ended without final completion evidence")
                        if len(output) != record["expected_output_tokens"] or meta.get("completion_tokens") != len(output):
                            raise ValueError("Actual output length differs from frozen target")
                        if meta.get("prompt_tokens") != row["prompt_tokens"]:
                            raise ValueError("Actual prompt length differs from encoded input")
                        if record["first_token_seconds"] is None:
                            raise ValueError("No generated token observed")
                        record["status"] = "completed"
                        previous_completion = completed
                        previous_row = row
                        previous_output = output
                    except BaseException as error:
                        completed = time.perf_counter()
                        record["status"] = "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
                        record["error"] = repr(error)
                        raise
                    finally:
                        record.update({"completed_seconds": completed - start, "latency_seconds": completed - submitted,
                                       "ttft_seconds": None if record["first_token_seconds"] is None else record["first_token_seconds"] - (submitted - start),
                                       "output_ids": output, "output_ids_sha256": canonical_digest(output),
                                       "actual_output_tokens": len(output), "meta_info": meta,
                                       "cached_tokens": meta.get("cached_tokens")})
                        append_record(requests, record, durable=True)
                        outcomes.append({key: value for key, value in record.items() if key not in {"output_ids", "meta_info"}})

            tasks = [asyncio.create_task(run_session(entry, rows)) for entry, rows in loaded]
            try:
                await asyncio.gather(*tasks)
                status = "completed"
            except BaseException as error:
                status = "interrupted" if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)) else "failed"
                error_text = repr(error)
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            finally:
                summary = {"status": status, "error": error_text, "purpose": workload["purpose"],
                           "started_at_utc": started_utc, "elapsed_seconds": time.perf_counter() - start,
                           "expected_requests": workload["requests"], "recorded_requests": len(outcomes),
                           "completed_requests": sum(item["status"] == "completed" for item in outcomes),
                           "workload_sha256": canonical_digest(workload),
                           "request_log_sha256": digest_file(destination / "requests.jsonl"),
                           "timing_transform": workload.get("timing_transform"),
                           "historical_template_reproduced": False,
                           "generation_consistency_checks": [item for item in outcomes if "previous_local_output_fully_matches_next_input" in item]}
                save_json(destination / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:31080")
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    destination = args.output.resolve()
    if not destination.is_relative_to(ROOT):
        raise ValueError("Results must stay inside this experiment")
    result = asyncio.run(replay(args.base_url.rstrip("/"), json.loads(args.workload.read_text()), destination))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
