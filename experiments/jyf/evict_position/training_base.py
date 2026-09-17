#!/usr/bin/env python3
"""Ablate server-visible features for wall-clock prefix-reuse hazards."""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


EDGES = (2.0, 5.0, 10.0, 20.0, 60.0, 180.0, 600.0, 1800.0, 7200.0)
HORIZONS = (5.0, 20.0, 60.0)

ORIGINAL = [
    "node_tokens", "path_tokens", "depth", "age_events", "lru_frac",
    "parent_hits", "siblings", "warm_sibling_fraction", "owner_turn",
    "is_cold", "hits", "gap_present", "recent_gap_events",
    "is_openhands", "is_request", "is_swa",
]
EVENT_EXTRAS = ["idle_events", "gap_ewma_events", "gap_std_events"]
TIME_NAMES = [
    "age_seconds", "idle_seconds", "recent_gap_seconds",
    "gap_ewma_seconds", "gap_std_seconds",
]
ALL_NAMES = ORIGINAL + EVENT_EXTRAS + TIME_NAMES


def without(names, *removed):
    removed = set(removed)
    return [name for name in names if name not in removed]


ORIGINAL_TIME16 = [
    "node_tokens", "path_tokens", "depth", "age_seconds", "lru_frac",
    "parent_hits", "siblings", "warm_sibling_fraction", "owner_turn",
    "is_cold", "hits", "gap_present", "recent_gap_seconds",
    "is_openhands", "is_request", "is_swa",
]
EVENT_CANDIDATE11 = [
    "node_tokens", "path_tokens", "age_events", "idle_events", "lru_frac",
    "hits", "gap_present", "recent_gap_events", "gap_ewma_events",
    "gap_std_events", "is_openhands",
]
TIME_CANDIDATE11 = [
    "node_tokens", "path_tokens", "age_seconds", "idle_seconds", "lru_frac",
    "hits", "gap_present", "recent_gap_seconds", "gap_ewma_seconds",
    "gap_std_seconds", "is_openhands",
]
BOTH_CANDIDATE16 = [
    "node_tokens", "path_tokens", "age_events", "age_seconds",
    "idle_events", "idle_seconds", "lru_frac", "hits", "gap_present",
    "recent_gap_events", "recent_gap_seconds", "gap_ewma_events",
    "gap_ewma_seconds", "gap_std_events", "gap_std_seconds", "is_openhands",
]
TIME_HISTORY = [
    "age_seconds", "idle_seconds", "hits", "gap_present",
    "recent_gap_seconds", "gap_ewma_seconds", "gap_std_seconds",
]
EVENT_HISTORY = [
    "age_events", "idle_events", "hits", "gap_present",
    "recent_gap_events", "gap_ewma_events", "gap_std_events",
]
FEATURE_SETS = {
    "original16": ORIGINAL,
    "original_time16": ORIGINAL_TIME16,
    "event_candidate11": EVENT_CANDIDATE11,
    "time_candidate11": TIME_CANDIDATE11,
    "both_candidate16": BOTH_CANDIDATE16,
    "only_event_history": EVENT_HISTORY,
    "only_time_history": TIME_HISTORY,
    "only_family": ["parent_hits", "siblings", "warm_sibling_fraction"],
    "only_lru": ["lru_frac"],
    "only_sizes": ["node_tokens", "path_tokens"],
    "time_minus_sizes": without(TIME_CANDIDATE11, "node_tokens", "path_tokens"),
    "time_minus_lru": without(TIME_CANDIDATE11, "lru_frac"),
    "time_minus_traffic": without(TIME_CANDIDATE11, "is_openhands"),
    "time_minus_history": without(TIME_CANDIDATE11, *TIME_HISTORY),
    "time_no_gap_present": without(TIME_CANDIDATE11, "gap_present"),
    "time_plus_parent_hits": TIME_CANDIDATE11 + ["parent_hits"],
    "time_plus_siblings": TIME_CANDIDATE11 + ["siblings"],
    "time_plus_warm_sibling_fraction": TIME_CANDIDATE11 + ["warm_sibling_fraction"],
    "time_plus_owner_turn": TIME_CANDIDATE11 + ["owner_turn"],
    "time_plus_swa": TIME_CANDIDATE11 + ["is_swa"],
    "time_plus_is_cold": TIME_CANDIDATE11 + ["is_cold"],
    "time_plus_age_events": TIME_CANDIDATE11 + ["age_events"],
    "time_plus_idle_events": TIME_CANDIDATE11 + ["idle_events"],
    "time_plus_recent_gap_events": TIME_CANDIDATE11 + ["recent_gap_events"],
    "time_plus_gap_ewma_events": TIME_CANDIDATE11 + ["gap_ewma_events"],
    "time_plus_gap_std_events": TIME_CANDIDATE11 + ["gap_std_events"],
    "time_plus_event_gap_stats": TIME_CANDIDATE11 + [
        "recent_gap_events", "gap_ewma_events", "gap_std_events",
    ],
    "both_minus_age_events": without(BOTH_CANDIDATE16, "age_events"),
    "both_minus_idle_events": without(BOTH_CANDIDATE16, "idle_events"),
    "both_minus_event_gap_stats": without(
        BOTH_CANDIDATE16, "recent_gap_events", "gap_ewma_events", "gap_std_events"
    ),
    "both_no_gap_present": without(BOTH_CANDIDATE16, "gap_present"),
    "both_minus_age_seconds": without(BOTH_CANDIDATE16, "age_seconds"),
    "both_minus_idle_seconds": without(BOTH_CANDIDATE16, "idle_seconds"),
    "both_minus_recent_gap_events": without(BOTH_CANDIDATE16, "recent_gap_events"),
    "both_minus_recent_gap_seconds": without(BOTH_CANDIDATE16, "recent_gap_seconds"),
    "both_minus_gap_ewma_events": without(BOTH_CANDIDATE16, "gap_ewma_events"),
    "both_minus_gap_ewma_seconds": without(BOTH_CANDIDATE16, "gap_ewma_seconds"),
    "both_minus_gap_std_events": without(BOTH_CANDIDATE16, "gap_std_events"),
    "both_minus_gap_std_seconds": without(BOTH_CANDIDATE16, "gap_std_seconds"),
    "both_minus_hits": without(BOTH_CANDIDATE16, "hits"),
    "both_minus_node_tokens": without(BOTH_CANDIDATE16, "node_tokens"),
    "both_minus_path_tokens": without(BOTH_CANDIDATE16, "path_tokens"),
    "both_minus_lru": without(BOTH_CANDIDATE16, "lru_frac"),
    "both_minus_traffic": without(BOTH_CANDIDATE16, "is_openhands"),
}


def split_digest(digest: str) -> int:
    value = int.from_bytes(hashlib.blake2b(digest.encode(), digest_size=8).digest(), "big") % 100
    return 0 if value < 70 else (1 if value < 85 else 2)


def choose_trace(trace_dir: Path) -> Path:
    traces = list(trace_dir.glob("frontier_pid*.jsonl"))
    if not traces:
        raise SystemExit(f"no frontier trace under {trace_dir}")
    return max(traces, key=lambda path: path.stat().st_size)


def load_trace(path: Path):
    frontiers = []
    demands = defaultdict(list)
    max_req = 0
    max_wall = 0.0
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            req = int(row.get("req_seq") or 0)
            wall = float(row.get("wall_s") or 0.0)
            max_req = max(max_req, req)
            max_wall = max(max_wall, wall)
            if row.get("kind") == "frontier":
                frontiers.append(row)
            elif row.get("kind") == "demand":
                demands[row["digest"]].append((req, wall))
    for values in demands.values():
        values.sort(key=lambda item: (item[0], item[1]))
    return frontiers, demands, max_req, max_wall


def log1p(value):
    return math.log1p(max(0.0, float(value)))


def summarize_gaps(values):
    if not values:
        return 0.0, 0.0
    ewma = float(values[0])
    for value in values[1:]:
        ewma = 0.6 * float(value) + 0.4 * ewma
    return ewma, float(np.std(values))


def make_features(candidate, req, wall, past_demands):
    siblings = max(0, int(candidate.get("siblings", 0)))
    warm_siblings = max(0, int(candidate.get("warm_siblings", 0)))
    recent_gap = int(candidate.get("recent_gap_req", -1))
    cold = int(candidate.get("cold", 0))
    traffic = candidate.get("owner_traffic", "")

    if cold:
        idle_events = max(0, int(candidate.get("age_requests", 0)))
        idle_seconds = max(0.0, float(candidate.get("age_s", 0.0)))
        idle_known = True
        gap_event_values = []
        gap_second_values = []
    else:
        idle_known = bool(past_demands)
        idle_events = req - past_demands[-1][0] if past_demands else 0
        idle_seconds = wall - past_demands[-1][1] if past_demands else 0.0
        event_points = [item[0] for item in past_demands[-9:]]
        wall_points = [item[1] for item in past_demands[-9:]]
        gap_event_values = np.diff(event_points).astype(np.float64).tolist() if len(event_points) >= 2 else []
        gap_second_values = np.diff(wall_points).astype(np.float64).tolist() if len(wall_points) >= 2 else []
        # The logged value belongs to the current node incarnation. Fall back
        # to it if trace-left truncation makes the reconstructed sequence stale.
        if recent_gap >= 0 and (not gap_event_values or int(gap_event_values[-1]) != recent_gap):
            gap_event_values = [float(recent_gap)]
            gap_second_values = []
        gap_event_values = gap_event_values[-8:]
        gap_second_values = gap_second_values[-8:]

    event_ewma, event_std = summarize_gaps(gap_event_values)
    second_ewma, second_std = summarize_gaps(gap_second_values)
    recent_gap_seconds = gap_second_values[-1] if gap_second_values else 0.0

    values = {
        "node_tokens": log1p(candidate.get("node_tokens", 0)),
        "path_tokens": log1p(candidate.get("path_tokens", 0)),
        "depth": log1p(candidate.get("depth", 0)),
        "age_events": log1p(candidate.get("age_requests", 0)),
        "age_seconds": log1p(candidate.get("age_s", 0.0)),
        "lru_frac": float(candidate.get("lru_frac", 0.0)),
        "parent_hits": log1p(candidate.get("parent_hits", 0)),
        "siblings": log1p(siblings),
        "warm_sibling_fraction": warm_siblings / max(siblings, 1),
        "owner_turn": log1p(candidate.get("owner_turn", 0)),
        "is_cold": float(cold),
        "hits": log1p(candidate.get("hits", 0)),
        "gap_present": float(recent_gap >= 0),
        "recent_gap_events": log1p(max(recent_gap, 0)),
        "is_openhands": float(traffic == "openhands"),
        "is_request": float(traffic == "request"),
        "is_swa": float(candidate.get("frontier") == "swa"),
        "idle_events": log1p(idle_events),
        "gap_ewma_events": log1p(event_ewma),
        "gap_std_events": log1p(event_std),
        "idle_seconds": log1p(max(0.0, idle_seconds)),
        "recent_gap_seconds": log1p(recent_gap_seconds),
        "gap_ewma_seconds": log1p(second_ewma),
        "gap_std_seconds": log1p(second_std),
    }
    return [values[name] for name in ALL_NAMES], idle_known


def build_dataset(frontiers, demands, max_req, max_wall):
    x, duration, events, splits, cold, tokens, digests = [], [], [], [], [], [], []
    skipped_left_truncated_warm = 0
    gap_checked = gap_matched = 0
    for frontier in frontiers:
        req = int(frontier.get("req_seq") or 0)
        wall = float(frontier.get("wall_s") or 0.0)
        for candidate in frontier.get("candidates") or []:
            digest = candidate["digest"]
            times = demands.get(digest, ())
            reqs = [item[0] for item in times]
            past_end = bisect.bisect_right(reqs, req)
            past = list(times[:past_end])
            future = times[past_end] if past_end < len(times) else None
            features, idle_known = make_features(candidate, req, wall, past)
            if not idle_known:
                skipped_left_truncated_warm += 1
                continue
            recent_gap = int(candidate.get("recent_gap_req", -1))
            if recent_gap >= 0 and len(past) >= 2:
                gap_checked += 1
                gap_matched += int(past[-1][0] - past[-2][0] == recent_gap)
            if future is not None:
                d = max(float(future[1]) - wall, 1e-6)
                observed = 1.0
            else:
                d = max(max_wall - wall, 1e-6)
                observed = 0.0
            x.append(features)
            duration.append(d)
            events.append(observed)
            splits.append(split_digest(digest))
            cold.append(int(candidate.get("cold", 0)))
            tokens.append(max(1, int(candidate.get("kv_tokens", 0))))
            digests.append(digest)
    return {
        "x": np.asarray(x, np.float32),
        "duration": np.asarray(duration, np.float32),
        "event": np.asarray(events, np.float32),
        "split": np.asarray(splits, np.uint8),
        "cold": np.asarray(cold, np.uint8),
        "tokens": np.asarray(tokens, np.float32),
        "digests": np.asarray(digests),
        "meta": {
            "frontiers": len(frontiers),
            "rows": len(x),
            "unique_digests": len(set(digests)),
            "skipped_left_truncated_warm": skipped_left_truncated_warm,
            "recent_gap_consistency": gap_matched / max(gap_checked, 1),
            "max_req": max_req,
            "max_wall": max_wall,
            "time_unit": "seconds",
            "label": "frontier wall_s to next demand wall_s",
            "bucket_edges_s": list(EDGES),
        },
    }


class HazardNet(nn.Module):
    def __init__(self, n_in):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 128), nn.ReLU(),
            nn.Linear(128, 128), nn.ReLU(),
            nn.Linear(128, len(EDGES)),
        )

    def forward(self, x):
        return self.net(x)


def hazard_loss(logits, duration, event, edges, weights=None):
    log_h = torch.nn.functional.logsigmoid(logits)
    log_s = torch.nn.functional.logsigmoid(-logits)
    index = torch.bucketize(duration, edges, right=True)
    positions = torch.arange(edges.numel(), device=logits.device).unsqueeze(0)
    ll = (log_s * (positions < index.unsqueeze(1))).sum(dim=1)
    finite_event = (event > 0.5) & (index < edges.numel())
    if finite_event.any():
        rows = torch.nonzero(finite_event, as_tuple=False).squeeze(1)
        ll[rows] += log_h[rows, index[rows]]
    partial_censor = (event <= 0.5) & (index < edges.numel())
    if partial_censor.any():
        rows = torch.nonzero(partial_censor, as_tuple=False).squeeze(1)
        j = index[rows]
        left = torch.where(j == 0, torch.zeros_like(duration[rows]), edges[j - 1])
        fraction = ((duration[rows] - left) / (edges[j] - left).clamp_min(1e-6)).clamp(0, 1)
        ll[rows] += fraction * log_s[rows, j]
    loss = -ll
    if weights is not None:
        loss = loss * weights
    return loss.mean()


def survival_at(hazards, times):
    hazards = np.asarray(hazards, np.float64)
    times = np.asarray(times, np.float64)
    if times.ndim == 0:
        times = np.full(len(hazards), float(times))
    log_intervals = np.log(np.clip(1.0 - hazards, 1e-9, 1.0))
    log_survival = np.zeros(len(hazards), np.float64)
    left = 0.0
    for j, right in enumerate(EDGES):
        full = times >= right
        log_survival[full] += log_intervals[full, j]
        partial = (times > left) & (times < right)
        if partial.any():
            log_survival[partial] += ((times[partial] - left) / (right - left)) * log_intervals[partial, j]
        left = right
    return np.exp(log_survival)


def censor_nll(hazards, duration, event):
    hazards = np.clip(np.asarray(hazards, np.float64), 1e-9, 1 - 1e-9)
    duration = np.asarray(duration, np.float64)
    event = np.asarray(event, bool)
    edges = np.asarray(EDGES)
    index = np.searchsorted(edges, duration, side="right")
    out = np.zeros(len(duration), np.float64)
    for i, j in enumerate(index):
        if j:
            out[i] -= np.log(1.0 - hazards[i, :j]).sum()
        if event[i] and j < len(edges):
            out[i] -= math.log(hazards[i, j])
        elif not event[i] and j < len(edges):
            left = 0.0 if j == 0 else edges[j - 1]
            fraction = min(1.0, max(0.0, (duration[i] - left) / (edges[j] - left)))
            out[i] -= fraction * math.log(1.0 - hazards[i, j])
    return out


def auc_score(y, score):
    y = np.asarray(y, dtype=bool)
    score = np.asarray(score)
    positive, negative = int(y.sum()), int((~y).sum())
    if not positive or not negative:
        return None
    order = np.argsort(score, kind="stable")
    sorted_score = score[order]
    ranks = np.empty(len(score), float)
    start = 0
    while start < len(score):
        end = start + 1
        while end < len(score) and sorted_score[end] == sorted_score[start]:
            end += 1
        ranks[order[start:end]] = 0.5 * (start + 1 + end)
        start = end
    return float((ranks[y].sum() - positive * (positive + 1) / 2) / (positive * negative))


def average_precision(y, score):
    y = np.asarray(y, dtype=bool)
    if not y.sum():
        return None
    order = np.argsort(-score, kind="stable")
    yy, ss = y[order], score[order]
    ends = np.r_[np.where(ss[1:] != ss[:-1])[0], len(ss) - 1]
    true_positive = np.cumsum(yy)[ends]
    precision = true_positive / (ends + 1)
    recall_delta = np.diff(np.r_[0, true_positive / y.sum()])
    return float(np.sum(precision * recall_delta))


def metric_block(duration, event, hazards, tokens, subset):
    selected_nll = subset & (duration > 1e-6)
    result = {
        "censor_nll": float(censor_nll(hazards[selected_nll], duration[selected_nll], event[selected_nll]).mean())
    }
    for horizon in HORIZONS:
        known = (event > 0.5) & (duration <= horizon) | (duration >= horizon)
        selected = subset & known
        yy = ((event[selected] > 0.5) & (duration[selected] <= horizon)).astype(np.float32)
        pp = np.clip(1.0 - survival_at(hazards[selected], horizon), 1e-6, 1 - 1e-6)
        weight = tokens[selected]
        brier = (pp - yy) ** 2
        nll = -(yy * np.log(pp) + (1 - yy) * np.log(1 - pp))
        result[str(int(horizon))] = {
            "n": int(selected.sum()),
            "positive_rate": float(yy.mean()),
            "auc": auc_score(yy, pp),
            "ap": average_precision(yy, pp),
            "brier": float(brier.mean()),
            "nll": float(nll.mean()),
            "token_brier": float(np.average(brier, weights=weight)),
        }
    return result


def fit_one(data, names, seed, args):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    device = torch.device(args.device)
    name_to_index = {name: index for index, name in enumerate(ALL_NAMES)}
    columns = [name_to_index[name] for name in names]
    raw = data["x"]
    train = data["split"] == 0
    val = data["split"] == 1
    test = data["split"] == 2
    mean = raw[train].mean(0)
    std = raw[train].std(0)
    std[std < 1e-5] = 1.0
    z = ((raw - mean) / std).astype(np.float32)
    excluded = np.ones(len(ALL_NAMES), dtype=bool)
    excluded[columns] = False
    z[:, excluded] = 0.0

    train_x = torch.from_numpy(z[train]).to(device)
    train_d = torch.from_numpy(data["duration"][train]).to(device)
    train_e = torch.from_numpy(data["event"][train]).to(device)
    val_x = torch.from_numpy(z[val]).to(device)
    val_d = torch.from_numpy(data["duration"][val]).to(device)
    val_e = torch.from_numpy(data["event"][val]).to(device)
    def balanced_weights(mask):
        raw_weight = np.sqrt(np.maximum(data["tokens"][mask], 1.0)).astype(np.float32)
        groups = data["cold"][mask]
        result = np.zeros(len(raw_weight), np.float32)
        present = np.unique(groups)
        for group in present:
            chosen = groups == group
            result[chosen] = raw_weight[chosen] / raw_weight[chosen].sum() * len(raw_weight) / len(present)
        return result
    train_w = torch.from_numpy(balanced_weights(train)).to(device)
    val_w = torch.from_numpy(balanced_weights(val)).to(device)
    edges = torch.tensor(EDGES, dtype=torch.float32, device=device)
    # Every ablation uses the same input width. For a fixed seed, all weights
    # start identically; excluded features are represented by zero columns.
    model = HazardNet(len(ALL_NAMES)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    generator = torch.Generator(device=device).manual_seed(seed)
    best_loss, best_state, stale = float("inf"), None, 0
    for epoch in range(args.epochs):
        model.train()
        permutation = torch.randperm(len(train_x), generator=generator, device=device)
        for start in range(0, len(train_x), args.batch_size):
            index = permutation[start : start + args.batch_size]
            loss = hazard_loss(model(train_x[index]), train_d[index], train_e[index], edges, train_w[index])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            validation = float(hazard_loss(model(val_x), val_d, val_e, edges, val_w).cpu())
        if validation < best_loss - 1e-5:
            best_loss = validation
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= args.patience:
            break
    model.load_state_dict(best_state)
    if getattr(args, 'checkpoint_dir', None):
        torch.save(dict(state_dict=best_state, mean=mean, std=std, names=names,
                        all_names=ALL_NAMES, edges=EDGES, seed=seed,
                        validation_nll=best_loss), args.checkpoint_dir / f'seed_{seed}.pt')
    model.eval()
    with torch.no_grad():
        hazards = torch.sigmoid(model(torch.from_numpy(z).to(device))).cpu().numpy()
    blocks = {}
    for subset_name, subset in {
        "all": test,
        "cold": test & (data["cold"] == 1),
        "warm": test & (data["cold"] == 0),
    }.items():
        blocks[subset_name] = metric_block(
            data["duration"], data["event"], hazards, data["tokens"], subset
        )
    return {"seed": seed, "epochs": epoch + 1, "best_val_nll": best_loss, "metrics": blocks}, hazards


def summarize(runs):
    summary = {}
    for feature_set, feature_runs in runs.items():
        summary[feature_set] = {}
        for subset in ("all", "cold", "warm"):
            summary[feature_set][subset] = {}
            for horizon in (str(int(value)) for value in HORIZONS):
                summary[feature_set][subset][horizon] = {}
                for metric in ("nll", "brier", "auc", "ap"):
                    values = np.asarray(
                        [run["metrics"][subset][horizon][metric] for run in feature_runs], float
                    )
                    summary[feature_set][subset][horizon][metric] = {
                        "mean": float(np.nanmean(values)), "std": float(np.nanstd(values))
                    }
    return summary


def write_report(path, data, summary, ensemble_metrics, seed_count):
    lines = [
        "# Wall-clock real-frontier feature ablation",
        "",
        f"Each row uses the same fixed-width two-layer 128-hidden-unit hazard MLP and a {seed_count}-seed hazard ensemble. Prefix digests are split 70/15/15.",
        "The label is seconds from frontier `wall_s` to the next demand `wall_s`; K=10 finite edges are 2/5/10/20/60/180/600/1800/7200 seconds.",
        "Training uses censor-aware discrete-hazard NLL, sqrt-token weights, and equal total cold/warm weight.",
        "",
        f"Rows: {data['meta']['rows']}; unique digests: {data['meta']['unique_digests']}; "
        f"left-truncated warm rows excluded: {data['meta']['skipped_left_truncated_warm']}.",
        "",
    ]
    for subset in ("all", "cold", "warm"):
        lines += [
            f"## {subset}", "",
            "| features | censor NLL ↓ | NLL@5s ↓ | AUC@5s ↑ | NLL@20s ↓ | AUC@20s ↑ | NLL@60s ↓ | AUC@60s ↑ |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for feature_set in ensemble_metrics:
            block = ensemble_metrics[feature_set][subset]
            lines.append(
                f"| {feature_set} | {block['censor_nll']:.5f} | {block['5']['nll']:.5f} | {block['5']['auc']:.4f} | "
                f"{block['20']['nll']:.5f} | {block['20']['auc']:.4f} | "
                f"{block['60']['nll']:.5f} | {block['60']['auc']:.4f} |"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[41, 42, 43])
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--feature-sets", nargs="+", choices=sorted(FEATURE_SETS))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    trace = choose_trace(args.trace_dir)
    frontiers, demands, max_req, max_wall = load_trace(trace)
    data = build_dataset(frontiers, demands, max_req, max_wall)
    print(json.dumps(data["meta"], indent=2), flush=True)
    runs = {}
    ensemble_metrics = {}
    selected_sets = FEATURE_SETS if not args.feature_sets else {
        name: FEATURE_SETS[name] for name in args.feature_sets
    }
    for feature_set, names in selected_sets.items():
        runs[feature_set] = []
        predictions = []
        for seed in args.seeds:
            print(f"[train] {feature_set} seed={seed}", flush=True)
            run, hazards = fit_one(data, names, seed, args)
            runs[feature_set].append(run)
            predictions.append(hazards)
            print(f"  val={run['best_val_nll']:.6f} epochs={run['epochs']}", flush=True)
        ensemble_hazards = np.mean(predictions, axis=0)
        test = data["split"] == 2
        ensemble_metrics[feature_set] = {}
        for subset_name, subset in {
            "all": test,
            "cold": test & (data["cold"] == 1),
            "warm": test & (data["cold"] == 0),
        }.items():
            ensemble_metrics[feature_set][subset_name] = metric_block(
                data["duration"], data["event"], ensemble_hazards, data["tokens"], subset
            )
    summary = summarize(runs)
    payload = {
        "trace": str(trace), "meta": data["meta"], "all_feature_names": ALL_NAMES,
        "feature_sets": selected_sets, "runs": runs, "summary": summary,
        "ensemble_metrics": ensemble_metrics,
    }
    (args.output_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
    write_report(args.output_dir / "report.md", data, summary, ensemble_metrics, len(args.seeds))
    print(args.output_dir / "report.md")


if __name__ == "__main__":
    main()
