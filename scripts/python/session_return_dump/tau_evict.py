"""Stamp τ̂ = E[min(τ, 60)] onto session-private radix suffix; evict larger τ̂ first.

Enabled by SESSION_RETURN_TAU_CKPT. Unscored nodes keep LRU. Does not use the
Engine leaf-MLP policy. Replay should pass original client.max_tokens / tools
length in sampling_params.custom_params because the OpenAI max_tokens field is
the logged-completion cap.
"""
from __future__ import annotations

import json
import math
import os
import sys
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import torch
from torch import nn

K8 = (
    "req.finished_len",
    "client.temperature",
    "client.max_tokens",
    "req.cached_tokens",
    "client.tools",
    "req.finished_reason",
    "req.fill_len",
    "req.extend_input_len",
)

_lock = threading.Lock()
_installed = False
_model: Optional["TauScorer"] = None
_failed = False
_n_score = 0
_n_evict_scored = 0


class HazardNet(nn.Module):
    def __init__(self, n_in: int, n_buckets: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 32),
            nn.ReLU(),
            nn.Linear(32, 32),
            nn.ReLU(),
            nn.Linear(32, n_buckets),
        )

    def forward(self, x):
        return self.net(x)


def _restricted_mean(hazards: np.ndarray, edges: np.ndarray, horizon: float) -> float:
    hazards = np.clip(np.asarray(hazards, np.float64).reshape(-1), 1e-9, 1 - 1e-9)
    surv = 1.0
    num = 0.0
    p_le = 0.0
    left = 0.0
    for j, right in enumerate(edges):
        if right > horizon + 1e-9:
            break
        p = surv * hazards[j]
        mid = 0.5 * (left + right)
        num += p * mid
        p_le += p
        surv *= 1.0 - hazards[j]
        left = right
    if p_le <= 1e-8:
        return float(horizon)
    cond = num / p_le
    return float(cond * min(p_le, 1.0) + horizon * max(0.0, 1.0 - p_le))


class TauScorer:
    def __init__(self, ckpt_path: Path):
        blob = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        spec_path = ckpt_path.with_name("k8_serving.json")
        spec = json.loads(spec_path.read_text()) if spec_path.is_file() else {}
        self.features = list(blob.get("features") or spec.get("features") or K8)
        self.mean = np.asarray(blob["mean"], dtype=np.float64)
        self.std = np.asarray(blob["std"], dtype=np.float64)
        self.std = np.where(self.std < 1e-8, 1.0, self.std)
        edges = blob.get("edges")
        if edges is None:
            edges = spec.get("edges")
        self.edges = np.asarray(edges, dtype=np.float64)
        self.horizon = float(blob.get("horizon_s") or spec.get("horizon_s") or 60.0)
        self.reason_map = dict(
            blob.get("finished_reason_map") or spec.get("finished_reason_map") or {}
        )
        self.net = HazardNet(len(self.features), len(self.edges))
        self.net.load_state_dict(blob["state_dict"])
        self.net.eval()

    def encode(self, values: dict[str, Any]) -> np.ndarray:
        x = np.zeros(len(self.features), dtype=np.float64)
        for i, name in enumerate(self.features):
            v = values.get(name)
            if name == "req.finished_reason":
                if isinstance(v, str):
                    v = self.reason_map.get(v, -1.0)
                elif v is None:
                    v = None
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                x[i] = 0.0
            else:
                x[i] = (float(v) - self.mean[i]) / self.std[i]
        return x

    @torch.no_grad()
    def predict(self, values: dict[str, Any]) -> float:
        z = torch.tensor(self.encode(values), dtype=torch.float32).unsqueeze(0)
        logits = self.net(z).numpy()[0]
        hazards = 1.0 / (1.0 + np.exp(-logits))
        return _restricted_mean(hazards, self.edges, self.horizon)


def _scorer() -> Optional[TauScorer]:
    global _model, _failed
    if _failed:
        return None
    if _model is not None:
        return _model
    raw = os.environ.get("SESSION_RETURN_TAU_CKPT")
    if not raw:
        return None
    with _lock:
        if _failed:
            return None
        if _model is None:
            try:
                _model = TauScorer(Path(raw))
            except Exception as exc:
                _failed = True
                sys.stderr.write(f"[tau_evict] checkpoint load failed: {exc}\n")
                return None
    return _model


def _as_float(value: Any) -> float | None:
    if value is None or value is False:
        return 0.0 if value is False else None
    if value is True:
        return 1.0
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _reason_type(reason: Any) -> str | None:
    if reason is None:
        return None
    if hasattr(reason, "to_json"):
        try:
            blob = reason.to_json()
            if isinstance(blob, dict) and blob.get("type") is not None:
                return str(blob["type"])
        except Exception:
            pass
    if isinstance(reason, dict) and reason.get("type") is not None:
        return str(reason["type"])
    return type(reason).__name__


def _custom(req: Any) -> dict:
    sp = getattr(req, "sampling_params", None)
    custom = getattr(sp, "custom_params", None) if sp is not None else None
    return custom if isinstance(custom, dict) else {}


def _k8_from_req(req: Any) -> dict[str, Any]:
    sp = getattr(req, "sampling_params", None)
    custom = _custom(req)
    tools = custom.get("sr_tools_len")
    max_tokens = custom.get("sr_client_max_tokens")
    if max_tokens is None:
        max_tokens = getattr(sp, "max_new_tokens", None)
    return {
        "req.finished_len": _as_float(getattr(req, "finished_len", None)),
        "client.temperature": _as_float(getattr(sp, "temperature", None) if sp else None),
        "client.max_tokens": _as_float(max_tokens),
        "req.cached_tokens": _as_float(getattr(req, "cached_tokens", None)),
        "client.tools": _as_float(tools),
        "req.finished_reason": _reason_type(getattr(req, "finished_reason", None)),
        "req.fill_len": _as_float(getattr(req, "fill_len", None)),
        "req.extend_input_len": _as_float(getattr(req, "extend_input_len", None)),
    }


def _stamp_private_suffix(cache: Any, last_node: Any, tau: float) -> int:
    n = last_node
    root = getattr(cache, "root_node", None)
    stamped = 0
    while n is not None and n is not root:
        n._sr_tau = float(tau)
        stamped += 1
        parent = getattr(n, "parent", None)
        if parent is None or parent is root:
            break
        children = getattr(parent, "children", None) or {}
        if len(children) > 1:
            break
        n = parent
    return stamped


def _victim_key(node: Any, rank: int) -> tuple:
    tau = getattr(node, "_sr_tau", None)
    if tau is None:
        return (float("inf"), rank)
    return (-float(tau), rank)


def _pick_victim(nodes: Iterable[Any], fallback: Any) -> Any:
    global _n_evict_scored
    best = fallback
    best_key = (float("inf"), 10**9)
    for rank, node in enumerate(nodes):
        if node is None:
            continue
        key = _victim_key(node, rank)
        if key < best_key:
            best, best_key = node, key
    if best is not None and getattr(best, "_sr_tau", None) is not None:
        _n_evict_scored += 1
    return best if best is not None else fallback


def _wrap(cls: Any, name: str, wrapper, flag: str = "_sr_tau_patched") -> None:
    orig = getattr(cls, name, None)
    if orig is None or getattr(orig, flag, False):
        return
    wrapped = wrapper(orig)
    setattr(wrapped, flag, True)
    setattr(cls, name, wrapped)


def _patch_finished(cls: Any) -> None:
    def wrapper(orig):
        def cache_finished_req(self, req, *args, **kwargs):
            result = orig(self, req, *args, **kwargs)
            model = _scorer()
            if model is None or req is None:
                return result
            try:
                tau = model.predict(_k8_from_req(req))
                last = getattr(req, "last_node", None)
                n = _stamp_private_suffix(self, last, tau)
                global _n_score
                _n_score += 1
                try:
                    from native_dump import emit

                    emit(
                        "tau_stamp",
                        rid=getattr(req, "rid", None),
                        tau_hat=tau,
                        n_nodes=n,
                    )
                except Exception:
                    pass
            except Exception:
                pass
            return result

        return cache_finished_req

    _wrap(cls, "cache_finished_req", wrapper)


def _patch_split(cls: Any) -> None:
    def wrapper(orig):
        def _split_node(self, *args, **kwargs):
            child = args[1] if len(args) > 1 else kwargs.get("child")
            node = orig(self, *args, **kwargs)
            if child is not None and hasattr(child, "_sr_tau"):
                node._sr_tau = child._sr_tau
            return node

        return _split_node

    _wrap(cls, "_split_node", wrapper)


def _patch_swa_select(cls: Any) -> None:
    def wrap_full(orig):
        def _select_full_leaf_victim(self):
            if _scorer() is None:
                return orig(self)
            fallback = self.full_lru_list.get_leaf_lru_no_lock()
            return _pick_victim(self._iter_full_unlocked_leaves(), fallback)

        return _select_full_leaf_victim

    def wrap_swa(orig):
        def _select_swa_victim(self):
            if _scorer() is None:
                return orig(self)
            fallback = self.swa_lru_list.get_lru_no_lock()
            return _pick_victim(self._iter_swa_unlocked(), fallback)

        return _select_swa_victim

    _wrap(cls, "_select_full_leaf_victim", wrap_full)
    _wrap(cls, "_select_swa_victim", wrap_swa)


def _patch_classic_priority(cls: Any) -> None:
    def wrapper(orig):
        def _get_eviction_priority(self, node):
            if _scorer() is None:
                return orig(self, node)
            tau = getattr(node, "_sr_tau", None)
            t = float(getattr(node, "last_access_time", 0.0) or 0.0)
            if tau is None:
                return (float("inf"), t)
            return (-float(tau), t)

        return _get_eviction_priority

    _wrap(cls, "_get_eviction_priority", wrapper)


def install() -> None:
    global _installed
    if not os.environ.get("SESSION_RETURN_TAU_CKPT"):
        return
    import sys

    swa = sys.modules.get("sglang.srt.mem_cache.swa_radix_cache")
    if swa is not None and getattr(swa, "SWARadixCache", None) is not None:
        cls = swa.SWARadixCache
        _patch_finished(cls)
        _patch_split(cls)
        _patch_swa_select(cls)
    radix = sys.modules.get("sglang.srt.mem_cache.radix_cache")
    if radix is not None and getattr(radix, "RadixCache", None) is not None:
        cls = radix.RadixCache
        _patch_finished(cls)
        _patch_split(cls)
        _patch_classic_priority(cls)
    if not _installed:
        _installed = True
        _scorer()
