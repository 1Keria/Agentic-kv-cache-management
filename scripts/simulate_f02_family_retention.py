#!/usr/bin/env python3
"""Offline radix-leaf eviction replay for Family residual utility."""

from __future__ import annotations

import argparse
import collections
import hashlib
import heapq
import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from transformers import AutoTokenizer

from analyze_f01_cross_session_prefix import (
    DEFAULT_TOKENIZER,
    DEFAULT_TRACE_DIR,
    load_first_turns,
    tokenize_messages,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "experiments/vllm_kv_cache/investigation/data/"
    "f02_family_retention_simulation.json"
)
ROOT = b"\x00" * 16


def block_path(token_ids: list[int], block_size: int) -> list[bytes]:
    parent = ROOT
    path = []
    for offset in range(0, len(token_ids) - block_size + 1, block_size):
        block = token_ids[offset : offset + block_size]
        payload = parent + b"".join(
            int(token).to_bytes(4, "little", signed=False) for token in block
        )
        parent = hashlib.blake2b(payload, digest_size=16).digest()
        path.append(parent)
    return path


@dataclass
class NodeState:
    parent: bytes
    depth: int
    resident: bool = False
    resident_children: int = 0
    last_access: int = 0
    hit_count: int = 0
    observed_holders: int = 0
    last_holder: int = -1
    next_use: float = math.inf
    version: int = 0


class RadixReplay:
    def __init__(
        self,
        parents: dict[bytes, bytes],
        depths: dict[bytes, int],
        future: dict[bytes, collections.deque[int]],
        capacity_blocks: int,
        policy: str,
    ):
        self.nodes = {
            node: NodeState(parent=parents[node], depth=depths[node])
            for node in parents
        }
        self.future = future
        self.capacity = capacity_blocks
        self.policy = policy
        self.heap: list[tuple[Any, int, bytes]] = []
        self.resident_count = 0
        self.clock = 0
        self.evicted_blocks = 0

    def _priority(self, node: bytes) -> Any:
        state = self.nodes[node]
        if self.policy == "lru":
            return (state.last_access,)
        if self.policy == "lfu":
            return (state.hit_count, state.last_access)
        if self.policy == "slru":
            return (int(state.hit_count >= 2), state.last_access)
        if self.policy == "observed_shared_depth":
            return (
                state.observed_holders,
                state.depth,
                state.last_access,
            )
        if self.policy == "oracle_next_use":
            next_use = state.next_use
            return (-(next_use if math.isfinite(next_use) else 10**18),)
        raise ValueError(self.policy)

    def _push_if_leaf(self, node: bytes) -> None:
        state = self.nodes[node]
        if state.resident and state.resident_children == 0:
            state.version += 1
            heapq.heappush(
                self.heap, (self._priority(node), state.version, node)
            )

    def _evict_one(self, protected: set[bytes]) -> None:
        skipped = []
        while self.heap:
            priority, version, node = heapq.heappop(self.heap)
            state = self.nodes[node]
            if (
                not state.resident
                or state.resident_children != 0
                or version != state.version
                or priority != self._priority(node)
            ):
                continue
            if node in protected:
                skipped.append((priority, version, node))
                continue
            state.resident = False
            self.resident_count -= 1
            self.evicted_blocks += 1
            parent = state.parent
            if parent != ROOT:
                parent_state = self.nodes[parent]
                parent_state.resident_children -= 1
                self._push_if_leaf(parent)
            for item in skipped:
                heapq.heappush(self.heap, item)
            return
        for item in skipped:
            heapq.heappush(self.heap, item)
        raise RuntimeError("No evictable radix leaf")

    def access(self, path: list[bytes], request_index: int) -> int:
        self.clock += 1
        for node in path:
            queue = self.future[node]
            while queue and queue[0] <= request_index:
                queue.popleft()
            self.nodes[node].next_use = queue[0] if queue else math.inf

        matched = 0
        for node in path:
            state = self.nodes[node]
            if not state.resident:
                break
            matched += 1
            state.last_access = self.clock
            state.hit_count += 1
            self._push_if_leaf(node)

        for node in path:
            state = self.nodes[node]
            if state.last_holder != request_index:
                state.observed_holders += 1
                state.last_holder = request_index
                self._push_if_leaf(node)

        if len(path) > self.capacity:
            return matched

        for node in path[matched:]:
            state = self.nodes[node]
            if state.resident:
                continue
            parent = state.parent
            if parent != ROOT:
                parent_state = self.nodes[parent]
                if not parent_state.resident:
                    raise RuntimeError("Radix ancestor invariant violated")
                parent_state.resident_children += 1
                parent_state.version += 1
            state.resident = True
            state.last_access = self.clock
            state.hit_count += 1
            self.resident_count += 1
            self._push_if_leaf(node)
        protected = set(path)
        while self.resident_count > self.capacity:
            self._evict_one(protected)
        return matched


def build_topology(
    paths: list[list[bytes]],
) -> tuple[dict[bytes, bytes], dict[bytes, int]]:
    parents: dict[bytes, bytes] = {}
    depths: dict[bytes, int] = {}
    for path in paths:
        parent = ROOT
        for depth, node in enumerate(path, start=1):
            parents.setdefault(node, parent)
            depths.setdefault(node, depth)
            parent = node
    return parents, depths


def simulate(
    paths: list[list[bytes]],
    order: list[int],
    capacity_tokens: int,
    block_size: int,
    policy: str,
    parents: dict[bytes, bytes],
    depths: dict[bytes, int],
) -> dict[str, Any]:
    future: dict[bytes, collections.deque[int]] = collections.defaultdict(
        collections.deque
    )
    for position, request_id in enumerate(order):
        for node in paths[request_id]:
            future[node].append(position)
    replay = RadixReplay(
        parents,
        depths,
        future,
        capacity_tokens // block_size,
        policy,
    )
    hit_blocks = 0
    total_blocks = 0
    request_hits = []
    oversized_requests = 0
    for position, request_id in enumerate(order):
        path = paths[request_id]
        if len(path) > capacity_tokens // block_size:
            oversized_requests += 1
        matched = replay.access(path, position)
        hit_blocks += matched
        total_blocks += len(path)
        request_hits.append(matched * block_size)
    return {
        "policy": policy,
        "capacity_tokens": capacity_tokens,
        "requests": len(order),
        "complete_block_prompt_tokens": total_blocks * block_size,
        "avoided_prefill_tokens": hit_blocks * block_size,
        "avoided_prefill_ratio_pct": round(
            100 * hit_blocks / total_blocks, 4
        ),
        "requests_with_4k_hit_pct": round(
            100 * sum(hit >= 4096 for hit in request_hits) / len(order), 4
        ),
        "request_hit_tokens_p50": sorted(request_hits)[len(request_hits) // 2],
        "oversized_requests_not_admitted": oversized_requests,
        "resident_blocks_final": replay.resident_count,
        "evicted_blocks": replay.evicted_blocks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR)
    parser.add_argument(
        "--tokenizer-path", type=Path, default=DEFAULT_TOKENIZER
    )
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument(
        "--capacities", type=int, nargs="+", default=[32000, 44000, 60000]
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(
        args.tokenizer_path, local_files_only=True
    )
    rows, audit = load_first_turns(args.trace_dir, None, None)
    token_paths = [
        tokenize_messages(tokenizer, row["messages"]) for row in rows
    ]
    paths = [block_path(tokens, args.block_size) for tokens in token_paths]
    parents, depths = build_topology(paths)
    policies = [
        "lru",
        "lfu",
        "slru",
        "observed_shared_depth",
        "oracle_next_use",
    ]

    workload_orders = {"dataset_order": list(range(len(paths)))}
    for seed in args.seeds:
        order = list(range(len(paths)))
        random.Random(seed).shuffle(order)
        workload_orders[f"shuffle_seed_{seed}"] = order

    started = time.time()
    results = []
    for workload, order in workload_orders.items():
        for capacity in args.capacities:
            for policy in policies:
                print(
                    f"workload={workload} capacity={capacity} policy={policy}",
                    flush=True,
                )
                row = simulate(
                    paths,
                    order,
                    capacity,
                    args.block_size,
                    policy,
                    parents,
                    depths,
                )
                row["workload"] = workload
                results.append(row)

    grouped: dict[str, list[float]] = collections.defaultdict(list)
    for row in results:
        key = f"{row['capacity_tokens']}:{row['policy']}"
        grouped[key].append(row["avoided_prefill_ratio_pct"])
    aggregates = {
        key: {
            "runs": len(values),
            "mean_avoided_prefill_ratio_pct": round(
                sum(values) / len(values), 4
            ),
            "min_avoided_prefill_ratio_pct": round(min(values), 4),
            "max_avoided_prefill_ratio_pct": round(max(values), 4),
        }
        for key, values in grouped.items()
    }
    payload = {
        "schema_version": 1,
        "generated_unix_seconds": time.time(),
        "elapsed_seconds": round(time.time() - started, 3),
        "configuration": {
            "block_size": args.block_size,
            "capacities": args.capacities,
            "seeds": args.seeds,
            "workloads": list(workload_orders),
            "policies": policies,
            "opportunity_semantics": (
                "causal replay of first-session requests; shuffled orders are "
                "synthetic sensitivity tests"
            ),
        },
        "input_audit": {
            "requests": len(rows),
            "sessions": audit["unique_explicit_sessions"],
            "radix_nodes": len(parents),
        },
        "results": results,
        "aggregates": aggregates,
        "limitations": [
            "The replay uses complete 16-token blocks while SGLang uses page size 1.",
            "Only first requests are replayed; within-session turns and close events are absent.",
            "Requests larger than cache capacity can consume resident prefixes but are not admitted after their first miss.",
            "Observed shared-count is online, but oracle next-use uses future knowledge.",
            "Dataset order and shuffled orders are not measured production arrival streams.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
