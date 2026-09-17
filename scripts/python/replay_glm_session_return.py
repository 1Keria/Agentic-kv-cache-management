#!/usr/bin/env python3
"""Compressed GLM replay for session-return native-field collection.

Reads splits/small (or full) train→val→test in arrival order, loads request
bodies from the original GLM jsonl, drops idle gaps, and caps generation to the
logged completion length. Labels stay on the split rows; do not use replay
wall-clock as τ.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = (
    REPO_ROOT / "third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl"
)
DEFAULT_SPLIT_DIR = REPO_ROOT / "experiments/session_return/splits/small"
DEFAULT_OUT_DIR = REPO_ROOT / "experiments/session_return/replay_small"

CLIENT_REQUEST_KEYS = (
    "messages",
    "input_ids",
    "model",
    "tools",
    "tool_choice",
    "parallel_tool_calls",
    "response_format",
    "reasoning_effort",
    "task",
    "user",
    "max_tokens",
    "max_completion_tokens",
    "min_tokens",
    "n",
    "stop",
    "stop_token_ids",
    "stop_regex",
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "frequency_penalty",
    "presence_penalty",
    "repetition_penalty",
    "seed",
    "ignore_eos",
    "no_stop_trim",
    "continue_final_message",
    "stream",
    "extra_key",
    "cache_salt",
    "lora_path",
    "priority",
    "session_params",
    "max_dynamic_patch",
    "min_dynamic_patch",
    "use_audio_in_video",
)


def load_json_maybe(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role") or "user"
        item: dict[str, Any] = {"role": role}
        content = msg.get("content")
        item["content"] = "" if content is None else content
        if role == "assistant" and msg.get("tool_calls"):
            tcs = []
            for tc in msg["tool_calls"]:
                fn = tc.get("function") or {}
                tcs.append(
                    {
                        "id": tc.get("id") or f"call_{len(tcs)}",
                        "type": tc.get("type") or "function",
                        "function": {
                            "name": fn.get("name") or "unknown",
                            "arguments": fn.get("arguments") or "{}",
                        },
                    }
                )
            item["tool_calls"] = tcs
        if role == "tool":
            item["tool_call_id"] = msg.get("tool_call_id") or "missing_tool_call_id"
            if msg.get("name"):
                item["name"] = msg["name"]
        out.append(item)
    return out


def read_split_rows(split_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in ("train.jsonl", "val.jsonl", "test.jsonl"):
        path = split_dir / name
        if not path.exists():
            raise SystemExit(f"missing split file: {path}")
        with path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    rows.sort(key=lambda r: (r["start_s"], r["line_no"]))
    return rows


def read_original(dataset: Path, offset: int) -> dict[str, Any]:
    with dataset.open("rb") as f:
        f.seek(offset)
        row = json.loads(f.readline().decode("utf-8"))
    prompt = load_json_maybe(row["prompt_body"])
    response = load_json_maybe(row["response_body"])
    usage = response.get("usage") or {}
    return {
        "prompt_body": prompt,
        "completion_tokens": max(1, int(usage.get("completion_tokens") or 1)),
        "logged_usage": usage,
    }


def client_request_fields(prompt: dict[str, Any]) -> dict[str, Any]:
    return {k: prompt.get(k) for k in CLIENT_REQUEST_KEYS if k in prompt}


async def measure_chat(
    client: AsyncOpenAI,
    *,
    model: str,
    rid: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    client_max_tokens: Any,
    tools: list[dict[str, Any]] | None,
    temperature: float | None,
    top_p: float | None,
    reasoning_effort: str | None,
    timeout_s: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    first_token_at: float | None = None
    prompt_tokens = 0
    cached_tokens = 0
    completion_tokens = 0
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "timeout": timeout_s,
        "extra_body": {
            "rid": rid,
            "custom_params": {
                k: v
                for k, v in {
                    "sr_client_max_tokens": client_max_tokens,
                    "sr_tools_len": None if tools is None else len(tools),
                }.items()
                if v is not None
            },
        },
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if top_p is not None:
        kwargs["top_p"] = top_p
    if tools:
        kwargs["tools"] = tools
    if reasoning_effort:
        kwargs["extra_body"]["reasoning_effort"] = reasoning_effort

    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and (
                delta.content
                or getattr(delta, "tool_calls", None)
                or getattr(delta, "reasoning_content", None)
            ):
                if first_token_at is None:
                    first_token_at = time.perf_counter()
        if chunk.usage is not None:
            prompt_tokens = int(chunk.usage.prompt_tokens or 0)
            completion_tokens = int(chunk.usage.completion_tokens or 0)
            details = getattr(chunk.usage, "prompt_tokens_details", None)
            if details is not None:
                cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)

    ended = time.perf_counter()
    return {
        "replay_created_perf_s": started,
        "replay_finished_perf_s": ended,
        "replay_first_token_perf_s": first_token_at,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": completion_tokens,
        "status": "200",
    }


async def run(args: argparse.Namespace) -> int:
    rows = read_split_rows(args.split_dir)
    if args.max_events is not None:
        rows = rows[: args.max_events]
    if not rows:
        raise SystemExit("no split rows")

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.out_prefix or f"session_return_{int(time.time())}"
    path_jsonl = out_dir / f"{prefix}.client.jsonl"
    path_meta = out_dir / f"{prefix}.meta.json"

    model = args.model
    if not args.dry_run:
        import requests

        resp = requests.get(f"{args.base_url.rstrip('/')}/v1/models", timeout=30)
        resp.raise_for_status()
        model = model or resp.json()["data"][0]["id"]
    else:
        model = model or "dry-run"

    meta = {
        "mode": "session_return_compressed_native_dump",
        "base_url": args.base_url,
        "model": model,
        "dataset": str(args.dataset),
        "split_dir": str(args.split_dir),
        "n": len(rows),
        "max_inflight": args.max_inflight,
        "time_in_secs": args.time_in_secs,
        "first_start_time": rows[0]["start_time"],
        "last_start_time": rows[-1]["start_time"],
        "dump_join": "client.trace_id == server.rid",
        "label_note": "tau/delta come from split jsonl original start_time, not replay clock",
    }
    path_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    if args.dry_run:
        with path_jsonl.open("w") as fout:
            for row in rows[: args.dry_run_preview]:
                fout.write(json.dumps({"dry_run": True, **row}, ensure_ascii=False) + "\n")
        print(f"[dry-run] {len(rows)} events, preview {path_jsonl}", flush=True)
        return 0

    client = AsyncOpenAI(
        base_url=f"{args.base_url.rstrip('/')}/v1",
        api_key=args.api_key,
    )
    sem = asyncio.Semaphore(max(1, int(args.max_inflight)))
    stop_at = (
        time.perf_counter() + float(args.time_in_secs)
        if args.time_in_secs and args.time_in_secs > 0
        else None
    )
    fout = path_jsonl.open("w", encoding="utf-8")
    write_lock = asyncio.Lock()
    n_ok = 0
    n_err = 0
    n_skip = 0
    results_lock = asyncio.Lock()

    async def one(index: int, split_row: dict[str, Any]) -> None:
        nonlocal n_ok, n_err, n_skip
        if stop_at is not None and time.perf_counter() >= stop_at:
            async with results_lock:
                n_skip += 1
            return
        orig = await asyncio.to_thread(read_original, args.dataset, int(split_row["offset"]))
        prompt = orig["prompt_body"]
        max_tokens = max(1, int(orig["completion_tokens"]))
        messages = sanitize_messages(prompt.get("messages") or [])
        tools = prompt.get("tools") or None
        rec = {
            "schema": "session_return_client_v1",
            "index": index,
            "trace_id": split_row["trace_id"],
            "rid": split_row["trace_id"],
            "line_no": split_row["line_no"],
            "offset": split_row["offset"],
            "user_hash": split_row["user_hash"],
            "time_idx": split_row["time_idx"],
            "small_split": split_row.get("small_split"),
            "full_split": split_row.get("full_split"),
            "start_time": split_row["start_time"],
            "start_s": split_row["start_s"],
            "tau_s_small": split_row.get("tau_s_small"),
            "delta_small": split_row.get("delta_small"),
            "tau_s_full": split_row.get("tau_s_full"),
            "delta_full": split_row.get("delta_full"),
            "tau_s_global": split_row.get("tau_s_global"),
            "delta_global": split_row.get("delta_global"),
            "next_trace_id": split_row.get("next_trace_id"),
            "replay_max_tokens": max_tokens,
            "logged_usage": orig["logged_usage"],
            "client_request": client_request_fields(prompt),
        }
        try:
            async with sem:
                metrics = await measure_chat(
                    client,
                    model=model,
                    rid=str(split_row["trace_id"]),
                    messages=messages,
                    max_tokens=max_tokens,
                    client_max_tokens=prompt.get("max_tokens"),
                    tools=None if args.no_tools else tools,
                    temperature=prompt.get("temperature"),
                    top_p=prompt.get("top_p"),
                    reasoning_effort=prompt.get("reasoning_effort"),
                    timeout_s=args.request_timeout_s,
                )
            rec.update(metrics)
            rec["error"] = None
            async with results_lock:
                n_ok += 1
        except Exception as exc:  # noqa: BLE001
            rec["error"] = str(exc)
            rec["status"] = "err"
            async with results_lock:
                n_err += 1
        rec["replay_wall_s"] = time.perf_counter() - t0
        async with write_lock:
            fout.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            fout.flush()
        print(
            f"[{index+1}/{len(rows)}] {split_row['trace_id']} "
            f"status={rec.get('status')} err={rec.get('error')}",
            flush=True,
        )

    t0 = time.perf_counter()
    tasks = [asyncio.create_task(one(i, row)) for i, row in enumerate(rows)]
    await asyncio.gather(*tasks)
    wall = time.perf_counter() - t0
    fout.close()
    summary = {
        "n": len(rows),
        "n_ok": n_ok,
        "n_err": n_err,
        "n_skip_time_cap": n_skip,
        "wall_clock_s": round(wall, 3),
    }
    (out_dir / f"{prefix}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"[done] {summary} {path_jsonl}", flush=True)
    return 0 if n_err == 0 else 2


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    p.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    p.add_argument("--base-url", default="http://127.0.0.1:30000")
    p.add_argument("--api-key", default="EMPTY")
    p.add_argument("--model", default=None)
    p.add_argument("--max-events", type=int, default=None)
    p.add_argument("--max-inflight", type=int, default=2)
    p.add_argument(
        "--time-in-secs",
        type=float,
        default=0.0,
        help="optional issue cutoff in wall seconds; 0 = send all split rows",
    )
    p.add_argument("--request-timeout-s", type=float, default=600.0)
    p.add_argument("--no-tools", action="store_true")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--out-prefix", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dry-run-preview", type=int, default=20)
    return p


def main() -> None:
    raise SystemExit(asyncio.run(run(build_argparser().parse_args())))


if __name__ == "__main__":
    main()
