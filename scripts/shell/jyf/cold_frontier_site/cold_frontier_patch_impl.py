"""Runtime-only SGLang SWA radix-cache frontier tracer.

Loaded as sitecustomize from an isolated PYTHONPATH. It monkeypatches the
installed SGLang process in memory and never edits the shared installation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import time
from collections import deque
from pathlib import Path


TRACE_DIR = os.environ.get("COLD_FRONTIER_TRACE_DIR")
if TRACE_DIR:
    from sglang.srt.mem_cache import swa_radix_cache as swa

    SAMPLE_EVERY = max(1, int(os.environ.get("COLD_FRONTIER_SAMPLE_EVERY", "1")))

    def _write(cache, row):
        handle = getattr(cache, "_cf_handle", None)
        if handle is None:
            return
        row.setdefault("pid", os.getpid())
        row.setdefault("wall_s", time.time())
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")

    def _req_meta(req):
        if req is None:
            return {"sid": "", "turn": 0, "traffic": ""}
        sp = getattr(req, "sampling_params", None)
        custom = getattr(sp, "custom_params", None) if sp is not None else None
        custom = custom if isinstance(custom, dict) else {}
        try:
            turn = int(custom.get("turn_idx", 0) or 0)
        except Exception:
            turn = 0
        return {
            "sid": str(custom.get("session_id") or getattr(req, "rid", "") or ""),
            "turn": turn,
            "traffic": str(custom.get("traffic_class") or ""),
        }

    def _extra_bytes(extra):
        return repr(extra).encode("utf-8", errors="replace")

    def _update_int(hasher, value):
        try:
            hasher.update(struct.pack("<q", int(value)))
        except Exception:
            hasher.update(repr(value).encode("utf-8", errors="replace"))

    def _node_tokens(node):
        chain = []
        cur = node
        while cur is not None and getattr(cur, "parent", None) is not None:
            chain.append(cur)
            cur = cur.parent
        chain.reverse()
        return chain

    def _node_digest(node):
        cached = getattr(node, "_cf_digest", None)
        if cached:
            return cached
        chain = _node_tokens(node)
        extra = getattr(getattr(chain[0], "key", None), "extra_key", None) if chain else None
        h = hashlib.blake2b(digest_size=16)
        h.update(_extra_bytes(extra)); h.update(b"|")
        length = 0
        for part in chain:
            vals = getattr(getattr(part, "key", None), "token_ids", [])
            for value in vals:
                _update_int(h, value); length += 1
        digest = h.hexdigest()
        node._cf_digest = digest
        node._cf_path_tokens = length
        return digest

    def _track_demands(cache, key):
        tracked = getattr(cache, "_cf_tracked", None)
        if not tracked:
            return
        vals = getattr(key, "token_ids", [])
        lengths = sorted(length for length in tracked if length <= len(vals))
        if not lengths:
            return
        h = hashlib.blake2b(digest_size=16)
        h.update(_extra_bytes(getattr(key, "extra_key", None))); h.update(b"|")
        wanted = set(lengths)
        for pos, value in enumerate(vals, 1):
            _update_int(h, value)
            if pos in wanted:
                digest = h.copy().hexdigest()
                if digest in tracked[pos]:
                    _write(cache, {"kind": "demand", "req_seq": cache._cf_req_seq,
                                   "digest": digest, "path_tokens": pos})
            if pos >= lengths[-1]:
                break

    def _path_nodes(node, root):
        out = []
        while node is not None and node is not root:
            out.append(node); node = node.parent
        out.reverse()
        return out

    def _frontier_full(cache):
        out = []
        node = cache.full_lru_list.get_leaf_lru_no_lock()
        while cache.full_lru_list.in_list(node):
            out.append(node)
            node = cache.full_lru_list.get_prev_leaf_no_lock(node)
        return out

    def _frontier_swa(cache):
        out = []
        node = cache.swa_lru_list.get_lru_no_lock()
        while cache.swa_lru_list.in_list(node):
            out.append(node)
            node = cache.swa_lru_list.get_prev_no_lock(node)
        return out

    def _candidate(cache, node, frontier, rank, total):
        digest = _node_digest(node)
        path_tokens = int(getattr(node, "_cf_path_tokens", 0))
        parent = getattr(node, "parent", None)
        siblings = list(getattr(parent, "children", {}).values()) if parent is not None else []
        created_req = int(getattr(node, "_cf_created_req", cache._cf_req_seq))
        created_wall = float(getattr(node, "_cf_created_wall", time.time()))
        gaps = list(getattr(node, "_cf_gap_reqs", ()))
        cache._cf_tracked.setdefault(path_tokens, set()).add(digest)
        node_key = getattr(node, "key", None)
        node_value = getattr(node, "value", None)
        return {
            "digest": digest,
            "frontier": frontier,
            "cold": int(getattr(node, "_cf_hits", 0) == 0),
            "hits": int(getattr(node, "_cf_hits", 0)),
            "recent_gap_req": int(gaps[-1]) if gaps else -1,
            "node_tokens": int(len(node_key)) if node_key is not None else 0,
            "kv_tokens": int(len(node_value)) if node_value is not None else 0,
            "path_tokens": path_tokens,
            "depth": len(_node_tokens(node)),
            "age_requests": max(0, cache._cf_req_seq - created_req),
            "age_s": max(0.0, time.time() - created_wall),
            "lru_rank": rank,
            "lru_frac": rank / max(total - 1, 1),
            "parent_hits": int(getattr(parent, "_cf_hits", 0)) if parent is not None else 0,
            "siblings": max(0, len(siblings) - 1),
            "warm_siblings": sum(int(getattr(s, "_cf_hits", 0) > 0) for s in siblings if s is not node),
            "owner_turn": int(getattr(node, "_cf_owner_turn", 0)),
            "owner_traffic": str(getattr(node, "_cf_owner_traffic", "")),
        }

    original_node_init = swa.TreeNode.__init__
    def node_init(self, *args, **kwargs):
        original_node_init(self, *args, **kwargs)
        self._cf_hits = 0
        self._cf_created_req = 0
        self._cf_created_wall = time.time()
        self._cf_last_hit_req = None
        self._cf_gap_reqs = deque(maxlen=8)
        self._cf_owner_turn = 0
        self._cf_owner_traffic = ""
        self._cf_digest = None
        self._cf_path_tokens = 0
    swa.TreeNode.__init__ = node_init

    original_cache_init = swa.SWARadixCache.__init__
    def cache_init(self, *args, **kwargs):
        original_cache_init(self, *args, **kwargs)
        out = Path(TRACE_DIR)
        out.mkdir(parents=True, exist_ok=True)
        self._cf_req_seq = 0
        self._cf_evict_seq = 0
        self._cf_tracked = {}
        self._cf_insert_meta = None
        self._cf_in_evict = False
        self._cf_handle = (out / f"frontier_pid{os.getpid()}_{id(self)}.jsonl").open("a", buffering=1)
        _write(self, {"kind": "init", "page_size": int(self.page_size),
                      "sliding_window_size": int(self.sliding_window_size)})
    swa.SWARadixCache.__init__ = cache_init

    original_match = swa.SWARadixCache.match_prefix
    def match_prefix(self, params):
        req = getattr(params, "req", None)
        genuine = req is not None
        if genuine:
            self._cf_req_seq += 1
            _track_demands(self, params.key)
        result = original_match(self, params)
        if genuine:
            meta = _req_meta(req)
            for node in _path_nodes(result.last_device_node, self.root_node):
                last = getattr(node, "_cf_last_hit_req", None)
                if last is not None and self._cf_req_seq > last:
                    node._cf_gap_reqs.append(self._cf_req_seq - last)
                node._cf_last_hit_req = self._cf_req_seq
                node._cf_hits = int(getattr(node, "_cf_hits", 0)) + 1
            _write(self, {"kind": "request", "req_seq": self._cf_req_seq,
                          "sid": meta["sid"], "turn": meta["turn"],
                          "traffic": meta["traffic"]})
        return result
    swa.SWARadixCache.match_prefix = match_prefix

    def _wrap_cache_method(name):
        original = getattr(swa.SWARadixCache, name)
        def wrapped(self, req, *args, **kwargs):
            self._cf_insert_meta = _req_meta(req)
            try:
                return original(self, req, *args, **kwargs)
            finally:
                self._cf_insert_meta = None
        setattr(swa.SWARadixCache, name, wrapped)
    _wrap_cache_method("cache_finished_req")
    _wrap_cache_method("cache_unfinished_req")

    original_add = swa.SWARadixCache._add_new_node
    def add_new_node(self, *args, **kwargs):
        node = original_add(self, *args, **kwargs)
        meta = self._cf_insert_meta or {}
        node._cf_created_req = self._cf_req_seq
        node._cf_created_wall = time.time()
        node._cf_owner_turn = int(meta.get("turn", 0))
        node._cf_owner_traffic = str(meta.get("traffic", ""))
        return node
    swa.SWARadixCache._add_new_node = add_new_node

    original_split = swa.SWARadixCache._split_node
    def split_node(self, key, child, split_len):
        old_digest = getattr(child, "_cf_digest", None)
        new_node = original_split(self, key, child, split_len)
        for attr in ("_cf_hits", "_cf_created_req", "_cf_created_wall", "_cf_last_hit_req",
                     "_cf_owner_turn", "_cf_owner_traffic"):
            setattr(new_node, attr, getattr(child, attr, getattr(new_node, attr, None)))
        new_node._cf_gap_reqs = deque(getattr(child, "_cf_gap_reqs", ()), maxlen=8)
        new_node._cf_digest = None
        child._cf_digest = old_digest  # child's complete path is unchanged by a split
        return new_node
    swa.SWARadixCache._split_node = split_node

    original_delete = swa.SWARadixCache._delete_leaf
    def delete_leaf(self, node):
        if getattr(self, "_cf_in_evict", False):
            _write(self, {"kind": "victim", "evict_seq": self._cf_evict_seq,
                          "victim_type": "full_delete", **_candidate(self, node, "victim", 0, 1)})
        return original_delete(self, node)
    swa.SWARadixCache._delete_leaf = delete_leaf

    original_tombstone = swa.SWARadixCache._tombstone_internal_node
    def tombstone(self, node):
        if getattr(self, "_cf_in_evict", False):
            _write(self, {"kind": "victim", "evict_seq": self._cf_evict_seq,
                          "victim_type": "swa_tombstone", **_candidate(self, node, "victim", 0, 1)})
        return original_tombstone(self, node)
    swa.SWARadixCache._tombstone_internal_node = tombstone

    original_evict = swa.SWARadixCache.evict
    def evict(self, params):
        self._cf_evict_seq += 1
        full = _frontier_full(self)
        swa_nodes = _frontier_swa(self)
        def summary(nodes):
            cold = [n for n in nodes if int(getattr(n, "_cf_hits", 0)) == 0]
            return {
                "nodes": len(nodes), "tokens": sum(len(n.value) for n in nodes),
                "cold_nodes": len(cold), "cold_tokens": sum(len(n.value) for n in cold),
            }
        row = {"kind": "frontier", "evict_seq": self._cf_evict_seq,
               "req_seq": self._cf_req_seq, "requested_full": int(params.num_tokens),
               "requested_swa": int(params.swa_num_tokens), "full": summary(full),
               "swa": summary(swa_nodes)}
        if self._cf_evict_seq % SAMPLE_EVERY == 0:
            row["candidates"] = [
                _candidate(self, node, "full", rank, len(full)) for rank, node in enumerate(full)
            ] + [
                _candidate(self, node, "swa", rank, len(swa_nodes)) for rank, node in enumerate(swa_nodes)
            ]
        _write(self, row)
        self._cf_in_evict = True
        try:
            return original_evict(self, params)
        finally:
            self._cf_in_evict = False
    swa.SWARadixCache.evict = evict
