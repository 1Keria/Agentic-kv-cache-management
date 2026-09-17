"""MLP reuse-probability scorer for radix eviction (V4Flash SWA + classic).

Controller (not the net): π = Σ α_k Δp_k with fixed α, NetValue = (π − λ) × KVSize,
evict lowest NetValue. The network only outputs p_i(H_k).

SWA victims (often internal nodes) reuse the same π: an ancestor takes the max
π of descendant leaves. Same π on one path tombstones closer to the root first.
"""

from __future__ import annotations

import heapq
import logging
import math
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional

import torch
import torch.nn as nn

if TYPE_CHECKING:
    from sglang.srt.managers.schedule_batch import Req
    from sglang.srt.mem_cache.cache_init_params import CacheInitParams

logger = logging.getLogger(__name__)

AGENT_LIKE = {"agent", "openhands", "glm"}
FEATURE_NAMES = [
    "log_node_tokens",
    "log_path_tokens",
    "log_prefix_depth",
    "log_reuse_count",
    "n_children",
    "is_leaf",
    "is_evictable",
    "session_alive",
    "has_tools",
    "is_alive_agent_session",
    "stop_end_turn",
    "log_hops",
    "log_gap_ms",
    "log_subtree_tokens",
    "n_siblings",
    "is_public_trunk",
]


DEFAULT_DELTA_ALPHA = (1.0, 0.7, 0.5)


def init_mlp_fields(node) -> None:
    node.mlp_last_session_id = ""
    node.mlp_net_value = 0.0
    node.mlp_pi = 0.0
    node.mlp_prefix_depth = 0


def copy_mlp_on_split(new_node, child) -> None:
    new_node.mlp_last_session_id = getattr(child, "mlp_last_session_id", "")
    new_node.mlp_net_value = 0.0
    new_node.mlp_pi = 0.0
    new_node.mlp_prefix_depth = 0


def parse_delta_alpha(raw, n_horizons: int) -> list[float]:
    if raw is None or raw == "":
        vals = list(DEFAULT_DELTA_ALPHA)
    elif isinstance(raw, str):
        vals = [float(x.strip()) for x in raw.split(",") if x.strip()]
    else:
        vals = [float(x) for x in raw]
    if not vals:
        vals = [1.0]
    if any(a <= 0.0 for a in vals):
        raise ValueError("mlp delta α must be > 0")
    if len(vals) < n_horizons:
        vals = vals + [vals[-1]] * (n_horizons - len(vals))
    return vals[:n_horizons]


def compose_pi(probs: torch.Tensor, alpha: list[float]) -> torch.Tensor:
    """π_i = Σ α_k Δp_{i,k} with Δp_1 = p(H_1), Δp_k = max(0, p(H_k)−p(H_{k-1}))."""
    k = int(probs.shape[-1])
    a = parse_delta_alpha(alpha, k)
    at = torch.tensor(a, dtype=probs.dtype, device=probs.device)
    delta = torch.empty_like(probs)
    delta[..., 0] = probs[..., 0].clamp(min=0)
    if k > 1:
        delta[..., 1:] = (probs[..., 1:] - probs[..., :-1]).clamp(min=0)
    return (delta * at).sum(dim=-1)


def mlp_victim_sort_key(node) -> tuple:
    kv = _kv_size(node)
    return (
        float(getattr(node, "mlp_net_value", 0.0)),
        float(getattr(node, "mlp_pi", 0.0)),
        -kv,
    )


def mlp_swa_victim_sort_key(node) -> tuple:
    """Lowest π first; same π → closer to root (smaller depth) first."""
    return (
        float(getattr(node, "mlp_pi", 0.0)),
        int(getattr(node, "mlp_prefix_depth", 0) or 0),
        float(getattr(node, "mlp_net_value", 0.0)),
        -_kv_size(node),
    )


def _log1p(x: float) -> float:
    return math.log1p(max(0.0, float(x)))


def _node_tokens(node) -> int:
    key = getattr(node, "key", None)
    if key is None:
        return 0
    try:
        return int(len(key))
    except TypeError:
        return 0


def _kv_size(node) -> int:
    value = getattr(node, "value", None)
    if value is None:
        return 0
    try:
        return int(len(value))
    except TypeError:
        return 0


def _path_tokens(node) -> int:
    total = 0
    cur = node
    while cur is not None and getattr(cur, "parent", None) is not None:
        total += _node_tokens(cur)
        cur = cur.parent
    return total


def _n_children(node) -> int:
    children = getattr(node, "children", None)
    if not children:
        return 0
    return int(len(children))


def _n_siblings(node) -> int:
    parent = getattr(node, "parent", None)
    if parent is None:
        return 0
    return max(0, _n_children(parent) - 1)


class LeafMLP(nn.Module):
    def __init__(self, n_in: int = 16, hidden: int = 128, n_horizons: int = 1) -> None:
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(n_in, hidden),
            nn.ReLU(),
            nn.Dropout(0.0),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Dropout(0.0),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Dropout(0.0),
        )
        self.head = nn.Linear(hidden, n_horizons)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.backbone(x))


class MlpReuseScorer:
    def __init__(self, ckpt_path: Path, device: str = "cpu") -> None:
        self.device = torch.device(device)
        try:
            blob = torch.load(ckpt_path, map_location=self.device, weights_only=False)
        except TypeError:
            blob = torch.load(ckpt_path, map_location=self.device)
        names = [
            "is_alive_agent_session" if name == "stop_tool_use" else name
            for name in list(blob.get("feature_names") or FEATURE_NAMES)
        ]
        if names != FEATURE_NAMES:
            raise ValueError(
                f"MLP checkpoint feature_names {names} != serving {FEATURE_NAMES}"
            )
        self.model = LeafMLP(
            n_in=int(blob["n_in"]),
            hidden=int(blob["hidden"]),
            n_horizons=int(blob["n_horizons"]),
        )
        self.model.load_state_dict(blob["state_dict"])
        self.model.to(self.device)
        self.model.eval()
        self.mean = torch.tensor(blob["x_mean"], dtype=torch.float32, device=self.device)
        self.std = torch.tensor(blob["x_std"], dtype=torch.float32, device=self.device)
        self.horizons_s = [float(h) for h in blob["horizons_s"]]

    @torch.no_grad()
    def score(self, x: torch.Tensor) -> torch.Tensor:
        xt = (x.to(self.device) - self.mean) / self.std
        return torch.sigmoid(self.model(xt))


@dataclass
class _SessionSide:
    hops: int = 0
    has_tools: bool = False
    traffic_class: str = ""
    last_wall_s: float = 0.0
    in_flight: int = 0
    ended: bool = False
    seen_rids: set[str] = field(default_factory=set)


def _req_custom(req: Any) -> dict:
    if req is None:
        return {}
    sp = getattr(req, "sampling_params", None)
    custom = getattr(sp, "custom_params", None) if sp is not None else None
    return custom if isinstance(custom, dict) else {}


def _parse_req_meta(req: Any) -> tuple[str, int, str, bool]:
    custom = _req_custom(req)
    sid = str(custom.get("session_id") or getattr(req, "rid", "") or "")
    try:
        turn_idx = int(custom.get("turn_idx", 0) or 0)
    except (TypeError, ValueError):
        turn_idx = 0
    traffic = str(custom.get("traffic_class") or "")
    has_tools = bool(custom.get("has_tools"))
    return sid, turn_idx, traffic, has_tools


class MlpReuseMixin:
    def init_mlp_from_params(
        self,
        params: "CacheInitParams",
        eviction_policy: str,
        uses_mlp: bool,
    ) -> None:
        self.mlp_shadow_only = bool(getattr(params, "mlp_shadow_only", False))
        self.mlp_checkpoint = getattr(params, "mlp_checkpoint", None)
        self.mlp_hold_lambda = float(getattr(params, "mlp_hold_lambda", 0.05) or 0.0)
        self.mlp_delta_alpha_raw = getattr(
            params, "mlp_delta_alpha", DEFAULT_DELTA_ALPHA
        )
        self.mlp_horizon_index = int(getattr(params, "mlp_horizon_index", -1))
        self.mlp_occupancy_hi = float(getattr(params, "mlp_occupancy_hi", 0.90))
        self.mlp_occupancy_mid = float(getattr(params, "mlp_occupancy_mid", 0.75))
        if self.mlp_shadow_only and eviction_policy != "lru":
            raise ValueError("mlp_shadow_only requires eviction_policy='lru'")
        self.mlp_enabled = uses_mlp or self.mlp_shadow_only
        self.mlp_scorer: Optional[MlpReuseScorer] = None
        self.mlp_sessions: dict[str, _SessionSide] = {}
        self._mlp_insert_sid = ""
        self._mlp_clock_depth = 0
        self._mlp_clock_t0 = 0.0
        self._mlp_phase_s = 0.0
        self._mlp_evict_n = 0
        self._mlp_phase_s_total = 0.0
        self._mlp_evict_s_total = 0.0
        if self.mlp_enabled:
            if not self.mlp_checkpoint:
                raise ValueError(
                    "mlp eviction requires --radix-mlp-checkpoint / CacheInitParams.mlp_checkpoint"
                )
            path = Path(str(self.mlp_checkpoint)).expanduser()
            if not path.is_file():
                raise FileNotFoundError(f"MLP checkpoint not found: {path}")
            self.mlp_scorer = MlpReuseScorer(path, device="cpu")
            self.mlp_delta_alpha = parse_delta_alpha(
                self.mlp_delta_alpha_raw, len(self.mlp_scorer.horizons_s)
            )
            logger.info(
                "MLP reuse scorer loaded from %s horizons=%s alpha=%s lambda=%.4f",
                path,
                self.mlp_scorer.horizons_s,
                self.mlp_delta_alpha,
                self.mlp_hold_lambda,
            )
        else:
            self.mlp_delta_alpha = parse_delta_alpha(self.mlp_delta_alpha_raw, 3)

    def _mlp_begin_insert(self, req: Any) -> None:
        self._mlp_insert_sid = ""
        if not self.mlp_enabled or req is None:
            return
        sid, _, _, _ = _parse_req_meta(req)
        self._mlp_insert_sid = sid

    def _mlp_end_insert(self) -> None:
        self._mlp_insert_sid = ""

    def _mlp_stamp_new_node(self, node) -> None:
        if self._mlp_insert_sid:
            node.mlp_last_session_id = self._mlp_insert_sid

    def _mlp_session(self, sid: str) -> _SessionSide:
        side = self.mlp_sessions.get(sid)
        if side is None:
            side = _SessionSide()
            self.mlp_sessions[sid] = side
        return side

    def _mlp_note_match(self, req: Any, last_node) -> None:
        if not self.mlp_enabled or req is None or last_node is None:
            return
        sid, turn_idx, traffic, has_tools = _parse_req_meta(req)
        if not sid:
            return
        now = time.time()
        side = self._mlp_session(sid)
        rid = str(getattr(req, "rid", "") or "")
        if rid and rid not in side.seen_rids:
            side.seen_rids.add(rid)
            hops = turn_idx + 1 if turn_idx >= 0 else side.hops + 1
            side.hops = max(side.hops, hops)
            side.in_flight += 1
            side.ended = False
        if traffic:
            side.traffic_class = traffic
        side.has_tools = bool(has_tools or side.has_tools)
        side.last_wall_s = now
        node = last_node
        root = getattr(self, "root_node", None)
        while node is not None and node is not root:
            node.mlp_last_session_id = sid
            node.reuse_count = int(getattr(node, "reuse_count", 0)) + 1
            node = node.parent

    def _mlp_note_finished(self, req: Any) -> None:
        if not self.mlp_enabled or req is None:
            return
        sid, _, traffic, _ = _parse_req_meta(req)
        if not sid:
            return
        side = self._mlp_session(sid)
        side.in_flight = max(0, side.in_flight - 1)
        side.last_wall_s = time.time()
        cls = traffic or side.traffic_class
        if cls == "request" and side.in_flight == 0:
            side.ended = True

    def _mlp_lambda(self) -> float:
        return float(self.mlp_hold_lambda)

    def _mlp_phase_begin(self) -> None:
        if not getattr(self, "mlp_enabled", False):
            return
        if self._mlp_clock_depth == 0:
            self._mlp_clock_t0 = time.perf_counter()
        self._mlp_clock_depth += 1

    def _mlp_phase_end(self) -> None:
        if not getattr(self, "mlp_enabled", False):
            return
        self._mlp_clock_depth = max(0, self._mlp_clock_depth - 1)
        if self._mlp_clock_depth == 0:
            self._mlp_phase_s += time.perf_counter() - self._mlp_clock_t0

    @contextmanager
    def _mlp_phase_timer(self):
        self._mlp_phase_begin()
        try:
            yield
        finally:
            self._mlp_phase_end()

    def _mlp_on_evict_start(self) -> None:
        self._mlp_phase_s = 0.0
        self._mlp_clock_depth = 0

    def _mlp_on_evict_end(self, evict_s: float, **kv) -> None:
        # Always record evict() wall time so LRU and MLP runs are comparable.
        # mlp_ms stays 0 unless mlp_enabled (phase timer is a no-op otherwise).
        self._mlp_evict_n = int(getattr(self, "_mlp_evict_n", 0)) + 1
        phase = float(getattr(self, "_mlp_phase_s", 0.0))
        self._mlp_phase_s_total = float(getattr(self, "_mlp_phase_s_total", 0.0)) + phase
        self._mlp_evict_s_total = float(getattr(self, "_mlp_evict_s_total", 0.0)) + evict_s
        ratio = phase / evict_s if evict_s > 1e-9 else 0.0
        cum_e = self._mlp_evict_s_total
        cum_m = self._mlp_phase_s_total
        cum_r = cum_m / cum_e if cum_e > 1e-9 else 0.0
        n = self._mlp_evict_n
        policy = getattr(self, "eviction_policy", "unknown")
        extra = " ".join(f"{k}={v}" for k, v in kv.items() if v is not None)
        if n <= 5 or n % 20 == 0 or evict_s >= 0.05:
            logger.info(
                "RADIX_EVICT policy=%s n=%d evict_ms=%.3f mlp_ms=%.3f ratio=%.3f "
                "cum_evict_s=%.3f cum_mlp_s=%.3f cum_ratio=%.3f %s",
                policy,
                n,
                evict_s * 1e3,
                phase * 1e3,
                ratio,
                cum_e,
                cum_m,
                cum_r,
                extra,
            )

    def _mlp_leaf_features(self, node, now: float) -> list[float]:
        sid = getattr(node, "mlp_last_session_id", "") or ""
        side = self.mlp_sessions.get(sid)
        agent = bool(side and side.traffic_class in AGENT_LIKE)
        alive = False
        has_tools = False
        hops = 0
        gap_ms = 0.0
        if side is not None:
            alive = (not side.ended) or side.in_flight > 0
            has_tools = bool(side.has_tools)
            hops = int(side.hops)
            if side.last_wall_s > 0:
                gap_ms = max(0.0, (now - side.last_wall_s) * 1000.0)
        stop_end = 0.0 if alive else 1.0
        alive_agent = 1.0 if alive and agent else 0.0
        ntok = _node_tokens(node)
        n_sib = _n_siblings(node)
        reuse = int(getattr(node, "reuse_count", 0) or getattr(node, "hit_count", 0) or 0)
        public = 1.0 if (n_sib >= 1 or reuse > 1) else 0.0
        parent = getattr(node, "parent", None)
        if parent is not None and _n_children(parent) > 1:
            public = 1.0
        depth = int(getattr(node, "prefix_depth", 0) or 0)
        if depth <= 0:
            depth = 0
            cur = node
            while cur is not None and getattr(cur, "parent", None) is not None:
                depth += 1
                cur = cur.parent
        return [
            _log1p(ntok),
            _log1p(_path_tokens(node)),
            _log1p(depth),
            _log1p(reuse),
            float(_n_children(node)),
            1.0,
            1.0,
            1.0 if alive else 0.0,
            1.0 if has_tools else 0.0,
            alive_agent,
            stop_end,
            _log1p(hops),
            _log1p(gap_ms),
            _log1p(ntok),
            float(n_sib),
            public,
        ]

    def _mlp_net_values(self, nodes: list) -> list[float]:
        assert self.mlp_scorer is not None
        with self._mlp_phase_timer():
            now = time.time()
            feats = [self._mlp_leaf_features(n, now) for n in nodes]
            x = torch.tensor(feats, dtype=torch.float32)
            probs = self.mlp_scorer.score(x)
            alpha = getattr(self, "mlp_delta_alpha", None) or parse_delta_alpha(
                getattr(self, "mlp_delta_alpha_raw", DEFAULT_DELTA_ALPHA),
                int(probs.shape[-1]),
            )
            pis = compose_pi(probs, alpha)
            lam = self._mlp_lambda()
            nets: list[float] = []
            for i, node in enumerate(nodes):
                pi = float(pis[i].item())
                kv = float(_kv_size(node))
                net = (pi - lam) * kv
                node.mlp_pi = pi
                node.mlp_net_value = net
                nets.append(net)
            return nets

    def _select_mlp_victim(self, candidates: Iterable, fallback):
        nodes = list(candidates)
        if not nodes:
            return fallback
        self._mlp_net_values(nodes)
        if self.mlp_shadow_only:
            lru = min(nodes, key=lambda n: n.last_access_time)
            mlp = min(nodes, key=mlp_victim_sort_key)
            logger.info(
                "MLP_SHADOW lambda=%.4f alpha=%s candidates=%d "
                "lru=%s mlp=%s agree=%s lru_pi=%.4f mlp_pi=%.4f",
                self._mlp_lambda(),
                getattr(self, "mlp_delta_alpha", None),
                len(nodes),
                getattr(lru, "id", None),
                getattr(mlp, "id", None),
                lru is mlp,
                float(getattr(lru, "mlp_pi", 0.0)),
                float(getattr(mlp, "mlp_pi", 0.0)),
            )
            return fallback
        return min(nodes, key=mlp_victim_sort_key)

    def _mlp_collect_subtree_leaves(self, node, out: list, seen: set) -> None:
        children = getattr(node, "children", None)
        if not children:
            nid = id(node)
            if nid not in seen:
                seen.add(nid)
                out.append(node)
            return
        for child in children.values():
            self._mlp_collect_subtree_leaves(child, out, seen)

    def _mlp_prefix_depth(self, node) -> int:
        depth = 0
        cur = node
        root = getattr(self, "root_node", None)
        while cur is not None and cur is not root and getattr(cur, "parent", None) is not None:
            depth += 1
            cur = cur.parent
        return depth

    def _mlp_score_swa_candidates(self, candidates: list) -> None:
        """π of an internal SWA node = max π of descendant leaves."""
        if not candidates:
            return
        with self._mlp_phase_timer():
            leaves: list = []
            seen: set = set()
            for node in candidates:
                self._mlp_collect_subtree_leaves(node, leaves, seen)
            if leaves:
                self._mlp_net_values(leaves)
            leaf_pi = {id(leaf): float(getattr(leaf, "mlp_pi", 0.0)) for leaf in leaves}
            cand_ids = {id(node) for node in candidates}
            for node in candidates:
                node.mlp_pi = 0.0
                node.mlp_prefix_depth = self._mlp_prefix_depth(node)
            root = getattr(self, "root_node", None)
            for leaf in leaves:
                pi = leaf_pi[id(leaf)]
                node = leaf
                while node is not None and node is not root:
                    if id(node) in cand_ids:
                        node.mlp_pi = max(float(getattr(node, "mlp_pi", 0.0)), pi)
                    node = getattr(node, "parent", None)
            lam = self._mlp_lambda()
            for node in candidates:
                kv = float(_kv_size(node))
                node.mlp_net_value = (float(node.mlp_pi) - lam) * kv

    def _select_mlp_swa_victim(self, candidates: Iterable, fallback):
        nodes = list(candidates)
        if not nodes:
            return fallback
        self._mlp_score_swa_candidates(nodes)
        if self.mlp_shadow_only:
            lru = min(nodes, key=lambda n: n.last_access_time)
            mlp = min(nodes, key=mlp_swa_victim_sort_key)
            logger.info(
                "MLP_SHADOW_SWA lambda=%.4f alpha=%s candidates=%d "
                "lru=%s mlp=%s agree=%s lru_pi=%.4f mlp_pi=%.4f",
                self._mlp_lambda(),
                getattr(self, "mlp_delta_alpha", None),
                len(nodes),
                getattr(lru, "id", None),
                getattr(mlp, "id", None),
                lru is mlp,
                float(getattr(lru, "mlp_pi", 0.0)),
                float(getattr(mlp, "mlp_pi", 0.0)),
            )
            return fallback
        return min(nodes, key=mlp_swa_victim_sort_key)

    def _mlp_is_unlocked_full_leaf(self, node) -> bool:
        if node is None:
            return False
        root = getattr(self, "root_node", None)
        if node is root:
            return False
        lru = getattr(self, "full_lru_list", None)
        if lru is None or not lru.in_list(node):
            return False
        if int(getattr(node, "full_lock_ref", 1) or 0) > 0:
            return False
        children = getattr(node, "children", None)
        if children:
            return False
        if getattr(node, "value", None) is None:
            return False
        return True

    def _mlp_make_evict_heap(self, nodes: list) -> list:
        nodes = [n for n in nodes if n is not None]
        if not nodes:
            return []
        self._mlp_net_values(nodes)
        heap = [(mlp_victim_sort_key(n), int(getattr(n, "id", 0)), n) for n in nodes]
        heapq.heapify(heap)
        return heap

    def _mlp_pop_evict_heap(self, heap: list):
        while heap:
            _, _, node = heapq.heappop(heap)
            if self._mlp_is_unlocked_full_leaf(node):
                return node
        return None

    def _mlp_heap_push_if_new_leaf(self, heap: list, node) -> None:
        if not self._mlp_is_unlocked_full_leaf(node):
            return
        self._mlp_net_values([node])
        heapq.heappush(heap, (mlp_victim_sort_key(node), int(getattr(node, "id", 0)), node))
