#!/usr/bin/env python3
"""Shared helpers for reading lmcache_traces Arrow first-turn rows."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.ipc as ipc

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_DIR = REPO_ROOT / "experiments/vllm_kv_cache/lmcache_traces"
DEFAULT_TOKENIZER = Path(
    "/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/"
    "snapshots/b968826d9c46dd6066d109eabc6255188de91218"
)


def clean_message(message: dict[str, Any]) -> dict[str, Any]:
    """Drop null Arrow struct fields while preserving tool-call payloads."""
    cleaned: dict[str, Any] = {}
    for key, value in message.items():
        if value is None:
            continue
        if isinstance(value, list):
            cleaned[key] = [
                clean_message(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, dict):
            cleaned[key] = clean_message(value)
        else:
            cleaned[key] = value
    return cleaned


def tokenize_messages(tokenizer: Any, messages: list[dict[str, Any]]) -> list[int]:
    cleaned = [clean_message(message) for message in messages]
    rendered = tokenizer.apply_chat_template(
        cleaned,
        tokenize=False,
        add_generation_prompt=True,
    )
    return tokenizer.encode(rendered, add_special_tokens=False)


def arrow_paths(trace_dir: Path) -> list[Path]:
    paths = sorted(trace_dir.glob("data-*-of-*.arrow"))
    if not paths:
        raise FileNotFoundError(f"No Arrow shards found under {trace_dir}")
    return paths


def load_first_turns(
    trace_dir: Path,
    source_model: str | None,
    max_sessions: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return the first row seen for each explicit session."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    all_row_count = 0
    missing_session_count = 0
    source_model_counts: Counter[str] = Counter()
    shard_manifest = []

    stop = False
    for path in arrow_paths(trace_dir):
        stat = path.stat()
        shard_rows = 0
        reader = ipc.open_stream(str(path))
        for batch in reader:
            columns = {name: batch.column(name) for name in batch.schema.names}
            for row_index in range(batch.num_rows):
                all_row_count += 1
                shard_rows += 1
                session_id = columns["session_id"][row_index].as_py()
                model = columns["model"][row_index].as_py()
                if not session_id:
                    missing_session_count += 1
                    continue
                if source_model and model != source_model:
                    continue
                if session_id in seen:
                    continue
                seen.add(session_id)
                source_model_counts[model or "unknown"] += 1
                rows.append(
                    {
                        "session_id": session_id,
                        "model": model or "unknown",
                        "messages": columns["input"][row_index].as_py(),
                        "row_ordinal": all_row_count - 1,
                    }
                )
                if max_sessions and len(rows) >= max_sessions:
                    stop = True
                    break
            if stop:
                break
        shard_manifest.append(
            {
                "path": str(path.relative_to(REPO_ROOT)),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "rows_scanned": shard_rows,
            }
        )
        if stop:
            break

    audit = {
        "rows_scanned": all_row_count,
        "first_turn_rows_selected": len(rows),
        "unique_explicit_sessions": len(seen),
        "missing_session_rows": missing_session_count,
        "source_model_filter": source_model,
        "source_model_session_counts": dict(source_model_counts),
        "shards": shard_manifest,
    }
    return rows, audit
