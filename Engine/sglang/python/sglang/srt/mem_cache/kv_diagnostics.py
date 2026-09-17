"""Opt-in JSONL tracing for KV cache miss attribution."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Optional

from sglang.srt.mem_cache.utils import compute_node_hash_values


class KVDiagnosticTrace:
    """Record stable page hashes without logging raw tokens."""

    def __init__(self, path: Optional[str] = None):
        self.path = path if path is not None else os.getenv("SGLANG_KV_DIAG_TRACE_PATH")
        self.enabled = bool(self.path)
        self._lock = threading.Lock()
        self._seq = 0
        self._fd: Optional[int] = None
        if self.enabled:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            self._fd = os.open(
                self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644
            )

    def write(self, event: str, **payload: Any):
        if not self.enabled or self._fd is None:
            return
        with self._lock:
            self._seq += 1
            row = {
                "schema": "sglang_kv_diag_v2",
                "pid": os.getpid(),
                "seq": self._seq,
                "event": event,
                "time_monotonic_s": time.monotonic(),
                "time_unix_s": time.time(),
                **payload,
            }
            os.write(
                self._fd,
                (json.dumps(row, separators=(",", ":")) + "\n").encode(),
            )

    @staticmethod
    def _state(cache: Any) -> dict[str, Optional[int]]:
        allocator = getattr(cache, "token_to_kv_pool_allocator", None)
        available = (
            int(allocator.available_size())
            if allocator is not None and hasattr(allocator, "available_size")
            else None
        )
        return {
            "kv_available_tokens": available,
            "kv_evictable_tokens": int(cache.evictable_size()),
            "kv_protected_tokens": int(cache.protected_size()),
        }

    @staticmethod
    def _node_hashes(cache: Any, node: Any) -> list[str]:
        if node.hash_value is None:
            node.hash_value = compute_node_hash_values(node, cache.page_size)
        return node.hash_value

    def record_reset(self, cache: Any):
        self.write("cache_reset", page_size=cache.page_size, **self._state(cache))

    def record_store(self, cache: Any, node: Any, medium: str):
        self.write(
            "cache_store",
            medium=medium,
            page_size=cache.page_size,
            block_hashes=self._node_hashes(cache, node),
            stored_tokens=len(node.key),
            **self._state(cache),
        )

    def record_remove(self, cache: Any, node: Any, medium: str):
        self.write(
            "cache_evict",
            medium=medium,
            page_size=cache.page_size,
            block_hashes=self._node_hashes(cache, node),
            evicted_tokens=len(node.key),
            age_since_access_ms=max(
                0.0, (time.monotonic() - float(node.last_access_time)) * 1000.0
            ),
            **self._state(cache),
        )

    def record_evict_boundary(self, cache: Any, event: str, num_tokens: int):
        self.write(event, num_tokens=int(num_tokens), **self._state(cache))

    def record_match(self, cache: Any, req: Any, key: Any, matched_tokens: int):
        key, _ = key.maybe_to_bigram_view(cache.is_eagle)
        key = key.page_aligned(cache.page_size)
        hashes = []
        prior_hash = None
        for start in range(0, len(key), cache.page_size):
            prior_hash = key.hash_page(
                start, min(start + cache.page_size, len(key)), prior_hash
            )
            hashes.append(prior_hash)
        self.write(
            "request_match",
            request_id=str(req.rid),
            page_size=cache.page_size,
            prompt_tokens=len(key),
            matched_tokens=int(matched_tokens),
            block_hashes=hashes,
            extra_key_present=key.extra_key is not None,
            **self._state(cache),
        )


def init_kv_diagnostic_trace() -> KVDiagnosticTrace:
    return KVDiagnosticTrace()
