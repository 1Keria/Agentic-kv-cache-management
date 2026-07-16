#!/usr/bin/env python3
"""Measure exact cross-session prefix opportunity on first-turn agent requests.

The analysis replays LMCache messages through a fixed Hugging Face chat template
and tokenizer, then inserts complete cache blocks into an exact block trie.
Unlike the older L0/L1 heuristic, trie edges are tuples of token IDs, so shared
nodes represent byte-for-byte compatible token prefixes.

This script intentionally analyzes the first request of each explicit session.
It therefore isolates cold-start cross-session opportunity from ordinary
within-session multi-turn reuse. The source trace has no global arrival time,
so the output reports:

* leave-one-session-out opportunity: another session uses the same prefix
  somewhere in the dataset (an order-free static upper bound);
* dataset-order prior opportunity: another session appeared earlier in Arrow
  shard/row order (an ordering proxy, not a production hit rate).

It does not model cache capacity, eviction, residency, or TTFT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pyarrow.ipc as ipc
from transformers import AutoTokenizer


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_DIR = (
    REPO_ROOT / "experiments/vllm_kv_cache/lmcache_traces"
)
DEFAULT_TOKENIZER = Path(
    "/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/"
    "snapshots/b968826d9c46dd6066d109eabc6255188de91218"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "experiments/vllm_kv_cache/investigation/data/"
    "f01_cross_session_exact_prefix.json"
)


@dataclass
class RequestPath:
    session_id: str
    source_model: str
    project: str
    task_key: str
    row_ordinal: int
    raw_tokens: int
    full_block_tokens: int
    path: list[int]


class ExactBlockTrie:
    """An exact radix-like trie whose edge keys are complete token blocks."""

    def __init__(self) -> None:
        self.children: list[dict[tuple[int, ...], int]] = [{}]
        self.parent: list[int] = [-1]
        self.edge: list[tuple[int, ...] | None] = [None]
        self.depth_blocks: list[int] = [0]
        self.holder_masks: list[int] = [0]

    def insert(
        self, token_ids: list[int], block_size: int, session_bit: int
    ) -> list[int]:
        node = 0
        path: list[int] = []
        complete = len(token_ids) // block_size
        for block_index in range(complete):
            start = block_index * block_size
            block = tuple(token_ids[start : start + block_size])
            child = self.children[node].get(block)
            if child is None:
                child = len(self.children)
                self.children[node][block] = child
                self.children.append({})
                self.parent.append(node)
                self.edge.append(block)
                self.depth_blocks.append(block_index + 1)
                self.holder_masks.append(0)
            self.holder_masks[child] |= session_bit
            path.append(child)
            node = child
        return path

    def prefix_key(self, node: int) -> str:
        blocks: list[tuple[int, ...]] = []
        while node:
            edge = self.edge[node]
            assert edge is not None
            blocks.append(edge)
            node = self.parent[node]
        digest = hashlib.blake2b(digest_size=16)
        for block in reversed(blocks):
            digest.update(struct.pack(f"<{len(block)}I", *block))
        return digest.hexdigest()


def percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * q)
    return ordered[index]


def distribution(values: list[int]) -> dict[str, float | int]:
    if not values:
        return {
            "count": 0,
            "min": 0,
            "p25": 0,
            "p50": 0,
            "p75": 0,
            "p90": 0,
            "p95": 0,
            "p99": 0,
            "max": 0,
            "mean": 0.0,
        }
    return {
        "count": len(values),
        "min": min(values),
        "p25": percentile(values, 0.25),
        "p50": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": max(values),
        "mean": round(sum(values) / len(values), 2),
    }


def ratio(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 4) if denominator else 0.0


def project_from_session_id(session_id: str) -> str:
    parts = session_id.split("__")
    if len(parts) >= 3 and parts[0] == "swebench":
        return parts[1]
    if parts:
        return parts[0]
    return "unknown"


def task_key_from_session_id(session_id: str) -> str:
    """Collapse repeated model/run variants of one SWE-bench instance."""
    parts = session_id.split("__")
    if len(parts) >= 3 and parts[0] == "swebench":
        return "__".join(parts[:3])
    return session_id


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
            columns = {
                name: batch.column(name) for name in batch.schema.names
            }
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


def longest_prefix_blocks(
    path: list[int], masks: list[int], eligible_mask: int
) -> int:
    depth = 0
    for node in path:
        if masks[node] & eligible_mask:
            depth += 1
        else:
            break
    return depth


def mask_samples(
    mask: int, session_ids: list[str], limit: int = 5
) -> list[str]:
    samples = []
    while mask and len(samples) < limit:
        low_bit = mask & -mask
        index = low_bit.bit_length() - 1
        samples.append(session_ids[index])
        mask ^= low_bit
    return samples


def aggregate_group(
    records: Iterable[dict[str, Any]], total_field: str
) -> dict[str, Any]:
    grouped = list(records)
    total = sum(int(record[total_field]) for record in grouped)
    cross = sum(int(record["cross_prefix_tokens"]) for record in grouped)
    return {
        "requests": len(grouped),
        "full_block_tokens": total,
        "cross_prefix_tokens": cross,
        "cross_prefix_token_ratio_pct": ratio(cross, total),
        "cross_prefix_tokens_per_request": distribution(
            [int(record["cross_prefix_tokens"]) for record in grouped]
        ),
        "requests_with_cross_prefix_pct": ratio(
            sum(record["cross_prefix_tokens"] > 0 for record in grouped),
            len(grouped),
        ),
    }


def analyze(
    rows: list[dict[str, Any]],
    tokenizer: Any,
    block_size: int,
    top_families: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trie = ExactBlockTrie()
    session_ids = [row["session_id"] for row in rows]
    session_index = {
        session_id: index for index, session_id in enumerate(session_ids)
    }
    model_masks: dict[str, int] = defaultdict(int)
    project_masks: dict[str, int] = defaultdict(int)
    task_masks: dict[str, int] = defaultdict(int)
    requests: list[RequestPath] = []
    tokenization_failures = []

    started = time.time()
    for index, row in enumerate(rows):
        bit = 1 << index
        model = row["model"]
        project = project_from_session_id(row["session_id"])
        task_key = task_key_from_session_id(row["session_id"])
        model_masks[model] |= bit
        project_masks[project] |= bit
        task_masks[task_key] |= bit
        try:
            token_ids = tokenize_messages(tokenizer, row["messages"])
        except Exception as error:  # Preserve auditability on malformed rows.
            tokenization_failures.append(
                {
                    "session_id": row["session_id"],
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            continue
        path = trie.insert(token_ids, block_size, bit)
        requests.append(
            RequestPath(
                session_id=row["session_id"],
                source_model=model,
                project=project,
                task_key=task_key,
                row_ordinal=row["row_ordinal"],
                raw_tokens=len(token_ids),
                full_block_tokens=len(path) * block_size,
                path=path,
            )
        )
        if (index + 1) % 100 == 0:
            print(
                f"  tokenized {index + 1}/{len(rows)} sessions; "
                f"trie_nodes={len(trie.children) - 1:,}",
                flush=True,
            )

    prior_masks = [0] * len(trie.children)
    request_results: list[dict[str, Any]] = []
    thresholds = (1024, 4096, 8192, 16384)
    for request in requests:
        index = session_index[request.session_id]
        own_bit = 1 << index
        other_sessions = ((1 << len(rows)) - 1) ^ own_bit
        all_cross_blocks = longest_prefix_blocks(
            request.path, trie.holder_masks, other_sessions
        )
        same_model_blocks = longest_prefix_blocks(
            request.path,
            trie.holder_masks,
            model_masks[request.source_model] ^ own_bit,
        )
        same_project_blocks = longest_prefix_blocks(
            request.path,
            trie.holder_masks,
            project_masks[request.project] ^ own_bit,
        )
        different_task_blocks = longest_prefix_blocks(
            request.path,
            trie.holder_masks,
            other_sessions & ~task_masks[request.task_key],
        )
        same_project_different_task_blocks = longest_prefix_blocks(
            request.path,
            trie.holder_masks,
            project_masks[request.project] & ~task_masks[request.task_key],
        )
        different_project_blocks = longest_prefix_blocks(
            request.path,
            trie.holder_masks,
            other_sessions & ~project_masks[request.project],
        )
        prior_blocks = longest_prefix_blocks(
            request.path, prior_masks, other_sessions
        )
        result = {
            "session_id": request.session_id,
            "source_model": request.source_model,
            "project": request.project,
            "task_key": request.task_key,
            "row_ordinal": request.row_ordinal,
            "raw_tokens": request.raw_tokens,
            "full_block_tokens": request.full_block_tokens,
            "cross_prefix_tokens": all_cross_blocks * block_size,
            "same_source_model_cross_prefix_tokens": (
                same_model_blocks * block_size
            ),
            "same_project_cross_prefix_tokens": same_project_blocks * block_size,
            "different_task_cross_prefix_tokens": (
                different_task_blocks * block_size
            ),
            "same_project_different_task_cross_prefix_tokens": (
                same_project_different_task_blocks * block_size
            ),
            "different_project_cross_prefix_tokens": (
                different_project_blocks * block_size
            ),
            "dataset_order_prior_cross_prefix_tokens": (
                prior_blocks * block_size
            ),
        }
        for threshold in thresholds:
            result[f"cross_at_least_{threshold}_tokens"] = (
                result["cross_prefix_tokens"] >= threshold
            )
        request_results.append(result)
        for node in request.path:
            prior_masks[node] |= own_bit

    shared_nodes = [
        node
        for node in range(1, len(trie.children))
        if trie.holder_masks[node].bit_count() >= 2
    ]
    maximal_shared_nodes = [
        node
        for node in shared_nodes
        if not any(
            trie.holder_masks[child].bit_count() >= 2
            for child in trie.children[node].values()
        )
    ]
    membership_boundary_nodes = [
        node
        for node in shared_nodes
        if trie.parent[node] == 0
        or trie.holder_masks[node] != trie.holder_masks[trie.parent[node]]
    ]

    top_nodes = sorted(
        maximal_shared_nodes,
        key=lambda node: (
            trie.depth_blocks[node] * trie.holder_masks[node].bit_count(),
            trie.depth_blocks[node],
        ),
        reverse=True,
    )[:top_families]
    top_family_rows = []
    for node in top_nodes:
        holder_mask = trie.holder_masks[node]
        top_family_rows.append(
            {
                "prefix_key_blake2b_128": trie.prefix_key(node),
                "prefix_tokens": trie.depth_blocks[node] * block_size,
                "holder_session_count": holder_mask.bit_count(),
                "sample_session_ids": mask_samples(
                    holder_mask, session_ids
                ),
            }
        )

    total_full_tokens = sum(
        result["full_block_tokens"] for result in request_results
    )
    total_cross_tokens = sum(
        result["cross_prefix_tokens"] for result in request_results
    )
    prior_cross_tokens = sum(
        result["dataset_order_prior_cross_prefix_tokens"]
        for result in request_results
    )
    same_model_tokens = sum(
        result["same_source_model_cross_prefix_tokens"]
        for result in request_results
    )
    same_project_tokens = sum(
        result["same_project_cross_prefix_tokens"]
        for result in request_results
    )
    different_task_tokens = sum(
        result["different_task_cross_prefix_tokens"]
        for result in request_results
    )
    same_project_different_task_tokens = sum(
        result["same_project_different_task_cross_prefix_tokens"]
        for result in request_results
    )
    different_project_tokens = sum(
        result["different_project_cross_prefix_tokens"]
        for result in request_results
    )
    duplicate_task_group_sizes = [
        mask.bit_count() for mask in task_masks.values() if mask.bit_count() > 1
    ]
    threshold_fields = {
        "any_other_session": "cross_prefix_tokens",
        "different_task": "different_task_cross_prefix_tokens",
        "same_project_different_task": (
            "same_project_different_task_cross_prefix_tokens"
        ),
        "different_project": "different_project_cross_prefix_tokens",
        "dataset_order_prior": "dataset_order_prior_cross_prefix_tokens",
    }

    summary = {
        "scope": {
            "unit": "first request of each explicit session",
            "token_prefix": (
                "Qwen chat-template serialization; exact complete token blocks"
            ),
            "opportunity_semantics": (
                "leave-one-session-out static opportunity; no cache capacity, "
                "residency, eviction, or global-time claim"
            ),
        },
        "counts": {
            "requests": len(request_results),
            "sessions": len(request_results),
            "source_models": len(model_masks),
            "projects": len(project_masks),
            "unique_task_keys": len(task_masks),
            "repeated_task_groups": len(duplicate_task_group_sizes),
            "tokenization_failures": len(tokenization_failures),
            "trie_nodes_excluding_root": len(trie.children) - 1,
            "shared_prefix_nodes": len(shared_nodes),
            "maximal_shared_prefix_nodes": len(maximal_shared_nodes),
            "membership_boundary_nodes": len(membership_boundary_nodes),
        },
        "token_mass": {
            "raw_prompt_tokens": sum(
                result["raw_tokens"] for result in request_results
            ),
            "complete_block_prompt_tokens": total_full_tokens,
            "leave_one_session_out_cross_prefix_tokens": total_cross_tokens,
            "leave_one_session_out_cross_prefix_ratio_pct": ratio(
                total_cross_tokens, total_full_tokens
            ),
            "same_source_model_cross_prefix_tokens": same_model_tokens,
            "same_source_model_cross_prefix_ratio_pct": ratio(
                same_model_tokens, total_full_tokens
            ),
            "same_project_cross_prefix_tokens": same_project_tokens,
            "same_project_cross_prefix_ratio_pct": ratio(
                same_project_tokens, total_full_tokens
            ),
            "different_task_cross_prefix_tokens": different_task_tokens,
            "different_task_cross_prefix_ratio_pct": ratio(
                different_task_tokens, total_full_tokens
            ),
            "same_project_different_task_cross_prefix_tokens": (
                same_project_different_task_tokens
            ),
            "same_project_different_task_cross_prefix_ratio_pct": ratio(
                same_project_different_task_tokens, total_full_tokens
            ),
            "different_project_cross_prefix_tokens": different_project_tokens,
            "different_project_cross_prefix_ratio_pct": ratio(
                different_project_tokens, total_full_tokens
            ),
            "dataset_order_prior_cross_prefix_tokens": prior_cross_tokens,
            "dataset_order_prior_cross_prefix_ratio_pct": ratio(
                prior_cross_tokens, total_full_tokens
            ),
        },
        "request_distributions": {
            "raw_prompt_tokens": distribution(
                [result["raw_tokens"] for result in request_results]
            ),
            "cross_prefix_tokens": distribution(
                [result["cross_prefix_tokens"] for result in request_results]
            ),
            "cross_prefix_ratio_pct": distribution(
                [
                    round(
                        100
                        * result["cross_prefix_tokens"]
                        / result["full_block_tokens"]
                    )
                    if result["full_block_tokens"]
                    else 0
                    for result in request_results
                ]
            ),
            "dataset_order_prior_cross_prefix_tokens": distribution(
                [
                    result["dataset_order_prior_cross_prefix_tokens"]
                    for result in request_results
                ]
            ),
            "different_task_cross_prefix_tokens": distribution(
                [
                    result["different_task_cross_prefix_tokens"]
                    for result in request_results
                ]
            ),
            "different_project_cross_prefix_tokens": distribution(
                [
                    result["different_project_cross_prefix_tokens"]
                    for result in request_results
                ]
            ),
        },
        "task_duplication_audit": {
            "repeated_task_group_size": distribution(
                duplicate_task_group_sizes
            ),
            "sessions_in_repeated_task_groups": sum(
                duplicate_task_group_sizes
            ),
            "sessions_in_repeated_task_groups_pct": ratio(
                sum(duplicate_task_group_sizes), len(request_results)
            ),
            "note": (
                "SWE-bench session IDs that differ only by source model or "
                "run suffix share one task_key; different-task metrics exclude "
                "these benchmark repeats."
            ),
        },
        "cold_start_thresholds": {
            f"requests_cross_at_least_{threshold}_tokens": sum(
                result[f"cross_at_least_{threshold}_tokens"]
                for result in request_results
            )
            for threshold in thresholds
        },
        "cold_start_threshold_rates_pct": {
            f"requests_cross_at_least_{threshold}_tokens_pct": ratio(
                sum(
                    result[f"cross_at_least_{threshold}_tokens"]
                    for result in request_results
                ),
                len(request_results),
            )
            for threshold in thresholds
        },
        "cold_start_thresholds_by_scope": {
            scope: {
                f"at_least_{threshold}_tokens": {
                    "requests": sum(
                        result[field] >= threshold
                        for result in request_results
                    ),
                    "requests_pct": ratio(
                        sum(
                            result[field] >= threshold
                            for result in request_results
                        ),
                        len(request_results),
                    ),
                }
                for threshold in thresholds
            }
            for scope, field in threshold_fields.items()
        },
        "family_structure": {
            "shared_node_holder_session_count": distribution(
                [
                    trie.holder_masks[node].bit_count()
                    for node in shared_nodes
                ]
            ),
            "shared_node_depth_tokens": distribution(
                [trie.depth_blocks[node] * block_size for node in shared_nodes]
            ),
            "maximal_family_holder_session_count": distribution(
                [
                    trie.holder_masks[node].bit_count()
                    for node in maximal_shared_nodes
                ]
            ),
            "maximal_family_prefix_tokens": distribution(
                [
                    trie.depth_blocks[node] * block_size
                    for node in maximal_shared_nodes
                ]
            ),
            "top_maximal_families": top_family_rows,
        },
        "by_source_model": {
            model: aggregate_group(
                (
                    result
                    for result in request_results
                    if result["source_model"] == model
                ),
                "full_block_tokens",
            )
            for model in sorted(model_masks)
        },
        "by_project": {
            project: aggregate_group(
                (
                    result
                    for result in request_results
                    if result["project"] == project
                ),
                "full_block_tokens",
            )
            for project in sorted(project_masks)
        },
        "runtime": {
            "analysis_seconds": round(time.time() - started, 3),
        },
        "tokenization_failures": tokenization_failures,
    }
    return summary, request_results


def tokenizer_manifest(tokenizer: Any, tokenizer_path: Path) -> dict[str, Any]:
    chat_template = tokenizer.chat_template or ""
    return {
        "path": str(tokenizer_path),
        "class": type(tokenizer).__name__,
        "name_or_path": tokenizer.name_or_path,
        "vocab_size": tokenizer.vocab_size,
        "model_max_length": tokenizer.model_max_length,
        "chat_template_sha256": hashlib.sha256(
            chat_template.encode("utf-8")
        ).hexdigest(),
        "add_generation_prompt": True,
        "add_special_tokens_after_render": False,
    }


def self_test() -> None:
    trie = ExactBlockTrie()
    a = trie.insert([1, 2, 3, 4], block_size=2, session_bit=1)
    b = trie.insert([1, 2, 5, 6], block_size=2, session_bit=2)
    c = trie.insert([7, 8, 9, 10], block_size=2, session_bit=4)
    assert longest_prefix_blocks(a, trie.holder_masks, 2 | 4) == 1
    assert longest_prefix_blocks(b, trie.holder_masks, 1 | 4) == 1
    assert longest_prefix_blocks(c, trie.holder_masks, 1 | 2) == 0
    assert trie.holder_masks[a[0]].bit_count() == 2
    assert trie.holder_masks[a[1]].bit_count() == 1
    assert trie.prefix_key(a[0]) == trie.prefix_key(b[0])
    print("self-test passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR)
    parser.add_argument(
        "--tokenizer-path", type=Path, default=DEFAULT_TOKENIZER
    )
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--source-model", default=None)
    parser.add_argument("--max-sessions", type=int, default=None)
    parser.add_argument("--top-families", type=int, default=20)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.block_size <= 0:
        raise ValueError("--block-size must be positive")

    print(f"Loading tokenizer from {args.tokenizer_path}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(
        args.tokenizer_path, local_files_only=True
    )
    if not tokenizer.chat_template:
        raise ValueError("Tokenizer has no chat_template")

    print(f"Scanning first turns under {args.trace_dir}", flush=True)
    rows, input_audit = load_first_turns(
        args.trace_dir, args.source_model, args.max_sessions
    )
    print(f"Selected {len(rows)} explicit sessions", flush=True)
    if len(rows) < 2:
        raise ValueError("At least two sessions are required")

    summary, request_results = analyze(
        rows, tokenizer, args.block_size, args.top_families
    )
    output = {
        "schema_version": 1,
        "generated_unix_seconds": time.time(),
        "configuration": {
            "trace_dir": str(args.trace_dir),
            "block_size": args.block_size,
            "source_model_filter": args.source_model,
            "max_sessions": args.max_sessions,
        },
        "input_audit": input_audit,
        "tokenizer_manifest": tokenizer_manifest(
            tokenizer, args.tokenizer_path
        ),
        "summary": summary,
        "per_session_first_turn": request_results,
        "limitations": [
            (
                "The Arrow trace has no global arrival timestamp; dataset-order "
                "metrics are ordering proxies, not causal online hit rates."
            ),
            (
                "Leave-one-session-out metrics assume another session's exact "
                "prefix could be available; they do not model cache residency."
            ),
            (
                "All messages are replayed through the fixed target tokenizer "
                "and chat template, regardless of their original source model."
            ),
            (
                "Only complete cache blocks are counted; incomplete trailing "
                "tokens are excluded."
            ),
            (
                "This first-turn analysis isolates cross-session cold-start "
                "opportunity and does not estimate within-session reuse."
            ),
            (
                "Some SWE-bench tasks have repeated model/run sessions. Use "
                "different_task metrics for the conservative cross-task view."
            ),
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    mass = summary["token_mass"]
    rates = summary["cold_start_threshold_rates_pct"]
    scoped_rates = summary["cold_start_thresholds_by_scope"]
    print(f"Wrote {args.output}")
    print(
        "Leave-one-session-out cross-prefix ratio: "
        f"{mass['leave_one_session_out_cross_prefix_ratio_pct']:.2f}%"
    )
    print(
        "Dataset-order prior cross-prefix ratio: "
        f"{mass['dataset_order_prior_cross_prefix_ratio_pct']:.2f}%"
    )
    print(
        "Different-task cross-prefix ratio: "
        f"{mass['different_task_cross_prefix_ratio_pct']:.2f}%"
    )
    print(
        "Different-project cross-prefix ratio: "
        f"{mass['different_project_cross_prefix_ratio_pct']:.2f}%"
    )
    print(
        "Cold starts with >=8K cross prefix: "
        f"{rates['requests_cross_at_least_8192_tokens_pct']:.2f}%"
    )
    print(
        "Cold starts with >=8K different-task cross prefix: "
        f"{scoped_rates['different_task']['at_least_8192_tokens']['requests_pct']:.2f}%"
    )
    print(
        "Cold starts with >=4K different-project cross prefix: "
        f"{scoped_rates['different_project']['at_least_4096_tokens']['requests_pct']:.2f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
