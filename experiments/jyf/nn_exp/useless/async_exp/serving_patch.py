"""Isolated real SGLang LRU/synchronous/asynchronous experimental policies.

Only TP rank 0 predicts. Legacy sync/async broadcast available scores at eviction
entry without waiting for unfinished worker inference. sync_fill checks and
synchronously fills the current shortlist before every victim selection, then
broadcasts complete scores. All modes retain upstream allocation/free logic;
LRU runs the original eviction unchanged.
"""
import hashlib
import inspect
import json
import os
from pathlib import Path
import textwrap
import time

import numpy as np
import torch
from sglang.srt.mem_cache import swa_radix_cache as swa
from predictor import Model, Node, Worker, predict_sync, reuse_probability

MODE = os.environ["ASYNC_SERVING_MODE"]
assert MODE in ("lru", "sync", "async", "sync_fill")
OUT = Path(os.environ["ASYNC_SERVING_OUT"])
CHECKPOINT = os.environ.get("ASYNC_CHECKPOINT", "/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/uniform_mlp_exp/k10/checkpoints/seed_42.pt")
SHORTLIST = int(os.environ.get("ASYNC_SHORTLIST", "16"))


def emit(cache, row):
    row["wall_s"] = time.time()
    cache._ap_log.write(json.dumps(row, separators=(",", ":")) + "\n")


def path_nodes(cache, node):
    nodes = []
    while node is not None and node is not cache.root_node:
        nodes.append(node)
        node = node.parent
    return nodes


def touch(cache, node):
    if not getattr(cache, "_ap_leader", False) or MODE == "lru" or node is None or node is cache.root_node:
        return
    for state in getattr(node, "_ap_states", {}).values():
        state.invalidate()
    cache._ap_dirty[node.id] = node


def frontier(cache, kind):
    ls = cache.full_lru_list if kind == "full" else cache.swa_lru_list
    get = ls.get_leaf_lru_no_lock if kind == "full" else ls.get_lru_no_lock
    prev = ls.get_prev_leaf_no_lock if kind == "full" else ls.get_prev_no_lock
    node = get()
    out = []
    while ls.in_list(node):
        out.append(node)
        node = prev(node)
    return out


def snapshot(cache, node, kind, frac):
    chain = path_nodes(cache, node)
    parent = node.parent
    siblings = list(parent.children.values())
    return dict(node_tokens=len(node.key), path_tokens=sum(len(n.key) for n in chain),
                depth=len(chain), age_requests=max(0, cache._ap_seq - getattr(node, "_ap_created", 0)),
                lru_frac=frac, parent_hits=getattr(parent, "_ap_hits", 0),
                siblings=max(0, len(siblings)-1),
                warm_siblings=sum(getattr(n, "_ap_hits", 0) > 0 for n in siblings if n is not node),
                owner_turn=getattr(node, "_ap_turn", 0), owner_traffic=getattr(node, "_ap_traffic", ""),
                cold=int(getattr(node, "_ap_hits", 0) == 0), hits=getattr(node, "_ap_hits", 0),
                recent_gap_req=getattr(node, "_ap_gap", -1), frontier=kind)


def flush(cache):
    if MODE == "lru" or not cache._ap_leader:
        return 0
    # Only dirty nodes receive new episodes. Traversal here computes the existing
    # checkpoint's LRU-fraction feature at observation time, common to both modes.
    ranks = {}
    for kind in ("full", "swa"):
        ns = frontier(cache, kind)
        ranks[kind] = {n.id: i/max(1, len(ns)-1) for i, n in enumerate(ns)}
    dirty, cache._ap_dirty = cache._ap_dirty, {}
    ts = []
    for node in dirty.values():
        if not hasattr(node, "_ap_states"):
            node._ap_states = {k: Node((node.id, k)) for k in ("full", "swa")}
        for kind in ("full", "swa"):
            if node.id in ranks[kind]:
                raw = snapshot(cache, node, kind, ranks[kind][node.id])
                ts.append(node._ap_states[kind].begin(raw, cache._ap_seq))
    if ts:
        if MODE == "async":
            for t in ts:
                cache._ap_worker.submit(t)
        else:
            predict_sync(cache._ap_model, ts)
    return len(ts)


old_init = swa.SWARadixCache.__init__
def cache_init(self, *args, **kwargs):
    old_init(self, *args, **kwargs)
    if os.environ.get("ASYNC_TEST_MODE"):
        self._ap_group = None
        self._ap_rank = 0
    else:
        from sglang.srt.distributed.parallel_state import get_tp_group
        self._ap_group = get_tp_group()
        self._ap_rank = self._ap_group.rank_in_group
    self._ap_leader = self._ap_rank == 0
    self._ap_seq = 0
    self._ap_finished = 0
    self._ap_evict = 0
    self._ap_dirty = {}
    self._ap_meta = {}
    self._ap_model = None
    self._ap_worker = None
    OUT.mkdir(parents=True, exist_ok=True)
    self._ap_log = (OUT / f"rank{self._ap_rank}_pid{os.getpid()}.jsonl").open("a", buffering=1)
    self.full_lru_list._ap_cache = self
    self.swa_lru_list._ap_cache = self
    if self._ap_leader and MODE != "lru":
        self._ap_model = Model(CHECKPOINT)
        for _ in range(20):
            self._ap_model.predict([{}] * 64)
        if MODE == "async":
            self._ap_worker = Worker(self._ap_model, batch_size=64, capacity=4096)
    emit(self, dict(kind="init", mode=MODE, rank=self._ap_rank, page_size=self.page_size,
                    sliding_window_size=self.sliding_window_size,
                    checkpoint=CHECKPOINT if MODE != "lru" else None))
swa.SWARadixCache.__init__ = cache_init


def wrap_list(name):
    original = getattr(swa.LRUList, name)
    def method(self, node, *args, **kwargs):
        cache = getattr(self, "_ap_cache", None)
        if cache:
            if name == "reset_node_and_parents_mru":
                for n in path_nodes(cache, node):
                    touch(cache, n)
            else:
                touch(cache, node)
                touch(cache, node.parent)
        return original(self, node, *args, **kwargs)
    setattr(swa.LRUList, name, method)
for name in ("insert_mru", "remove_node", "reset_node_mru", "reset_node_and_parents_mru"):
    wrap_list(name)


old_match = swa.SWARadixCache.match_prefix
def match(self, params):
    req = getattr(params, "req", None)
    if req is not None:
        self._ap_seq += 1
    result = old_match(self, params)
    if req is not None and self._ap_leader and MODE != "lru":
        for n in path_nodes(self, result.last_device_node):
            last = getattr(n, "_ap_last_hit", None)
            if last is not None and self._ap_seq > last:
                n._ap_gap = self._ap_seq - last
            n._ap_last_hit = self._ap_seq
            n._ap_hits = getattr(n, "_ap_hits", 0) + 1
    return result
swa.SWARadixCache.match_prefix = match


old_add = swa.SWARadixCache._add_new_node
def add(self, *args, **kwargs):
    n = old_add(self, *args, **kwargs)
    n._ap_created = self._ap_seq
    n._ap_turn = int(self._ap_meta.get("turn_idx", 0) or 0)
    n._ap_traffic = str(self._ap_meta.get("traffic_class", ""))
    touch(self, n)
    return n
swa.SWARadixCache._add_new_node = add


old_split = swa.SWARadixCache._split_node
def split(self, key, child, split_len):
    n = old_split(self, key, child, split_len)
    for attr in ("_ap_created", "_ap_turn", "_ap_traffic", "_ap_hits", "_ap_gap", "_ap_last_hit"):
        if hasattr(child, attr):
            setattr(n, attr, getattr(child, attr))
    touch(self, n)
    touch(self, child)
    return n
swa.SWARadixCache._split_node = split


def wrap_lock(name):
    original = getattr(swa.SWARadixCache, name)
    def method(self, node, *args, **kwargs):
        for n in path_nodes(self, node):
            touch(self, n)
        return original(self, node, *args, **kwargs)
    setattr(swa.SWARadixCache, name, method)
for name in ("inc_lock_ref", "dec_lock_ref", "dec_swa_lock_only"):
    wrap_lock(name)


def wrap_request(name):
    original = getattr(swa.SWARadixCache, name)
    def method(self, req, *args, **kwargs):
        start = time.perf_counter_ns()
        custom = getattr(getattr(req, "sampling_params", None), "custom_params", None)
        self._ap_meta = custom if isinstance(custom, dict) else {}
        try:
            result = original(self, req, *args, **kwargs)
        finally:
            self._ap_meta = {}
        if name == "cache_finished_req":
            original_end = time.perf_counter_ns()
            count = flush(self)
            end = time.perf_counter_ns()
            self._ap_finished += 1
            if self._ap_leader:
                worker = self._ap_worker
                emit(self, dict(kind="finish", index=self._ap_finished,
                                original_us=(original_end-start)/1000,
                                prediction_hook_us=(end-original_end)/1000,
                                total_us=(end-start)/1000, submitted=count,
                                dropped=worker.dropped if worker else 0,
                                worker_error=worker.error if worker else None,
                                batches=len(worker.batch_sizes) if worker else 0))
        return result
    setattr(swa.SWARadixCache, name, method)
for name in ("cache_finished_req", "cache_unfinished_req"):
    wrap_request(name)


def node_signature(nodes):
    return [(n.id, len(n.key)) for n in nodes]


def choose_fill(cache, kind, nodes):
    """Guarantee scores for every current candidate, including new parents."""
    started = time.perf_counter_ns()
    payload = None
    if cache._ap_leader:
        scores, missing, reasons = {}, [], {}
        for n in nodes:
            state = getattr(n, "_ap_states", {}).get(kind)
            ticket = state.prediction_state if state else None
            result = state.read() if state else None
            score = None
            reason = "missing_or_invalidated"
            if result is not None:
                score = reuse_probability(result.hazard, cache._ap_seq-ticket.episode_start, 20)
                reason = "outside_horizon" if score is None else "nonfinite"
            if score is None or not np.isfinite(score):
                missing.append(n)
                reasons[reason] = reasons.get(reason, 0) + 1
            else:
                scores[n.id] = score
        inference_us = 0.0
        if missing:
            current = frontier(cache, kind)
            ranks = {n.id: i/max(1, len(current)-1) for i, n in enumerate(current)}
            ts = []
            for n in missing:
                if not hasattr(n, "_ap_states"):
                    n._ap_states = {k: Node((n.id, k)) for k in ("full", "swa")}
                # A refresh is a new prediction observation at now. Do not attach
                # current features to the old prediction's time origin.
                ts.append(n._ap_states[kind].begin(snapshot(cache, n, kind, ranks[n.id]), cache._ap_seq))
            t0 = time.perf_counter_ns()
            predict_sync(cache._ap_model, ts)
            inference_us = (time.perf_counter_ns()-t0)/1000
            for n, t in zip(missing, ts):
                score = reuse_probability(t.result.hazard, 0, 20)
                assert score is not None and np.isfinite(score), "invalid fresh MLP score"
                scores[n.id] = score
        assert len(scores) == len(nodes)
        payload = (node_signature(nodes), scores, len(missing), reasons, inference_us)
    if cache._ap_group is not None and cache._ap_group.world_size > 1:
        box = [payload]
        torch.distributed.broadcast_object_list(box, src=cache._ap_group.ranks[0], group=cache._ap_group.cpu_group)
        payload = box[0]
    signature, scores, filled, reasons, inference_us = payload
    assert signature == node_signature(nodes), "TP shortlist mismatch during synchronous fill"
    cache._ap_fill_nodes += filled
    cache._ap_fill_batches += int(filled > 0)
    cache._ap_fill_inference_us += inference_us
    cache._ap_fill_selection_us += (time.perf_counter_ns()-started)/1000
    for reason, count in reasons.items():
        cache._ap_fill_reasons[reason] = cache._ap_fill_reasons.get(reason, 0) + count
    chosen = min(nodes, key=lambda n: scores[n.id])
    cache._ap_decisions.append((kind, chosen.id, len(chosen.key), True, chosen.id != nodes[0].id))
    return chosen


def choose(cache, kind, original):
    ls = cache.full_lru_list if kind == "full" else cache.swa_lru_list
    get = ls.get_leaf_lru_no_lock if kind == "full" else ls.get_lru_no_lock
    prev = ls.get_prev_leaf_no_lock if kind == "full" else ls.get_prev_no_lock
    nodes = []
    x = get()
    while ls.in_list(x) and len(nodes) < SHORTLIST:
        nodes.append(x)
        x = prev(x)
    if not nodes:
        return original
    if MODE == "sync_fill":
        return choose_fill(cache, kind, nodes)
    score_map = cache._ap_plan[kind]
    usable = all(n.id in score_map for n in nodes)
    chosen = min(nodes, key=lambda n: score_map[n.id]) if usable else nodes[0]
    cache._ap_decisions.append((kind, chosen.id, len(chosen.key), usable, chosen.id != nodes[0].id))
    return chosen


original_evict = swa.SWARadixCache.evict
# Keep upstream memory management verbatim and replace only selection.
source = textwrap.dedent(inspect.getsource(original_evict))
source = source.replace("def evict(", "def predicted_evict(", 1)
full_loop = "while full_num_evicted < full_num_tokens and self.full_lru_list.in_list(x):"
swa_loop = "while swa_num_evicted < swa_num_tokens and (self.swa_lru_list.in_list(x)):"
assert source.count(full_loop) == source.count(swa_loop) == 1
source = source.replace(full_loop, full_loop + '\n            x = _ap_choose(self, "full", x)')
source = source.replace(swa_loop, swa_loop + '\n            x = _ap_choose(self, "swa", x)')
# After an out-of-order eviction start from the real LRU again; otherwise earlier
# nodes could be skipped or a newly exposed parent could be missed.
assert source.count("            x = x_next") == 2
source = source.replace("            x = x_next", "            x = self.full_lru_list.get_leaf_lru_no_lock()", 1)
source = source.replace("            x = x_next", "            x = self.swa_lru_list.get_lru_no_lock()", 1)
namespace = dict(vars(swa), _ap_choose=choose)
exec(compile(source, "<async-exp-upstream-evict>", "exec"), namespace)
predicted_evict = namespace["predicted_evict"]


def evict(self, params):
    start = time.perf_counter_ns()
    self._ap_evict += 1
    self._ap_decisions = []
    plan_end = start
    signature = None
    self._ap_fill_nodes = 0
    self._ap_fill_batches = 0
    self._ap_fill_inference_us = 0.0
    self._ap_fill_selection_us = 0.0
    self._ap_fill_reasons = {}
    if MODE == "sync_fill":
        result = predicted_evict(self, params)
    elif MODE != "lru":
        fs = {k: frontier(self, k) for k in ("full", "swa")}
        signature = {k: node_signature(ns) for k, ns in fs.items()}
        payload = None
        if self._ap_leader:
            plan = {"full": {}, "swa": {}}
            for k, ns in fs.items():
                for n in ns:
                    state = getattr(n, "_ap_states", {}).get(k)
                    ticket = state.prediction_state if state else None
                    result = state.read() if state else None
                    if result is not None:
                        score = reuse_probability(result.hazard, self._ap_seq-ticket.episode_start, 20)
                        if score is not None and np.isfinite(score):
                            plan[k][n.id] = score
            payload = (signature, plan)
        if self._ap_group is not None and self._ap_group.world_size > 1:
            # Explicit Gloo group: do not interleave the scheduler's message queue.
            box = [payload]
            torch.distributed.broadcast_object_list(box, src=self._ap_group.ranks[0], group=self._ap_group.cpu_group)
            payload = box[0]
        assert payload[0] == signature, "TP radix frontier mismatch before eviction"
        self._ap_plan = payload[1]
        plan_end = time.perf_counter_ns()
        result = predicted_evict(self, params)
    else:
        result = original_evict(self, params)
    ended = time.perf_counter_ns()
    digest = hashlib.sha256(repr(self._ap_decisions).encode()).hexdigest()
    emit(self, dict(kind="evict", index=self._ap_evict, seq=self._ap_seq,
                    total_us=(ended-start)/1000, plan_and_tp_us=(plan_end-start)/1000,
                    freed_full=result.num_tokens_evicted, freed_swa=result.swa_num_tokens_evicted,
                    choices=len(self._ap_decisions), mlp_choices=sum(d[3] for d in self._ap_decisions),
                    changed_choices=sum(d[4] for d in self._ap_decisions), digest=digest,
                    fill_nodes=self._ap_fill_nodes, fill_batches=self._ap_fill_batches,
                    fill_inference_us=self._ap_fill_inference_us,
                    fill_selection_and_tp_us=self._ap_fill_selection_us,
                    fill_reasons=self._ap_fill_reasons))
    return result
swa.SWARadixCache.evict = evict
