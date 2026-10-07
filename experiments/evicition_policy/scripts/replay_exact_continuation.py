#!/usr/bin/env python3
"""Run a controlled Agent-only trace with exact token continuation."""

from __future__ import annotations

from array import array
import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import time

import aiohttp


ROOT = Path(__file__).resolve().parents[1]
PAGE_SIZE = 256


def digest_json(value) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def prefix_digest(tokens: list[int], extra_key=None) -> str:
    values = array("q", (int(token) for token in tokens))
    digest = hashlib.sha256()
    digest.update(b"agentkv-prefix-v1\0")
    digest.update(repr(extra_key).encode("utf-8", "surrogatepass"))
    digest.update(b"\0")
    digest.update(values.tobytes())
    return digest.hexdigest()


def token_block(seed: int, length: int, vocab_size: int) -> list[int]:
    # Stay away from low special-token IDs and generate deterministic content.
    usable = max(4096, vocab_size - 4096)
    x = seed & 0x7FFFFFFF
    output = []
    for _ in range(length):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        output.append(2048 + x % usable)
    return output


def build_plan(vocab_size: int) -> dict:
    sessions = {
        "chain_a": {"turns": 8, "behavior": "strict_append"},
        "chain_b": {"turns": 4, "behavior": "stops_early"},
        "chain_c": {"turns": 8, "behavior": "strict_append"},
        "chain_d": {"turns": 7, "behavior": "fork_after_turn_3", "branch_from_turn": 1},
    }
    common = token_block(7001, 512, vocab_size)
    initial = {
        name: common + token_block(8100 + index * 997, 3584, vocab_size)
        for index, name in enumerate(sessions)
    }
    schedule = []
    for turn in range(max(spec["turns"] for spec in sessions.values())):
        for name, spec in sessions.items():
            if turn < spec["turns"]:
                schedule.append({"session_id": name, "turn_index": turn})
    return {
        "schema": "agentkv_exact_continuation_plan_v1",
        "page_size": PAGE_SIZE,
        "common_prefix_tokens": len(common),
        "initial_tokens": 4096,
        "generated_tokens_per_turn": 32,
        "tool_tokens_per_turn": 224,
        "sessions": sessions,
        "initial_input_ids": initial,
        "schedule": schedule,
    }


def load_frozen_trace(path: Path, plan: dict) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(rows) != len(plan["schedule"]):
        raise ValueError(f"Frozen trace request count mismatch: {len(rows)}")
    history = {name: {} for name in plan["sessions"]}
    previous = {name: None for name in plan["sessions"]}
    required = {"request_seq", "session_id", "turn_index", "lifecycle_state", "input_ids", "output_ids", "tool_ids"}
    for request_seq, (scheduled, row) in enumerate(zip(plan["schedule"], rows), start=1):
        missing = required - set(row)
        if missing:
            raise ValueError(f"Frozen trace row {request_seq} is missing {sorted(missing)}")
        if row["request_seq"] != request_seq:
            raise ValueError(f"Frozen trace sequence mismatch at row {request_seq}")
        if (row["session_id"], row["turn_index"]) != (scheduled["session_id"], scheduled["turn_index"]):
            raise ValueError(f"Frozen trace schedule mismatch at row {request_seq}")
        input_ids = row["input_ids"]
        output_ids = row["output_ids"]
        tool_ids = row["tool_ids"]
        if any(type(token) is not int for values in (input_ids, output_ids, tool_ids) for token in values):
            raise ValueError(f"Frozen trace contains a non-integer token at row {request_seq}")
        if len(input_ids) % PAGE_SIZE or len(output_ids) != 32 or len(tool_ids) != 224:
            raise ValueError(f"Frozen trace token lengths are invalid at row {request_seq}")
        session_id = row["session_id"]
        turn = row["turn_index"]
        lifecycle = row["lifecycle_state"]
        if turn == 0:
            if input_ids != plan["initial_input_ids"][session_id] or lifecycle != "first":
                raise ValueError(f"Frozen trace initial request mismatch at row {request_seq}")
        elif lifecycle == "continuation":
            prior = previous[session_id]
            expected = prior["input_ids"] + prior["output_ids"] + prior["tool_ids"]
            if input_ids != expected:
                raise ValueError(f"Frozen trace continuation mismatch at row {request_seq}")
        elif lifecycle == "branch":
            branch_turn = row.get("branch_from_turn")
            source = history[session_id].get(branch_turn)
            if source is None:
                raise ValueError(f"Frozen trace branch source is missing at row {request_seq}")
            prefix = source["input_ids"] + source["output_ids"]
            if input_ids[: len(prefix)] != prefix or len(input_ids) != len(prefix) + 224:
                raise ValueError(f"Frozen trace branch mismatch at row {request_seq}")
        else:
            raise ValueError(f"Frozen trace lifecycle mismatch at row {request_seq}")
        canonical = {
            "request_seq": request_seq,
            "session_id": session_id,
            "turn_index": turn,
            "lifecycle_state": lifecycle,
            "branch_from_turn": row.get("branch_from_turn"),
            "input_ids": list(input_ids),
            "output_ids": list(output_ids),
            "tool_ids": list(tool_ids),
        }
        history[session_id][turn] = canonical
        previous[session_id] = canonical
    return rows


async def sse_events(response):
    pending = []
    async for raw in response.content:
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("data:"):
            pending.append(line[5:].lstrip())
        elif not line and pending:
            yield "\n".join(pending)
            pending = []
    if pending:
        yield "\n".join(pending)


def update_output(previous: list[int], chunk: dict) -> list[int]:
    if "error" in chunk:
        raise RuntimeError(str(chunk["error"]))
    current = chunk.get("output_ids", previous)
    if not isinstance(current, list) or any(type(token) is not int for token in current):
        raise ValueError("Missing output_ids")
    if current[: len(previous)] != previous:
        raise ValueError("Output stream is not cumulative")
    return current


async def generate(client: aiohttp.ClientSession, base_url: str, payload: dict) -> tuple[list[int], dict, float, float]:
    start = time.perf_counter()
    first_token = None
    output = []
    meta = {}
    done = False
    async with client.post(base_url + "/generate", json=payload) as response:
        response.raise_for_status()
        async for event in sse_events(response):
            if event == "[DONE]":
                done = True
                break
            chunk = json.loads(event)
            updated = update_output(output, chunk)
            if first_token is None and len(updated) > len(output):
                first_token = time.perf_counter()
            output = updated
            meta.update(chunk.get("meta_info", {}))
    end = time.perf_counter()
    if not done:
        raise RuntimeError("Streaming response ended without [DONE]")
    if first_token is None:
        raise RuntimeError("No output token observed")
    return output, meta, first_token - start, end - start


async def replay(
    base_url: str,
    destination: Path,
    vocab_size: int,
    run_label: str,
    frozen_trace: Path | None = None,
) -> dict:
    plan = build_plan(vocab_size)
    frozen_rows = None if frozen_trace is None else load_frozen_trace(frozen_trace, plan)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    state = {
        name: {
            "input": list(tokens),
            "history": {},
            "previous_input": None,
            "previous_output": None,
        }
        for name, tokens in plan["initial_input_ids"].items()
    }
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    records = []
    connector = aiohttp.TCPConnector(limit=1, force_close=True)
    timeout = aiohttp.ClientTimeout(total=1800, sock_read=None)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout, read_bufsize=2**22) as client:
        for request_seq, scheduled in enumerate(plan["schedule"], start=1):
            session_id = scheduled["session_id"]
            turn = scheduled["turn_index"]
            session = state[session_id]
            if frozen_rows is not None:
                frozen = frozen_rows[request_seq - 1]
                lifecycle = frozen["lifecycle_state"]
                branch_from_turn = frozen.get("branch_from_turn")
                input_ids = list(frozen["input_ids"])
                tool_ids = list(frozen["tool_ids"])
                continuation_asserted = turn > 0 and lifecycle == "continuation"
            else:
                lifecycle = "first" if turn == 0 else "continuation"
                branch_from_turn = None
                if session_id == "chain_d" and turn == 4:
                    branch_from_turn = plan["sessions"][session_id]["branch_from_turn"]
                    source = session["history"][branch_from_turn]
                    alternate_tool = token_block(99000 + turn, 224, vocab_size)
                    session["input"] = source["input"] + source["output"] + alternate_tool
                    lifecycle = "branch"
                input_ids = list(session["input"])
                continuation_asserted = False
                if turn > 0 and lifecycle == "continuation":
                    expected = session["previous_input"] + session["previous_output"] + session["previous_tool"]
                    if input_ids != expected:
                        raise AssertionError(f"Exact continuation failed for {session_id} turn {turn}")
                    continuation_asserted = True
            if len(input_ids) % PAGE_SIZE:
                raise AssertionError(f"Input is not page aligned: {len(input_ids)}")
            rid = f"agentkv-diag-{run_label}-{request_seq:04d}-{session_id}-t{turn}"
            payload = {
                "input_ids": input_ids,
                "rid": rid,
                "stream": True,
                "sampling_params": {
                    "temperature": 0.0,
                    "sampling_seed": 420000 + request_seq,
                    "max_new_tokens": 32,
                    "ignore_eos": True,
                },
            }
            output_ids, meta, ttft, latency = await generate(client, base_url, payload)
            if len(output_ids) != 32:
                raise AssertionError(f"Expected 32 generated tokens, got {len(output_ids)}")
            if frozen_rows is None:
                tool_ids = token_block(50000 + request_seq * 131, 224, vocab_size)
            page_prefixes = [
                {
                    "path_tokens": end,
                    "stable_prefix_digest": prefix_digest(input_ids[:end]),
                }
                for end in range(PAGE_SIZE, len(input_ids) + 1, PAGE_SIZE)
            ]
            record = {
                "schema": "agentkv_exact_continuation_request_v1",
                "run_label": run_label,
                "request_seq": request_seq,
                "request_id": rid,
                "session_id": session_id,
                "turn_index": turn,
                "lifecycle_state": lifecycle,
                "branch_from_turn": branch_from_turn,
                "continuation_asserted": continuation_asserted,
                "input_ids": input_ids,
                "input_tokens": len(input_ids),
                "input_ids_sha256": digest_json(input_ids),
                "page_prefixes": page_prefixes,
                "output_ids": output_ids,
                "output_tokens": len(output_ids),
                "output_ids_sha256": digest_json(output_ids),
                "tool_ids": tool_ids,
                "tool_tokens": len(tool_ids),
                "next_growth_tokens": len(output_ids) + len(tool_ids),
                "ttft_seconds": ttft,
                "latency_seconds": latency,
                "cached_tokens": meta.get("cached_tokens"),
                "prompt_tokens_reported": meta.get("prompt_tokens"),
                "completion_tokens_reported": meta.get("completion_tokens"),
                "finish_reason": meta.get("finish_reason"),
                "trace_mode": "captured_fixed" if frozen_rows is not None else "closed_loop",
            }
            if frozen_rows is not None:
                record["trace_source_output_ids_sha256"] = digest_json(frozen_rows[request_seq - 1]["output_ids"])
            if record["prompt_tokens_reported"] != len(input_ids):
                raise AssertionError(f"Server prompt length mismatch: {record}")
            records.append(record)
            with (destination / "requests.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            if frozen_rows is None:
                session["history"][turn] = {"input": input_ids, "output": output_ids, "tool": tool_ids}
                session["previous_input"] = input_ids
                session["previous_output"] = output_ids
                session["previous_tool"] = tool_ids
                session["input"] = input_ids + output_ids + tool_ids
    summary = {
        "schema": "agentkv_exact_continuation_summary_v1",
        "status": "completed",
        "run_label": run_label,
        "started_at_utc": started_at,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "requests": len(records),
        "strict_continuations": sum(row["continuation_asserted"] for row in records),
        "branches": sum(row["lifecycle_state"] == "branch" for row in records),
        "total_input_tokens": sum(row["input_tokens"] for row in records),
        "total_output_tokens": sum(row["output_tokens"] for row in records),
        "cached_tokens": sum(int(row["cached_tokens"] or 0) for row in records),
        "mean_ttft_seconds": sum(row["ttft_seconds"] for row in records) / len(records),
        "mean_latency_seconds": sum(row["latency_seconds"] for row in records) / len(records),
        "plan_sha256": digest_json(plan),
        "requests_sha256": hashlib.sha256((destination / "requests.jsonl").read_bytes()).hexdigest(),
        "trace_mode": "captured_fixed" if frozen_rows is not None else "closed_loop",
        "frozen_trace_sha256": None if frozen_trace is None else hashlib.sha256(frozen_trace.read_bytes()).hexdigest(),
        "input_trace_sha256": digest_json([row["input_ids_sha256"] for row in records]),
    }
    (destination / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:31080")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vocab-size", type=int, default=129280)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--frozen-trace", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    destination = args.output.resolve()
    if not destination.is_relative_to(ROOT):
        raise ValueError("Output must stay inside the experiment directory")
    frozen_trace = None if args.frozen_trace is None else args.frozen_trace.resolve()
    result = asyncio.run(replay(args.base_url.rstrip("/"), destination, args.vocab_size, args.run_label, frozen_trace))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
