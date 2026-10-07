"""Optional read-only KV-cache diagnostics for SGLang 0.5.13.post1.

This module is copied into the isolated wheel installation by
``install_agentkv_diagnostics_patch.py``.  It is inert unless
``AGENTKV_DIAGNOSTICS_DIR`` is set.
"""

from __future__ import annotations

from array import array
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Iterable, Optional


def _sha256(parts: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.hexdigest()


def _token_digest(token_ids: Iterable[int], extra_key: Any = None) -> str:
    values = array("q", (int(token) for token in token_ids))
    return _sha256(
        (
            b"agentkv-prefix-v1\0",
            repr(extra_key).encode("utf-8", "surrogatepass"),
            b"\0",
            values.tobytes(),
        )
    )


class AgentKVDiagnostics:
    def __init__(self, cache: Any):
        destination = os.environ.get("AGENTKV_DIAGNOSTICS_DIR", "").strip()
        self.enabled = bool(destination)
        self.destination = Path(destination).resolve() if destination else None
        self.cache_instance_id = f"pid-{os.getpid()}-cache-{id(cache):x}"
        self._lock = threading.Lock()
        self._stream = None
        self._event_seq = 0
        self._eviction_seq = 0
        self._seen_request_ids: set[str] = set()
        self._demand: dict[str, dict[str, Any]] = {}
        self._bytes_per_token: dict[str, Optional[float]] = {}

    def _rank(self) -> int:
        try:
            import torch

            if torch.distributed.is_available() and torch.distributed.is_initialized():
                return int(torch.distributed.get_rank())
        except Exception:
            pass
        for name in ("RANK", "LOCAL_RANK", "SGLANG_TP_RANK"):
            try:
                return int(os.environ[name])
            except (KeyError, TypeError, ValueError):
                continue
        return -1

    def _rank_enabled(self, rank: int) -> bool:
        configured = os.environ.get("AGENTKV_DIAGNOSTICS_RANKS", "0").strip()
        if configured in {"", "all", "*"}:
            return True
        allowed = {int(item.strip()) for item in configured.split(",") if item.strip()}
        return rank in allowed

    def _ensure_stream(self, rank: int):
        if not self.enabled or not self._rank_enabled(rank):
            return None
        if self._stream is None:
            self.destination.mkdir(parents=True, exist_ok=True)
            path = self.destination / f"events.rank{rank}.pid{os.getpid()}.jsonl"
            self._stream = path.open("a", encoding="utf-8", buffering=1)
        return self._stream

    def emit(self, event_type: str, **fields: Any) -> Optional[int]:
        if not self.enabled:
            return None
        rank = self._rank()
        with self._lock:
            stream = self._ensure_stream(rank)
            if stream is None:
                return None
            self._event_seq += 1
            record = {
                "schema_version": "agentkv_runtime_diagnostics_v1",
                "event_seq": self._event_seq,
                "event_time_monotonic_ns": time.monotonic_ns(),
                "event_time_unix_ns": time.time_ns(),
                "event_type": event_type,
                "cache_instance_id": self.cache_instance_id,
                "tp_rank": rank,
                "pid": os.getpid(),
                **fields,
            }
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
            return self._event_seq

    @staticmethod
    def _node_tokens(node: Any) -> tuple[list[int], Any]:
        chunks = []
        extra_key = None
        cur = node
        while cur is not None and getattr(cur, "parent", None) is not None:
            key = getattr(cur, "key", None)
            if key is not None:
                chunks.append(list(key.token_ids))
                extra_key = key.extra_key
            cur = cur.parent
        tokens = []
        for chunk in reversed(chunks):
            tokens.extend(chunk)
        return tokens, extra_key

    def node_identity(self, node: Any) -> dict[str, Any]:
        if node is None or getattr(node, "parent", None) is None:
            return {
                "stable_prefix_digest": "root",
                "cache_namespace_hash": _sha256((b"agentkv-namespace-v1\0root",)),
                "path_tokens": 0,
            }
        tokens, extra_key = self._node_tokens(node)
        namespace_hash = _sha256(
            (b"agentkv-namespace-v1\0", repr(extra_key).encode("utf-8", "surrogatepass"))
        )
        return {
            "stable_prefix_digest": _token_digest(tokens, extra_key),
            "cache_namespace_hash": namespace_hash,
            "path_tokens": len(tokens),
        }

    def _component_data(self, node: Any, component: int) -> Any:
        try:
            return node.component_data[component]
        except Exception:
            return None

    def _pool_bytes_per_token(self, cache: Any, pool: str) -> Optional[float]:
        if pool in self._bytes_per_token:
            return self._bytes_per_token[pool]
        value = None
        try:
            allocator = cache.token_to_kv_pool_allocator
            kv_cache = allocator.get_kvcache()
            if pool == "full":
                physical_pool = getattr(kv_cache, "full_kv_pool", kv_cache)
                capacity = getattr(allocator, "size_full", getattr(allocator, "size", 0))
            else:
                physical_pool = getattr(kv_cache, "swa_kv_pool", None)
                capacity = getattr(allocator, "size_swa", 0)
            total_bytes = physical_pool.get_kv_size_bytes() if physical_pool is not None else None
            if isinstance(total_bytes, tuple):
                total_bytes = sum(total_bytes)
            if total_bytes is not None and capacity:
                value = float(total_bytes) / float(capacity)
        except Exception:
            value = None
        self._bytes_per_token[pool] = value
        return value

    def snapshot_node(self, cache: Any, node: Any, pool: str) -> dict[str, Any]:
        from sglang.srt.mem_cache.unified_cache_components.tree_component import ComponentType

        ct = ComponentType.FULL if pool == "full" else ComponentType.SWA
        identity = self.node_identity(node)
        parent_identity = self.node_identity(getattr(node, "parent", None))
        cd = self._component_data(node, ct)
        logical_tokens = len(node.key) if getattr(node, "key", None) is not None else 0
        bytes_per_token = self._pool_bytes_per_token(cache, pool)
        demand = self._demand.get(identity["stable_prefix_digest"], {})
        strategy = getattr(cache, "eviction_strategy", None)
        try:
            policy_score = strategy.get_priority(node) if pool == "full" else node.last_access_time
            if isinstance(policy_score, tuple):
                policy_score = list(policy_score)
        except Exception:
            policy_score = None
        return {
            **identity,
            "parent_stable_prefix_digest": parent_identity["stable_prefix_digest"],
            "transient_node_id": int(node.id),
            "logical_tokens": logical_tokens,
            "physical_bytes": None if bytes_per_token is None else int(round(logical_tokens * bytes_per_token)),
            "bytes_per_token": bytes_per_token,
            "component_value_tokens": None if cd is None or cd.value is None else len(cd.value),
            "component_host_value_tokens": None if cd is None or cd.host_value is None else len(cd.host_value),
            "lock_ref": None if cd is None else int(cd.lock_ref),
            "host_lock_ref": None if cd is None else int(cd.host_lock_ref),
            "child_count": len(getattr(node, "children", {})),
            "is_full_device_leaf": node in getattr(cache, "evictable_device_leaves", ()),
            "hit_count": int(getattr(node, "hit_count", 0)),
            "last_access_time": float(getattr(node, "last_access_time", 0)),
            "creation_time": float(getattr(node, "creation_time", 0)),
            "priority": int(getattr(node, "priority", 0)),
            "policy_score": policy_score,
            "demand_count": int(demand.get("count", 0)),
            "last_demand_event_seq": demand.get("event_seq"),
            "last_demand_time_ns": demand.get("time_ns"),
        }

    def log_demand(self, cache: Any, params: Any, result: Any, aligned_key: Any) -> None:
        req = getattr(params, "req", None)
        if not self.enabled or req is None:
            return
        rid = str(getattr(req, "rid", ""))
        if not rid or rid in self._seen_request_ids:
            return
        self._seen_request_ids.add(rid)
        matched = int(len(result.device_indices))
        nodes = []
        cur = result.last_device_node
        while cur is not None and getattr(cur, "parent", None) is not None:
            nodes.append(cur)
            cur = cur.parent
        nodes.reverse()
        demand_nodes = []
        for node in nodes:
            identity = self.node_identity(node)
            digest = identity["stable_prefix_digest"]
            current = self._demand.setdefault(digest, {"count": 0})
            current["count"] += 1
            demand_nodes.append({**identity, "transient_node_id": int(node.id)})
        event_seq = self.emit(
            "demand",
            request_id=rid,
            requested_tokens=len(aligned_key),
            requested_stable_prefix_digest=_token_digest(aligned_key.token_ids, aligned_key.extra_key),
            matched_full_tokens=matched,
            matched_stable_prefix_digest=self.node_identity(result.last_device_node)["stable_prefix_digest"],
            demanded_nodes=demand_nodes,
        )
        now = time.monotonic_ns()
        if event_seq is not None:
            for node in demand_nodes:
                current = self._demand[node["stable_prefix_digest"]]
                current["event_seq"] = event_seq
                current["time_ns"] = now

    def log_store(self, cache: Any, node: Any) -> None:
        if self.enabled:
            self.emit("store", pool="full", node=self.snapshot_node(cache, node, "full"))

    def log_split(self, cache: Any, old_child_id: int, new_parent: Any, child: Any) -> None:
        if self.enabled:
            self.emit(
                "split",
                old_child_transient_node_id=old_child_id,
                new_parent=self.snapshot_node(cache, new_parent, "full"),
                child=self.snapshot_node(cache, child, "full"),
            )

    def log_commit(self, cache: Any, req: Any, committed_tokens: int, page_aligned_tokens: int, result: Any, finished: bool) -> None:
        if not self.enabled:
            return
        self.emit(
            "commit",
            request_id=str(getattr(req, "rid", "")),
            committed_tokens=int(committed_tokens),
            page_aligned_tokens=int(page_aligned_tokens),
            already_present_tokens=None if result is None else int(result.prefix_len),
            finished=bool(finished),
        )

    def log_lock(self, cache: Any, node: Any, action: str) -> None:
        if not self.enabled or node is None:
            return
        self.emit(action, anchor=self.snapshot_node(cache, node, "full"))

    def log_flush(self, cache: Any) -> None:
        if self.enabled and hasattr(cache, "root_node"):
            self.emit("flush")

    def begin_eviction(self, cache: Any, pool: str, requested_tokens: int, candidates: Iterable[Any]) -> Optional[str]:
        if not self.enabled or requested_tokens <= 0:
            return None
        self._eviction_seq += 1
        eviction_id = f"{self.cache_instance_id}-{pool}-{self._eviction_seq}"
        snapshots = [self.snapshot_node(cache, node, pool) for node in candidates]
        snapshots.sort(key=lambda item: (json.dumps(item.get("policy_score"), sort_keys=True), item["transient_node_id"]))
        self.emit(
            "eviction_begin",
            eviction_id=eviction_id,
            pool=pool,
            trigger_reason="allocator_capacity",
            requested_free_tokens=int(requested_tokens),
            requested_free_bytes=None,
            candidate_coverage_complete=True,
            candidate_count=len(snapshots),
            candidates=snapshots,
        )
        return eviction_id

    def eviction_step(
        self,
        cache: Any,
        eviction_id: Optional[str],
        pool: str,
        step_seq: int,
        victim_before: dict[str, Any],
        released_tokens: int,
        parent_after: Any = None,
        parent_exposed: bool = False,
        step_kind: str = "leaf",
        selection_stage: Optional[str] = None,
    ) -> None:
        if eviction_id is None:
            return
        bytes_per_token = self._pool_bytes_per_token(cache, pool)
        self.emit(
            "eviction_step",
            eviction_id=eviction_id,
            pool=pool,
            step_seq=int(step_seq),
            step_kind=step_kind,
            victim=victim_before,
            released_tokens=int(released_tokens),
            released_bytes=None if bytes_per_token is None else int(round(released_tokens * bytes_per_token)),
            parent_exposed=bool(parent_exposed),
            added_candidate=(self.snapshot_node(cache, parent_after, pool) if parent_exposed and parent_after is not None else None),
            selection_stage=selection_stage,
        )

    def end_eviction(self, eviction_id: Optional[str], pool: str, requested_tokens: int, released_tokens: int, steps: int) -> None:
        if eviction_id is not None:
            self.emit(
                "eviction_end",
                eviction_id=eviction_id,
                pool=pool,
                requested_free_tokens=int(requested_tokens),
                released_tokens=int(released_tokens),
                overshoot_tokens=max(0, int(released_tokens) - int(requested_tokens)),
                steps=int(steps),
            )


def get_diagnostics(cache: Any) -> AgentKVDiagnostics:
    return AgentKVDiagnostics(cache)
