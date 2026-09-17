#!/usr/bin/env python3
"""Standalone offline prefix-reuse experiment for GLM-5.1 request logs.

This script deliberately does not import or depend on AgentKV/SGLang MLP code.
It reconstructs logical message-boundary prefixes with rolling hashes, builds
per-prefix behavioral features, trains discrete-hazard MLPs, and compares
Static, conditional Shift, and age-aware Re-predict strategies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset


FEATURE_NAMES = (
    [f"log_recent_gap_{i+1}" for i in range(8)]
    + [f"recent_gap_mask_{i+1}" for i in range(8)]
    + ["log_gap_mean", "log_gap_std", "log_gap_min", "log_gap_max", "log_gap_ewma"]
    + ["log_reuse_count", "log_trajectory_requests", "log_consecutive_growth"]
    + ["log_last_growth", "log_growth_mean4", "log_growth_std4", "log_growth_ewma"]
    + ["log_prefix_tokens", "log_increment_tokens"]
)

BUCKETS = {
    "k5": [5.0, 20.0, 60.0, 180.0],
    "k10": [2.0, 5.0, 10.0, 20.0, 60.0, 180.0, 600.0, 1800.0, 7200.0],
    "k20": [1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 30.0, 45.0, 60.0,
             90.0, 120.0, 180.0, 300.0, 450.0, 600.0, 1200.0, 2400.0,
             7200.0],
}
AGES = [0.0, 5.0, 20.0, 60.0, 180.0, 600.0, 1800.0]
EVAL_AGES = [5.0, 20.0, 60.0, 180.0, 600.0]
EVAL_HORIZONS = [5.0, 20.0, 60.0]


def log1p(x: float) -> float:
    return math.log1p(max(0.0, float(x)))


def stable_json_hash(obj: object) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(raw.encode("utf-8", errors="replace"), digest_size=16).digest()


def chained_hash(previous: bytes, item_hash: bytes) -> bytes:
    return hashlib.blake2b(previous + item_hash, digest_size=16).digest()


def parse_timestamp(raw: str) -> float:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()


def split_for_anchor(anchor: bytes) -> int:
    value = int.from_bytes(hashlib.blake2b(anchor, digest_size=8).digest(), "big") % 100
    return 0 if value < 70 else (1 if value < 85 else 2)


def response_usage(response_body: object) -> dict:
    try:
        body = json.loads(response_body) if isinstance(response_body, str) else response_body
        usage = (body or {}).get("usage") or {}
        return usage if isinstance(usage, dict) else {}
    except Exception:
        return {}


def read_requests(dataset: Path) -> tuple[list[dict], dict]:
    requests: list[dict] = []
    malformed = 0
    t0 = time.time()
    with dataset.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, 1):
            try:
                outer = json.loads(line)
                prompt = json.loads(outer["prompt_body"])
                messages = prompt.get("messages") or []
                if not messages:
                    continue
                first_user = next((i for i, m in enumerate(messages) if m.get("role") == "user"), None)
                if first_user is None:
                    continue
                usage = response_usage(outer.get("response_body"))
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                if prompt_tokens <= 0:
                    prompt_tokens = max(1, len(outer.get("prompt_body", "")) // 4)
                tool_hash = stable_json_hash(prompt.get("tools") or [])
                scope = stable_json_hash({"model": prompt.get("model", ""), "tools": tool_hash.hex()})
                rolling = scope
                msg_hashes: list[bytes] = []
                msg_sizes: list[int] = []
                for msg in messages:
                    mh = stable_json_hash(msg)
                    msg_hashes.append(mh)
                    msg_sizes.append(max(1, len(json.dumps(msg, ensure_ascii=False, separators=(",", ":")))))
                for i in range(first_user + 1):
                    rolling = chained_hash(rolling, msg_hashes[i])
                anchor = rolling
                suffix_chars = sum(msg_sizes[first_user + 1 :])
                occurrences = []
                total_chars = sum(msg_sizes)
                rolling = scope
                consumed_chars = 0
                for i, (mh, nchars) in enumerate(zip(msg_hashes, msg_sizes)):
                    rolling = chained_hash(rolling, mh)
                    consumed_chars += nchars
                    if i < first_user:
                        continue
                    # Retain fixed prompt/tool overhead by subtracting only estimated suffix tokens.
                    suffix = max(0, total_chars - consumed_chars)
                    prefix_tokens = max(1, prompt_tokens - int(round(suffix / 4.0)))
                    increment_tokens = max(1, int(round(nchars / 4.0)))
                    occurrences.append((rolling, prefix_tokens, increment_tokens))
                requests.append({
                    "t": parse_timestamp(outer["start_time"]),
                    "line": line_no,
                    "anchor": anchor,
                    "split": split_for_anchor(anchor),
                    "prompt_tokens": prompt_tokens,
                    "occurrences": occurrences,
                })
            except Exception:
                malformed += 1
            if line_no % 1000 == 0:
                print(f"[parse] lines={line_no} requests={len(requests)} malformed={malformed} elapsed={time.time()-t0:.1f}s", flush=True)
    requests.sort(key=lambda row: (row["t"], row["line"]))
    meta = {"requests": len(requests), "malformed": malformed}
    return requests, meta


def behavior_features(gaps: deque, reuse_count: int, trajectory_requests: int,
                      consecutive_growth: int, growths: deque, prefix_tokens: int,
                      increment_tokens: int) -> list[float]:
    recent = list(gaps)[-8:][::-1]
    gap_values = recent + [0.0] * (8 - len(recent))
    masks = [1.0] * len(recent) + [0.0] * (8 - len(recent))
    if recent:
        arr = np.asarray(recent, dtype=np.float64)
        ewma = arr[-1]
        for value in arr[-2::-1]:
            ewma = 0.6 * value + 0.4 * ewma
        stats = [arr.mean(), arr.std(), arr.min(), arr.max(), ewma]
    else:
        stats = [0.0] * 5
    grow = list(growths)[-4:]
    if grow:
        ga = np.asarray(grow, dtype=np.float64)
        gewma = ga[0]
        for value in ga[1:]:
            gewma = 0.6 * value + 0.4 * gewma
        grow_stats = [ga[-1], ga.mean(), ga.std(), gewma]
    else:
        grow_stats = [0.0] * 4
    return (
        [log1p(v) for v in gap_values]
        + masks
        + [log1p(v) for v in stats]
        + [log1p(reuse_count), log1p(trajectory_requests), log1p(consecutive_growth)]
        + [log1p(v) for v in grow_stats]
        + [log1p(prefix_tokens), log1p(increment_tokens)]
    )


def build_dataset(dataset: Path, output: Path) -> dict:
    requests, meta = read_requests(dataset)
    if not requests:
        raise SystemExit("no valid requests")
    t_end = max(row["t"] for row in requests)
    anchor_state: dict[bytes, dict] = {}
    prefix_state: dict[bytes, dict] = {}
    xs: list[list[float]] = []
    durations: list[float] = []
    events: list[int] = []
    splits: list[int] = []
    histories: list[int] = []
    token_weights: list[float] = []
    sample_times: list[float] = []
    negative_gap = 0

    for req_i, req in enumerate(requests, 1):
        ast = anchor_state.setdefault(req["anchor"], {
            "requests": 0, "last_tokens": None, "growths": deque(maxlen=8),
            "consecutive": 0,
        })
        previous_tokens = ast["last_tokens"]
        growth = 0.0 if previous_tokens is None else max(0.0, req["prompt_tokens"] - previous_tokens)
        if previous_tokens is not None:
            ast["growths"].append(growth)
            ast["consecutive"] = ast["consecutive"] + 1 if growth > 0 else 0
        ast["requests"] += 1
        ast["last_tokens"] = req["prompt_tokens"]

        for prefix_id, prefix_tokens, increment_tokens in req["occurrences"]:
            pst = prefix_state.get(prefix_id)
            if pst is None:
                pst = {"last_t": None, "gaps": deque(maxlen=8), "hits": 0, "pending": None}
                prefix_state[prefix_id] = pst
            if pst["last_t"] is not None:
                gap = req["t"] - pst["last_t"]
                if gap < 0:
                    negative_gap += 1
                    continue
                previous_sample = pst["pending"]
                durations[previous_sample] = max(gap, 1e-6)
                events[previous_sample] = 1
                pst["gaps"].append(gap)
                pst["hits"] += 1
            history_count = len(pst["gaps"])
            feature = behavior_features(
                pst["gaps"], pst["hits"], ast["requests"], ast["consecutive"],
                ast["growths"], prefix_tokens, increment_tokens,
            )
            sample_idx = len(xs)
            xs.append(feature)
            durations.append(0.0)
            events.append(0)
            splits.append(req["split"])
            histories.append(history_count)
            token_weights.append(float(increment_tokens))
            sample_times.append(req["t"])
            pst["last_t"] = req["t"]
            pst["pending"] = sample_idx
        if req_i % 2000 == 0:
            print(f"[build] requests={req_i}/{len(requests)} samples={len(xs)} prefixes={len(prefix_state)}", flush=True)

    for pst in prefix_state.values():
        idx = pst["pending"]
        if idx is not None and events[idx] == 0:
            durations[idx] = max(t_end - pst["last_t"], 1e-6)

    x = np.asarray(xs, dtype=np.float32)
    duration = np.asarray(durations, dtype=np.float32)
    event = np.asarray(events, dtype=np.uint8)
    split = np.asarray(splits, dtype=np.uint8)
    history = np.asarray(histories, dtype=np.uint8)
    weight = np.asarray(token_weights, dtype=np.float32)
    sample_time = np.asarray(sample_times, dtype=np.float64)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, x=x, duration=duration, event=event, split=split,
                        history=history, weight=weight, sample_time=sample_time)
    eligible = history >= 1
    observed = eligible & (event == 1)
    quantiles = {}
    if observed.any():
        for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99):
            quantiles[str(q)] = float(np.quantile(duration[observed], q))
    meta.update({
        "samples": int(len(x)), "unique_prefixes": int(len(prefix_state)),
        "eligible_history_ge_1": int(eligible.sum()), "eligible_observed": int(observed.sum()),
        "split_eligible": {str(i): int((eligible & (split == i)).sum()) for i in range(3)},
        "gap_quantiles_s": quantiles, "negative_gap": negative_gap,
        "feature_names": FEATURE_NAMES, "label": "request-start to next request-start",
        "dataset": str(dataset), "output": str(output),
    })
    meta_path = output.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2), flush=True)
    return meta


class HazardMLP(nn.Module):
    def __init__(self, n_in: int, n_out: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 128), nn.ReLU(),
            nn.Linear(128, 128), nn.ReLU(),
            nn.Linear(128, n_out),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def hazard_loss(logits: torch.Tensor, duration: torch.Tensor, event: torch.Tensor,
                edges: torch.Tensor, weights: torch.Tensor | None = None) -> torch.Tensor:
    log_h = torch.nn.functional.logsigmoid(logits)
    log_s = torch.nn.functional.logsigmoid(-logits)
    idx = torch.bucketize(duration, edges, right=True)
    positions = torch.arange(edges.numel(), device=logits.device).unsqueeze(0)
    full_survival = (positions < idx.unsqueeze(1)).float()
    ll = (log_s * full_survival).sum(dim=1)
    finite_event = (event > 0.5) & (idx < edges.numel())
    if finite_event.any():
        rows = torch.nonzero(finite_event, as_tuple=False).squeeze(1)
        ll[rows] += log_h[rows, idx[rows]]
    censored_partial = (event <= 0.5) & (idx < edges.numel())
    if censored_partial.any():
        rows = torch.nonzero(censored_partial, as_tuple=False).squeeze(1)
        j = idx[rows]
        left = torch.where(j == 0, torch.zeros_like(duration[rows]), edges[j - 1])
        right_edge = edges[j]
        frac = ((duration[rows] - left) / (right_edge - left).clamp_min(1e-6)).clamp(0, 1)
        ll[rows] += frac * log_s[rows, j]
    loss = -ll
    if weights is not None:
        loss = loss * weights
    return loss.mean()


def expanded_landmarks(indices: np.ndarray, duration: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    out_i, out_a = [], []
    for age in AGES:
        valid = indices[duration[indices] > age + 1e-6]
        out_i.append(valid)
        out_a.append(np.full(len(valid), age, dtype=np.float32))
    return np.concatenate(out_i), np.concatenate(out_a)


@torch.no_grad()
def predict(model: nn.Module, x: np.ndarray, device: torch.device, batch_size: int = 16384) -> np.ndarray:
    model.eval()
    outputs = []
    for start in range(0, len(x), batch_size):
        xb = torch.from_numpy(x[start:start + batch_size]).to(device)
        outputs.append(torch.sigmoid(model(xb)).cpu().numpy())
    return np.concatenate(outputs) if outputs else np.empty((0, model.net[-1].out_features), np.float32)


def fit_one(data: dict, edges_list: list[float], kind: str, seed: int, out: Path,
            epochs: int, device: torch.device) -> dict:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    x = data["x"].astype(np.float32)
    duration = data["duration"].astype(np.float32)
    event = data["event"].astype(np.float32)
    split = data["split"]
    history = data["history"]
    base_train = np.where((split == 0) & (history >= 1) & (duration > 1e-6))[0]
    base_val = np.where((split == 1) & (history >= 1) & (duration > 1e-6))[0]
    mean = x[base_train].mean(0)
    std = x[base_train].std(0)
    std[std < 1e-5] = 1.0
    xz = (x - mean) / std
    if kind == "initial":
        train_i, train_a = base_train, np.zeros(len(base_train), np.float32)
        val_i, val_a = base_val, np.zeros(len(base_val), np.float32)
        train_x = xz[train_i]
        val_x = xz[val_i]
        age_mean, age_std = 0.0, 1.0
    else:
        train_i, train_a = expanded_landmarks(base_train, duration)
        val_i, val_a = expanded_landmarks(base_val, duration)
        age_log = np.log1p(train_a)
        age_mean, age_std = float(age_log.mean()), float(age_log.std())
        age_std = max(age_std, 1e-5)
        train_x = np.concatenate([xz[train_i], ((np.log1p(train_a)-age_mean)/age_std)[:,None]], axis=1)
        val_x = np.concatenate([xz[val_i], ((np.log1p(val_a)-age_mean)/age_std)[:,None]], axis=1)
    train_d = duration[train_i] - train_a
    val_d = duration[val_i] - val_a
    train_e = event[train_i]
    val_e = event[val_i]
    # Keep token weighting bounded so a few huge messages cannot dominate training.
    raw_w = np.sqrt(np.maximum(data["weight"][train_i].astype(np.float32), 1.0))
    train_w = raw_w / raw_w.mean()
    ds = TensorDataset(torch.from_numpy(train_x.astype(np.float32)),
                       torch.from_numpy(train_d.astype(np.float32)),
                       torch.from_numpy(train_e.astype(np.float32)),
                       torch.from_numpy(train_w.astype(np.float32)))
    gen = torch.Generator().manual_seed(seed)
    loader = DataLoader(ds, batch_size=8192, shuffle=True, generator=gen, num_workers=0)
    edges = torch.tensor(edges_list, dtype=torch.float32, device=device)
    model = HazardMLP(train_x.shape[1], len(edges_list)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    best_loss, best_state, patience = float("inf"), None, 3
    history_rows = []
    for epoch in range(1, epochs + 1):
        model.train(); running = 0.0; count = 0
        for xb, db, eb, wb in loader:
            xb, db, eb, wb = xb.to(device), db.to(device), eb.to(device), wb.to(device)
            loss = hazard_loss(model(xb), db, eb, edges, wb)
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
            running += float(loss.item()) * len(xb); count += len(xb)
        train_loss = running / max(count, 1)
        model.eval(); val_total = 0.0; val_count = 0
        with torch.no_grad():
            for start in range(0, len(val_x), 16384):
                xb = torch.from_numpy(val_x[start:start+16384].astype(np.float32)).to(device)
                db = torch.from_numpy(val_d[start:start+16384].astype(np.float32)).to(device)
                eb = torch.from_numpy(val_e[start:start+16384].astype(np.float32)).to(device)
                vl = hazard_loss(model(xb), db, eb, edges)
                val_total += float(vl.item()) * len(xb); val_count += len(xb)
        val_loss = val_total / max(val_count, 1)
        history_rows.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        print(f"[train] kind={kind} seed={seed} epoch={epoch} train={train_loss:.5f} val={val_loss:.5f}", flush=True)
        if val_loss < best_loss - 1e-4:
            best_loss = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            patience = 3
        else:
            patience -= 1
            if patience == 0:
                break
    model.load_state_dict(best_state)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": best_state, "n_in": train_x.shape[1], "n_out": len(edges_list),
        "edges": edges_list, "kind": kind, "seed": seed,
        "x_mean": mean.tolist(), "x_std": std.tolist(),
        "age_mean": age_mean, "age_std": age_std, "features": FEATURE_NAMES,
        "history": history_rows, "best_val_loss": best_loss,
    }, out)
    return {"checkpoint": str(out), "best_val_loss": best_loss, "epochs": history_rows}


def load_model(path: Path, device: torch.device) -> tuple[HazardMLP, dict]:
    blob = torch.load(path, map_location="cpu", weights_only=False)
    model = HazardMLP(int(blob["n_in"]), int(blob["n_out"]))
    model.load_state_dict(blob["state_dict"]); model.to(device); model.eval()
    return model, blob


def survival_at(hazards: np.ndarray, edges: np.ndarray, times: np.ndarray | float) -> np.ndarray:
    t = np.asarray(times, dtype=np.float64)
    if t.ndim == 0:
        t = np.full(hazards.shape[0], float(t))
    log_s_intervals = np.log(np.clip(1.0 - hazards.astype(np.float64), 1e-9, 1.0))
    out = np.zeros(hazards.shape[0], dtype=np.float64)
    left = 0.0
    for j, right in enumerate(edges):
        full = t >= right
        out[full] += log_s_intervals[full, j]
        partial = (t > left) & (t < right)
        if partial.any():
            frac = (t[partial] - left) / (right - left)
            out[partial] += frac * log_s_intervals[partial, j]
        left = right
    return np.exp(out)


def strategy_survival(hazards: np.ndarray, edges: np.ndarray, strategy: str,
                      age: float, r: np.ndarray | float) -> np.ndarray:
    rv = np.asarray(r, dtype=np.float64)
    if rv.ndim == 0:
        rv = np.full(hazards.shape[0], float(rv))
    if strategy == "shift":
        denom = survival_at(hazards, edges, age)
        return np.clip(survival_at(hazards, edges, age + rv) / np.clip(denom, 1e-9, None), 0, 1)
    return survival_at(hazards, edges, rv)


def evaluate_checkpoint(data: dict, initial_path: Path, landmark_path: Path,
                        device: torch.device) -> list[dict]:
    initial, ib = load_model(initial_path, device)
    landmark, lb = load_model(landmark_path, device)
    edges = np.asarray(ib["edges"], dtype=np.float64)
    x = data["x"].astype(np.float32)
    mean, std = np.asarray(ib["x_mean"], np.float32), np.asarray(ib["x_std"], np.float32)
    xz = (x - mean) / std
    test_base = np.where((data["split"] == 2) & (data["history"] >= 1) & (data["duration"] > 1e-6))[0]
    initial_h_all = predict(initial, xz[test_base], device)
    index_pos = {int(idx): pos for pos, idx in enumerate(test_base)}
    rows = []
    for age in EVAL_AGES:
        idx = test_base[data["duration"][test_base] > age + 1e-6]
        if len(idx) == 0:
            continue
        positions = np.asarray([index_pos[int(i)] for i in idx])
        initial_h = initial_h_all[positions]
        age_z = (math.log1p(age) - float(lb["age_mean"])) / float(lb["age_std"])
        lx = np.concatenate([xz[idx], np.full((len(idx), 1), age_z, np.float32)], axis=1)
        rep_h = predict(landmark, lx, device)
        residual = data["duration"][idx].astype(np.float64) - age
        event = data["event"][idx].astype(bool)
        weights = data["weight"][idx].astype(np.float64)
        weights = weights / max(weights.mean(), 1e-9)
        for strategy, hazards in (("static", initial_h), ("shift", initial_h), ("repredict", rep_h)):
            briers = {}
            weighted_briers = {}
            for horizon in EVAL_HORIZONS:
                known = event | (residual >= horizon)
                if not known.any():
                    continue
                y = (event & (residual <= horizon)).astype(np.float64)
                p = 1.0 - strategy_survival(hazards, edges, strategy, age, horizon)
                err = (p[known] - y[known]) ** 2
                briers[str(int(horizon))] = float(err.mean())
                weighted_briers[str(int(horizon))] = float(np.average(err, weights=weights[known]))
            # Discrete residual-bucket likelihood; censored rows contribute survival likelihood.
            bucket_edges = edges
            probs = []
            left = np.zeros(len(idx), dtype=np.float64)
            for right in bucket_edges:
                sl = strategy_survival(hazards, edges, strategy, age, left)
                sr = strategy_survival(hazards, edges, strategy, age, float(right))
                probs.append(np.clip(sl - sr, 1e-12, 1.0))
                left = np.full(len(idx), float(right))
            probs.append(np.clip(strategy_survival(hazards, edges, strategy, age, float(bucket_edges[-1])), 1e-12, 1.0))
            probs = np.stack(probs, axis=1)
            true_bin = np.searchsorted(bucket_edges, residual, side="right")
            likelihood = np.empty(len(idx), dtype=np.float64)
            likelihood[event] = probs[np.where(event)[0], true_bin[event]]
            likelihood[~event] = strategy_survival(hazards[~event], edges, strategy, age, residual[~event])
            nll_each = -np.log(np.clip(likelihood, 1e-12, 1.0))
            pred_bin = probs.argmax(axis=1)
            accuracy = float((pred_bin[event] == true_bin[event]).mean()) if event.any() else None
            rows.append({
                "age_s": age, "strategy": strategy, "n": int(len(idx)),
                "n_event": int(event.sum()), "nll": float(nll_each.mean()),
                "token_weighted_nll": float(np.average(nll_each, weights=weights)),
                "event_bucket_accuracy": accuracy, "brier": briers,
                "token_weighted_brier": weighted_briers,
            })
    return rows


def train_and_evaluate(data_path: Path, out_dir: Path, bucket_names: list[str],
                       seeds: list[int], epochs: int, device_name: str) -> dict:
    z = np.load(data_path, allow_pickle=False)
    data = {name: z[name] for name in z.files}
    device = torch.device(device_name)
    result = {"dataset": str(data_path), "device": str(device), "runs": []}
    for bucket in bucket_names:
        edges = BUCKETS[bucket]
        for seed in seeds:
            run_dir = out_dir / bucket / f"seed_{seed}"
            initial_path = run_dir / "initial.pt"
            landmark_path = run_dir / "landmark.pt"
            initial_fit = fit_one(data, edges, "initial", seed, initial_path, epochs, device)
            landmark_fit = fit_one(data, edges, "landmark", seed, landmark_path, epochs, device)
            metrics = evaluate_checkpoint(data, initial_path, landmark_path, device)
            run = {"bucket": bucket, "edges_s": edges, "seed": seed,
                   "initial_fit": initial_fit, "landmark_fit": landmark_fit,
                   "metrics": metrics}
            (run_dir / "metrics.json").write_text(json.dumps(run, indent=2) + "\n")
            result["runs"].append(run)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "all_results.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    write_report(result, out_dir / "report.md")
    return result


def write_report(result: dict, path: Path) -> None:
    grouped: dict[tuple, list[dict]] = {}
    for run in result["runs"]:
        for row in run["metrics"]:
            grouped.setdefault((run["bucket"], row["age_s"], row["strategy"]), []).append(row)
    lines = ["# Standalone Prefix Reuse MLP Experiment", "",
             "Label time is request-start to next request-start; no radix tree or serving code is used.", "",
             "## Mean over seeds", "",
             "| buckets | age(s) | strategy | N | NLL | token-NLL | Brier@5 | Brier@20 | Brier@60 | token-Brier@20 |", 
             "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key in sorted(grouped, key=lambda k: (int(k[0][1:]), k[1], k[2])):
        bucket, age, strategy = key
        rows = grouped[key]
        mean = lambda vals: float(np.mean(vals)) if vals else float("nan")
        lines.append(
            f"| {bucket} | {age:.0f} | {strategy} | {int(mean([r['n'] for r in rows]))} | "
            f"{mean([r['nll'] for r in rows]):.5f} | {mean([r['token_weighted_nll'] for r in rows]):.5f} | "
            f"{mean([r['brier'].get('5', float('nan')) for r in rows]):.5f} | "
            f"{mean([r['brier'].get('20', float('nan')) for r in rows]):.5f} | "
            f"{mean([r['brier'].get('60', float('nan')) for r in rows]):.5f} | "
            f"{mean([r['token_weighted_brier'].get('20', float('nan')) for r in rows]):.5f} |"
        )
    lines += ["", "## Pairwise winner counts", ""]
    for bucket in sorted({r["bucket"] for r in result["runs"]}, key=lambda x: int(x[1:])):
        subset = {k: v for k, v in grouped.items() if k[0] == bucket}
        lines.append(f"### {bucket}")
        lines.append("")
        for age in EVAL_AGES:
            scores = {}
            for strategy in ("static", "shift", "repredict"):
                rows = subset.get((bucket, age, strategy), [])
                if rows:
                    scores[strategy] = float(np.mean([r["token_weighted_brier"].get("20", float("nan")) for r in rows]))
            if scores:
                winner = min(scores, key=scores.get)
                lines.append(f"- age={age:.0f}s: Brier@20 winner **{winner}**, " + ", ".join(f"{k}={v:.5f}" for k,v in scores.items()))
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dataset", type=Path, required=True)
    b.add_argument("--output", type=Path, required=True)
    r = sub.add_parser("run")
    r.add_argument("--data", type=Path, required=True)
    r.add_argument("--out-dir", type=Path, required=True)
    r.add_argument("--buckets", nargs="+", choices=sorted(BUCKETS), default=sorted(BUCKETS))
    r.add_argument("--seeds", nargs="+", type=int, default=[41, 42, 43])
    r.add_argument("--epochs", type=int, default=15)
    r.add_argument("--device", default="cuda")
    args = parser.parse_args()
    if args.cmd == "build":
        build_dataset(args.dataset, args.output)
    else:
        result = train_and_evaluate(args.data, args.out_dir, args.buckets, args.seeds, args.epochs, args.device)
        print(json.dumps({"runs": len(result["runs"]), "report": str(args.out_dir / 'report.md')}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
