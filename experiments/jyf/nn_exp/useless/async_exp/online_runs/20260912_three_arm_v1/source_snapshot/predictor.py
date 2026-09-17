"""CPU prediction worker prototype; no SGLang installation is modified.

The serving owner swaps episode tickets. Workers only publish onto the ticket
they received, so a late result cannot overwrite a newer node episode. Raw
feature inputs are immutable snapshots; workers never traverse the live tree.
Queue operations use a short Python Queue mutex, never an inference lock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import queue
import threading
import time
from types import MappingProxyType

import numpy as np
import torch
from torch import nn

EDGES = np.array([0, 1, 2, 5, 10, 20, 50, 100, 200, 500], dtype=float)
FEATURES = ["log_node_tokens", "log_path_tokens", "log_depth", "log_age_events", "lru_frac", "log_parent_hits", "log_siblings", "warm_sibling_fraction", "log_owner_turn", "is_cold", "log_hits", "gap_present", "log_recent_gap_events", "is_openhands", "is_request", "is_swa"]


def features(c):
    sib = max(0, int(c.get("siblings", 0)))
    gap = int(c.get("recent_gap_req", -1))
    tr = c.get("owner_traffic", "")
    log = lambda key: math.log1p(max(0, int(c.get(key, 0))))
    return [log("node_tokens"), log("path_tokens"), log("depth"),
            log("age_requests"), float(c.get("lru_frac", 0)), log("parent_hits"),
            math.log1p(sib), max(0, int(c.get("warm_siblings", 0))) / max(sib, 1),
            log("owner_turn"), float(c.get("cold", 0)), log("hits"), float(gap >= 0),
            math.log1p(max(gap, 0)), float(tr == "openhands"),
            float(tr == "request"), float(c.get("frontier") == "swa")]


class Unified(nn.Module):
    def __init__(self):
        super().__init__()
        self.t = nn.Sequential(nn.Linear(16, 64), nn.ReLU(), nn.Linear(64, 32), nn.ReLU())
        self.h = nn.Linear(32, 10)

    def forward(self, x):
        return self.h(self.t(x))


class Model:
    def __init__(self, checkpoint):
        cp = torch.load(checkpoint, map_location="cpu", weights_only=False)
        assert cp["features"] == FEATURES
        assert tuple(cp["bucket_upper_edges"]) == tuple(EDGES[1:])
        self.mean = np.asarray(cp["mean"], dtype=np.float32)
        self.std = np.asarray(cp["std"], dtype=np.float32)
        self.net = Unified().eval()
        self.net.load_state_dict(cp["state_dict"])

    @torch.inference_mode()
    def predict(self, snapshots):
        x = np.asarray([features(c) for c in snapshots], dtype=np.float32)
        x = (x - self.mean) / self.std
        p = self.net(torch.from_numpy(x)).softmax(1).numpy()
        # Nine finite-interval conditional hazards, then unresolved tail mass.
        survival = np.cumsum(p[:, ::-1], axis=1)[:, ::-1]
        hazard = p[:, :9] / np.maximum(survival[:, :9], 1e-12)
        return p, hazard


def reuse_probability(hazard, age, horizon):
    """Piecewise-constant hazard interpolation, units = cache-access events.

    Never reinterpret event buckets as seconds. The open tail has no learned
    rate: return None beyond 500 so the caller falls back to LRU.
    """
    if age < 0 or horizon < 0 or age + horizon > EDGES[-1]:
        return None
    h = np.clip(np.asarray(hazard, dtype=float), 0, 1 - 1e-12)
    overlap = np.maximum(0, np.minimum(EDGES[1:], age + horizon)
                         - np.maximum(EDGES[:-1], age))
    log_survival_ratio = np.sum(np.log1p(-h) * overlap / np.diff(EDGES))
    return float(-np.expm1(log_survival_ratio))


@dataclass(frozen=True)
class Result:
    ready_ns: int
    probabilities: tuple
    hazard: tuple


@dataclass(eq=False)
class Ticket:
    node_id: object
    episode_id: int
    episode_start: float
    snapshot: object
    enqueued_ns: int = field(default_factory=time.perf_counter_ns)
    cancelled: bool = False
    result: Result | None = None


class Node:
    """Only the serving thread may call begin/invalidate/read."""
    def __init__(self, node_id):
        self.node_id = node_id
        self.episode_id = 0
        self.prediction_state = None

    def begin(self, raw, episode_start=0):
        self.invalidate()
        # Flat numeric/string metadata only. The copy prevents worker/tree races.
        ticket = Ticket(self.node_id, self.episode_id, episode_start,
                        MappingProxyType(dict(raw)))
        self.prediction_state = ticket
        return ticket

    def invalidate(self):
        if self.prediction_state is not None:
            self.prediction_state.cancelled = True
        self.episode_id += 1
        self.prediction_state = None

    def read(self):
        t = self.prediction_state
        return None if t is None or t.cancelled else t.result


class Worker:
    def __init__(self, model, batch_size=64, capacity=4096, delay_ms=0):
        self.model = model
        self.batch_size = batch_size
        self.queue = queue.Queue(capacity)
        self.delay_s = delay_ms / 1000
        self.stopping = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.dropped = 0
        self.cancelled = 0
        self.batch_sizes = []
        self.batch_us = []
        self.queue_us = []
        self.thread = threading.Thread(target=self._run, name="PredictionWorker", daemon=True)
        self.thread.start()
        if not self.ready.wait(30):
            raise RuntimeError("worker initialization timed out")
        if self.error:
            raise RuntimeError(self.error)

    def submit(self, ticket):
        if self.error or self.stopping.is_set():
            self.dropped += 1
            return False
        try:
            self.queue.put_nowait(ticket)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def _run(self):
        try:
            for _ in range(20):
                self.model.predict([{}] * self.batch_size)
            self.ready.set()
            while not self.stopping.is_set() or not self.queue.empty():
                try:
                    first = self.queue.get(timeout=0.01)
                except queue.Empty:
                    continue
                batch = [first]
                while len(batch) < self.batch_size:
                    try:
                        batch.append(self.queue.get_nowait())
                    except queue.Empty:
                        break
                active = [t for t in batch if not t.cancelled]
                self.cancelled += len(batch) - len(active)
                if not active:
                    continue
                start = time.perf_counter_ns()
                self.queue_us.extend((start - t.enqueued_ns) / 1000 for t in active)
                if self.delay_s:
                    time.sleep(self.delay_s)
                p, hazard = self.model.predict([t.snapshot for t in active])
                for t, pi, hi in zip(active, p, hazard):
                    if t.cancelled:
                        self.cancelled += 1
                        continue
                    probs, hazards = tuple(map(float, pi)), tuple(map(float, hi))
                    t.result = Result(time.perf_counter_ns(), probs, hazards)
                self.batch_us.append((time.perf_counter_ns() - start) / 1000)
                self.batch_sizes.append(len(active))
        except Exception as exc:
            self.error = repr(exc)
            self.ready.set()

    def close(self):
        """Benchmark shutdown only. Serving/eviction never call this."""
        self.stopping.set()
        self.thread.join(30)
        if self.thread.is_alive():
            raise RuntimeError("worker did not stop")
        if self.error:
            raise RuntimeError(self.error)


def predict_sync(model, tickets, delay_ms=0):
    if delay_ms:
        time.sleep(delay_ms / 1000)
    p, hazard = model.predict([t.snapshot for t in tickets])
    for t, pi, hi in zip(tickets, p, hazard):
        probs, hazards = tuple(map(float, pi)), tuple(map(float, hi))
        t.result = Result(time.perf_counter_ns(), probs, hazards)


def choose_candidate(nodes, now, horizon=20):
    """LRU-ordered legal shortlist. No wait, queue read, or model call here."""
    if not nodes:
        return None, False
    tickets = [n.prediction_state for n in nodes]
    if any(t is None or t.cancelled or t.result is None for t in tickets):
        return nodes[0], False
    age = np.asarray([now - t.episode_start for t in tickets])
    if horizon < 0 or np.any(age < 0) or np.any(age + horizon > EDGES[-1]):
        return nodes[0], False
    h = np.clip(np.asarray([t.result.hazard for t in tickets]), 0, 1 - 1e-12)
    overlap = np.maximum(0, np.minimum(EDGES[1:], age[:, None] + horizon)
                         - np.maximum(EDGES[:-1], age[:, None]))
    scores = -np.expm1(np.sum(np.log1p(-h) * overlap / np.diff(EDGES), axis=1))
    return nodes[int(np.argmin(scores))], True
