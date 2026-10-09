"""Read-only, rank-zero observation of the official UnifiedRadixCache.

The observer never calls a cache match, changes a node, or chooses a victim.
Its historical index retains *actually materialized* Full/SWA pages since
the most recent flush. Only hashes and structural metadata are emitted.
"""

from __future__ import annotations

from array import array
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def page_chain(tokens, page_size, extra_key=None):
    namespace = hashlib.sha256(b"agentkv-pages-v2\0" + repr(extra_key).encode()).hexdigest()
    previous = namespace
    pages = []
    for start in range(0, len(tokens) - page_size + 1, page_size):
        values = array("i", tokens[start:start + page_size])
        if sys.byteorder != "little":
            values.byteswap()
        previous = hashlib.sha256(bytes.fromhex(previous) + values.tobytes()).hexdigest()
        pages.append(previous)
    return namespace, pages


def history_match(pages, full_history, swa_history, page_size, window):
    """Page-level history availability; no future demand or capacity oracle."""
    full = joint = 0
    consecutive = float("inf")
    for page in pages:
        if page not in full_history:
            break
        full += page_size
        if page not in swa_history:
            consecutive = 0
        else:
            consecutive += page_size
            if consecutive >= window:
                joint = full
    return full, joint


class MechanismObserver:
    def __init__(self, cache):
        destination = os.environ.get("AGENTKV_MECHANISM_DIR")
        rank = 0
        if destination:
            import torch
            if torch.distributed.is_initialized():
                rank = torch.distributed.get_rank()
        self.enabled = bool(destination) and rank == 0
        self.cache = cache
        self.seq = self.reclaim_seq = 0
        self.reclaim_id = None
        self.driver = None
        self.step = 0
        self.identities = {}
        self.defined_pages = set()
        self.full_history = set()
        self.swa_history = set()
        self.last_free = {"full": {}, "swa": {}}
        self.stream = None
        if self.enabled:
            from sglang.srt.mem_cache.unified_cache_components.tree_component import ComponentType
            self.full_ct, self.swa_ct = ComponentType.FULL, ComponentType.SWA
            self.components = [ct.name for ct in cache.tree_components]
            self.supported = set(cache.tree_components) == {self.full_ct, self.swa_ct}
            Path(destination).mkdir(parents=True, exist_ok=True)
            self.stream = (Path(destination) / f"events.rank0.pid{os.getpid()}.jsonl").open("x", buffering=1024 * 1024)
            self.emit("observer_start", rank=rank, components=self.components,
                      full_swa_history_supported=self.supported, page_size=cache.page_size,
                      native_decisions_unchanged=True)

    def emit(self, kind, **fields):
        if not self.enabled:
            return None
        self.seq += 1
        self.stream.write(json.dumps({"schema": "agentkv.mechanism.v2", "event_seq": self.seq,
                                     "time_unix_ns": time.time_ns(), "event_type": kind,
                                     **fields}, separators=(",", ":")) + "\n")
        if self.seq % 128 == 0 or kind in {"flush", "reclaim_end", "request_commit"}:
            self.stream.flush()
        return self.seq

    def define(self, tokens, extra_key):
        namespace, pages = page_chain(tokens, self.cache.page_size, extra_key)
        new = []
        previous = namespace
        for depth, page in enumerate(pages, 1):
            if page not in self.defined_pages:
                self.defined_pages.add(page)
                new.append([page, previous, depth])
            previous = page
        if new:
            self.emit("page_definitions", namespace=namespace, pages=new)
        return namespace, pages

    def identity(self, node):
        if node is None or node.parent is None:
            return {"node_id": None, "end_page": None, "path_tokens": 0, "pages": ()}
        if node.id not in self.identities:
            parts = []
            current = node
            extra_key = node.key.extra_key
            while current.parent is not None:
                parts.append(current.key.token_ids)
                current = current.parent
            tokens = [token for part in reversed(parts) for token in part]
            namespace, pages = self.define(tokens, extra_key)
            self.identities[node.id] = {"node_id": int(node.id), "namespace": namespace,
                                        "end_page": pages[-1] if pages else None,
                                        "path_tokens": len(tokens), "pages": tuple(pages)}
        return self.identities[node.id]

    def segment_pages(self, node):
        identity = self.identity(node)
        count = len(node.key) // self.cache.page_size
        return identity["pages"][-count:] if count else ()

    def snapshot(self, node, score=None):
        identity = self.identity(node)
        parent = self.identity(node.parent)
        full = node.component_data[self.full_ct]
        swa = node.component_data[self.swa_ct]
        return {k: v for k, v in identity.items() if k != "pages"} | {
            "parent_node_id": parent["node_id"], "parent_end_page": parent["end_page"],
            "logical_tokens": len(node.key), "full_tokens": 0 if full.value is None else len(full.value),
            "swa_tokens": 0 if swa.value is None else len(swa.value),
            "full_lock_ref": int(full.lock_ref), "swa_lock_ref": int(swa.lock_ref),
            "children": len(node.children), "full_leaf": node in self.cache.evictable_device_leaves,
            "hit_count": int(node.hit_count), "last_access_time": float(node.last_access_time),
            "policy_score": score,
        }

    def walk(self, key):
        """Inspect the current tree without splitting or refreshing anything."""
        node = self.cache.root_node
        rest = key
        depth = 0
        while len(rest):
            child = node.children.get(rest.child_key(self.cache.page_size))
            if child is None or child.evicted:
                break
            count = child.key.match(rest, page_size=self.cache.page_size)
            if count <= 0:
                break
            yield child, depth, count
            depth += count
            if count < len(child.key):
                break
            rest = rest[count:]
            node = child

    def flush(self):
        if not self.enabled:
            return
        self.full_history.clear()
        self.swa_history.clear()
        self.last_free = {"full": {}, "swa": {}}
        self.emit("flush", historical_index_reset=True)

    def inserted(self, key, params, result):
        if not self.enabled:
            return
        _, pages = self.define(key.token_ids, key.extra_key)
        nodes = []
        for node, depth, count in self.walk(key):
            snapshot = self.snapshot(node)
            nodes.append(snapshot)
            segment = pages[depth // self.cache.page_size:(depth + count) // self.cache.page_size]
            for pool, history in (("full", self.full_history), ("swa", self.swa_history)):
                if snapshot[pool + "_tokens"]:
                    history.update(segment)
                    for page in segment:
                        self.last_free[pool].pop(page, None)
        self.emit("insert", key_end_page=pages[-1] if pages else None, tokens=len(key),
                  prior_present_tokens=int(result.prefix_len), swa_evicted_seqlen=int(params.swa_evicted_seqlen),
                  chunked=bool(params.chunked), nodes=nodes)

    def matched(self, key, params, result):
        if not self.enabled:
            return
        req = params.req
        if req is None:
            return
        namespace, pages = self.define(key.token_ids, key.extra_key)
        window = int(self.cache.sliding_window_size or 0)
        hist_full, hist_joint = history_match(pages, self.full_history, self.swa_history,
                                             self.cache.page_size, window)
        full = joint = 0
        consecutive = float("inf")
        nodes = []
        for node, depth, count in self.walk(key):
            snapshot = self.snapshot(node)
            nodes.append(snapshot)
            full = depth + count
            if not snapshot["swa_tokens"]:
                consecutive = 0
            else:
                consecutive += count
                if consecutive >= window:
                    joint = full
        actual = len(result.device_indices)
        missing = Counter()
        for page in pages[full // self.cache.page_size:hist_joint // self.cache.page_size]:
            cause = self.last_free["full"].get(page)
            missing[json.dumps(cause, sort_keys=True) if cause else "unobserved_free"] += self.cache.page_size
        swa_holes = []
        for node in nodes:
            if node["swa_tokens"] == 0:
                cause = self.last_free["swa"].get(node["end_page"])
                swa_holes.append({"end_page": node["end_page"], "path_tokens": node["path_tokens"], "last_free": cause})
        self.emit("match", request_id=str(req.rid), namespace=namespace,
                  key_end_page=pages[-1] if pages else None, requested_tokens=len(key),
                  origin_input_tokens=len(req.origin_input_ids), output_tokens=len(req.output_ids),
                  native_matched_tokens=actual, inspected_full_tokens=full,
                  inspected_joint_tokens=joint, inspected_match_agrees=(joint == actual) if self.supported else None,
                  historical_full_tokens=hist_full, historical_joint_tokens=hist_joint,
                  history_shortfall_tokens=max(0, hist_joint - actual),
                  missing_full_cause_tokens=dict(missing), swa_holes=swa_holes, resident_path=nodes)

    def commit(self, req, committed_tokens, page_aligned_tokens, finished):
        if self.enabled:
            self.emit("request_commit", request_id=str(req.rid), finished=bool(finished),
                      committed_tokens=int(committed_tokens), page_aligned_tokens=int(page_aligned_tokens))

    def lock(self, node, action):
        if self.enabled and node is not None:
            self.emit(action, anchor=self.snapshot(node))

    def split(self, parent, child):
        if self.enabled:
            self.emit("split", parent=self.snapshot(parent), child=self.snapshot(child))

    def begin_reclaim(self, params):
        if not self.enabled:
            return
        self.reclaim_seq += 1
        self.reclaim_id = self.reclaim_seq
        self.emit("reclaim_begin", reclaim_id=self.reclaim_id,
                  requested_full_tokens=int(params.num_tokens), requested_swa_tokens=int(params.swa_num_tokens))

    def begin_drive(self, pool, requested, tracker, candidates):
        if not self.enabled:
            return
        self.driver = pool
        self.step = 0
        ct = self.full_ct if pool == "full" else self.swa_ct
        active = tracker[ct] < requested
        snapshots = []
        if active:
            if pool == "full":
                snapshots = [self.snapshot(node, score) for score, node in candidates]
            else:
                lru = self.cache.lru_lists[self.swa_ct]
                node = lru.get_lru_no_lock()
                while node is not None:
                    snapshots.append(self.snapshot(node, len(snapshots)))
                    node = lru.get_prev_no_lock(node)
        self.emit("drive_begin", reclaim_id=self.reclaim_id, pool=pool, requested_tokens=int(requested),
                  tracker_start=self.tracker(tracker), active=active,
                  candidate_coverage_complete=True, candidates=snapshots,
                  evictable_tokens={ct.name: int(v) for ct, v in self.cache.component_evictable_size_.items()},
                  protected_tokens={ct.name: int(v) for ct, v in self.cache.component_protected_size_.items()})

    def tracker(self, tracker):
        return {"full": int(tracker[self.full_ct]), "swa": int(tracker.get(self.swa_ct, 0))}

    def before_step(self, node, tracker):
        if not self.enabled:
            return None
        self.step += 1
        return {"victim": self.snapshot(node), "tracker": self.tracker(tracker), "parent": node.parent}

    def after_step(self, before, tracker):
        if before is None:
            return
        after = self.tracker(tracker)
        parent = before["parent"]
        exposed = parent is not None and parent in self.cache.evictable_device_leaves
        self.emit("victim_step", reclaim_id=self.reclaim_id, pool=self.driver, step=self.step,
                  victim=before["victim"],
                  released={pool: after[pool] - before["tracker"][pool] for pool in after},
                  parent_exposed=exposed, exposed_parent=self.snapshot(parent) if exposed else None)

    def freed(self, node, pool, freed_tokens):
        if not self.enabled or freed_tokens <= 0:
            return
        snapshot = self.snapshot(node)
        event = self.emit("component_free", reclaim_id=self.reclaim_id, driver=self.driver,
                          step=self.step, pool=pool, freed_tokens=int(freed_tokens), node=snapshot)
        cause = {"event_seq": event, "reclaim_id": self.reclaim_id, "driver": self.driver, "step": self.step}
        for page in self.segment_pages(node):
            self.last_free[pool][page] = cause

    def end_drive(self, pool, requested, tracker):
        if self.enabled:
            self.emit("drive_end", reclaim_id=self.reclaim_id, pool=pool,
                      requested_tokens=int(requested), tracker_end=self.tracker(tracker), steps=self.step)

    def end_reclaim(self, tracker):
        if self.enabled:
            self.emit("reclaim_end", reclaim_id=self.reclaim_id, released=self.tracker(tracker))
            self.reclaim_id = self.driver = None
