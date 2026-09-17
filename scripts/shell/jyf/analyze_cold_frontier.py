#!/usr/bin/env python3
"""Label real frontier snapshots with future demand and compare cold predictors."""

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
from torch.utils.data import DataLoader, TensorDataset


HORIZONS = (5, 20, 100)


def mean(xs):
    return float(np.mean(xs)) if xs else None


def percentile(xs, q):
    return float(np.quantile(xs, q)) if xs else None


def choose_trace(trace_dir: Path) -> Path:
    files = list(trace_dir.glob("frontier_pid*.jsonl"))
    if not files:
        raise SystemExit(f"no frontier traces in {trace_dir}")
    return max(files, key=lambda p: p.stat().st_size)


def load_trace(path: Path):
    frontiers, victims = [], []
    demands = defaultdict(list)
    max_req = 0
    with path.open() as f:
        for line in f:
            row = json.loads(line)
            kind = row.get("kind")
            max_req = max(max_req, int(row.get("req_seq") or 0))
            if kind == "frontier":
                frontiers.append(row)
            elif kind == "victim":
                victims.append(row)
            elif kind == "demand":
                demands[row["digest"]].append(int(row["req_seq"]))
    for values in demands.values():
        values.sort()
    return frontiers, victims, demands, max_req


def frontier_summary(frontiers, victims):
    result = {"events": len(frontiers), "victims": len(victims), "frontier": {}}
    for kind in ("full", "swa"):
        rows = [r[kind] for r in frontiers if kind in r and r[kind]["nodes"]]
        candidates = [c for event in frontiers for c in (event.get("candidates") or []) if c.get("frontier") == kind]
        unique = {c["digest"] for c in candidates}
        unique_cold = {c["digest"] for c in candidates if c.get("cold")}
        nodes = sum(r["nodes"] for r in rows)
        tokens = sum(r["tokens"] for r in rows)
        cold_nodes = sum(r["cold_nodes"] for r in rows)
        cold_tokens = sum(r["cold_tokens"] for r in rows)
        result["frontier"][kind] = {
            "events_nonempty": len(rows),
            "candidate_exposures": nodes,
            "token_exposures": tokens,
            "cold_candidate_exposures": cold_nodes,
            "cold_token_exposures": cold_tokens,
            "unique_candidates": len(unique),
            "unique_cold_candidates": len(unique_cold),
            "unique_cold_fraction": len(unique_cold) / len(unique) if unique else None,
            "aggregate_cold_node_fraction": cold_nodes / nodes if nodes else None,
            "aggregate_cold_token_fraction": cold_tokens / tokens if tokens else None,
            "event_cold_node_fraction_mean": mean([r["cold_nodes"] / r["nodes"] for r in rows]),
            "event_cold_node_fraction_p50": percentile([r["cold_nodes"] / r["nodes"] for r in rows], .5),
            "event_cold_node_fraction_p90": percentile([r["cold_nodes"] / r["nodes"] for r in rows], .9),
            "event_cold_token_fraction_mean": mean([r["cold_tokens"] / r["tokens"] for r in rows if r["tokens"]]),
        }
    if victims:
        result["victim_cold_node_fraction"] = sum(int(v.get("cold", 0)) for v in victims) / len(victims)
        total = sum(int(v.get("kv_tokens", 0)) for v in victims)
        result["victim_cold_token_fraction"] = (
            sum(int(v.get("kv_tokens", 0)) for v in victims if v.get("cold")) / total if total else None
        )
    return result


def split_digest(digest: str) -> int:
    value = int.from_bytes(hashlib.blake2b(digest.encode(), digest_size=8).digest(), "big") % 100
    return 0 if value < 70 else (1 if value < 85 else 2)


def row_features(c):
    siblings = max(0, int(c.get("siblings", 0)))
    warm_siblings = max(0, int(c.get("warm_siblings", 0)))
    gap = int(c.get("recent_gap_req", -1))
    traffic = c.get("owner_traffic", "")
    return [
        math.log1p(max(0, int(c.get("node_tokens", 0)))),
        math.log1p(max(0, int(c.get("path_tokens", 0)))),
        math.log1p(max(0, int(c.get("depth", 0)))),
        math.log1p(max(0, int(c.get("age_requests", 0)))),
        float(c.get("lru_frac", 0.0)),
        math.log1p(max(0, int(c.get("parent_hits", 0)))),
        math.log1p(siblings),
        warm_siblings / max(siblings, 1),
        math.log1p(max(0, int(c.get("owner_turn", 0)))),
        float(c.get("cold", 0)),
        math.log1p(max(0, int(c.get("hits", 0)))),
        float(gap >= 0),
        math.log1p(max(gap, 0)),
        float(traffic == "openhands"),
        float(traffic == "request"),
        float(c.get("frontier") == "swa"),
    ]


FEATURE_NAMES = [
    "log_node_tokens", "log_path_tokens", "log_depth", "log_age_requests",
    "lru_frac", "log_parent_hits", "log_siblings", "warm_sibling_fraction",
    "log_owner_turn", "cold", "log_hits", "gap_present", "log_recent_gap_req",
    "is_openhands", "is_request", "is_swa",
]
COLD_STATIC = [0, 1, 2, 3, 4, 5, 6, 7, 8, 13, 14, 15]


def build_rows(frontiers, demands, max_req, horizon):
    rows = []
    for event in frontiers:
        req = int(event.get("req_seq") or 0)
        for c in event.get("candidates") or []:
            future = demands.get(c["digest"], ())
            pos = bisect.bisect_right(future, req)
            next_req = future[pos] if pos < len(future) else None
            observed_positive = next_req is not None and next_req - req <= horizon
            fully_observed = req + horizon <= max_req
            if not observed_positive and not fully_observed:
                continue
            rows.append({
                "digest": c["digest"], "split": split_digest(c["digest"]),
                "cold": int(c.get("cold", 0)), "x": row_features(c),
                "y": int(observed_positive), "tokens": max(1, int(c.get("kv_tokens", 0))),
                "next_distance": None if next_req is None else next_req - req,
            })
    return rows


def auc_score(y, score):
    y = np.asarray(y, dtype=bool); score = np.asarray(score)
    n_pos, n_neg = y.sum(), (~y).sum()
    if not n_pos or not n_neg:
        return None
    order = np.argsort(score, kind="stable")
    ranks = np.empty(len(score), float); ranks[order] = np.arange(1, len(score) + 1)
    # Average tied ranks.
    for value in np.unique(score):
        idx = np.where(score == value)[0]
        if len(idx) > 1: ranks[idx] = ranks[idx].mean()
    return float((ranks[y].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def average_precision(y, score):
    y = np.asarray(y, dtype=bool); score = np.asarray(score)
    if not y.sum(): return None
    order = np.argsort(-score, kind="stable"); yy = y[order]; ss = score[order]
    # Integrate precision over recall at distinct score thresholds. This makes
    # tied/constant predictors deterministic (constant AP == prevalence).
    ends = np.r_[np.where(ss[1:] != ss[:-1])[0], len(ss) - 1]
    tp = np.cumsum(yy)[ends]
    precision = tp / (ends + 1)
    delta_recall = np.diff(np.r_[0, tp / y.sum()])
    return float(np.sum(precision * delta_recall))


def metrics(y, p, tokens):
    y = np.asarray(y, float); p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    tokens = np.asarray(tokens, float)
    brier = (p - y) ** 2
    nll = -(y * np.log(p) + (1-y) * np.log(1-p))
    order = np.argsort(-p); k = max(1, len(y) // 10); top = order[:k]
    return {
        "n": len(y), "positive_rate": float(y.mean()), "auc": auc_score(y, p),
        "ap": average_precision(y, p), "brier": float(brier.mean()),
        "token_brier": float(np.average(brier, weights=tokens)),
        "nll": float(nll.mean()),
        "top10_positive_recall": float(y[top].sum() / y.sum()) if y.sum() and np.ptp(p) > 1e-12 else None,
        "top10_token_positive_recall": float((tokens[top] * y[top]).sum() / (tokens*y).sum()) if (tokens*y).sum() and np.ptp(p) > 1e-12 else None,
    }


class Net(nn.Module):
    def __init__(self, n_in, hidden):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(n_in, hidden), nn.ReLU(), nn.Linear(hidden, 1)) if hidden else nn.Linear(n_in, 1)
    def forward(self, x): return self.net(x).squeeze(1)


def train_net(x, y, train, val, hidden, seed):
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    mean = x[train].mean(0); std = x[train].std(0); std[std < 1e-5] = 1
    z = ((x - mean) / std).astype(np.float32)
    model = Net(x.shape[1], hidden)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3 if hidden else 5e-2, weight_decay=1e-4)
    ds = TensorDataset(torch.from_numpy(z[train]), torch.from_numpy(y[train].astype(np.float32)))
    loader = DataLoader(ds, batch_size=4096, shuffle=True, generator=torch.Generator().manual_seed(seed))
    max_epochs, patience_limit = (30, 4) if hidden else (200, 15)
    best, state, patience = float("inf"), None, patience_limit
    for _ in range(max_epochs):
        model.train()
        for xb, yb in loader:
            loss = nn.functional.binary_cross_entropy_with_logits(model(xb), yb)
            opt.zero_grad(); loss.backward(); opt.step()
        model.eval()
        with torch.no_grad():
            vl = nn.functional.binary_cross_entropy_with_logits(model(torch.from_numpy(z[val])), torch.from_numpy(y[val].astype(np.float32))).item()
        if vl < best - 1e-5:
            best, state, patience = vl, {k:v.detach().clone() for k,v in model.state_dict().items()}, patience_limit
        else:
            patience -= 1
            if patience == 0: break
    model.load_state_dict(state); model.eval()
    with torch.no_grad(): p = torch.sigmoid(model(torch.from_numpy(z))).numpy()
    return p


def ensemble(x, y, train, val, hidden, seeds=(41, 42, 43)):
    return np.mean([train_net(x, y, train, val, hidden, seed) for seed in seeds], axis=0)


def compare(rows):
    x = np.asarray([r["x"] for r in rows], np.float32)
    y = np.asarray([r["y"] for r in rows], np.uint8)
    split = np.asarray([r["split"] for r in rows], np.uint8)
    cold = np.asarray([r["cold"] for r in rows], bool)
    tokens = np.asarray([r["tokens"] for r in rows], np.float32)
    train_all, val_all = np.where(split == 0)[0], np.where(split == 1)[0]
    train_cold, val_cold = np.where((split == 0) & cold)[0], np.where((split == 1) & cold)[0]
    test = np.where((split == 2) & cold)[0]
    if not len(train_cold) or not len(val_cold) or not len(test):
        return {"error": "insufficient cold rows", "counts": [len(train_cold),len(val_cold),len(test)]}
    prior = float(y[train_cold].mean())
    strategies = {
        "pessimistic_zero": np.full(len(rows), 1e-6),
        "cold_global_prior": np.full(len(rows), prior),
        # The heuristics are calibrated on cold training rows so their Brier/NLL
        # are comparable to learned predictors, not just their ranking metrics.
        "lru_recency_calibrated": train_net(x[:, [4]], y, train_cold, val_cold, 0, 42),
        "parent_sibling_calibrated": train_net(x[:, [5, 6, 7]], y, train_cold, val_cold, 0, 42),
        "unified_logistic": train_net(x, y, train_all, val_all, 0, 42),
        "unified_mlp_3seed_ensemble": ensemble(x, y, train_all, val_all, 64),
    }
    cx = x[:, COLD_STATIC]
    strategies["cold_only_logistic"] = train_net(cx, y, train_cold, val_cold, 0, 42)
    strategies["cold_only_mlp_3seed_ensemble"] = ensemble(cx, y, train_cold, val_cold, 64)
    return {
        "counts": {"all": len(rows), "cold": int(cold.sum()), "cold_train":len(train_cold), "cold_val":len(val_cold), "cold_test":len(test)},
        "feature_names": FEATURE_NAMES, "cold_static_features": [FEATURE_NAMES[i] for i in COLD_STATIC],
        "strategies_on_cold_test": {name: metrics(y[test], p[test], tokens[test]) for name,p in strategies.items()},
    }


def write_report(result, path):
    def fmt(v, digits=4):
        return "—" if v is None else f"{v:.{digits}f}"
    s = result["frontier_summary"]
    lines = ["# Cold Predictor Experiment", "", f"Trace: `{result['trace']}`", "",
             "## Cold share in real LRU eviction frontier", "",
             "| frontier | events | candidate exposures | cold node fraction | cold token fraction | event p50 / p90 |",
             "|---|---:|---:|---:|---:|---:|"]
    for kind, r in s["frontier"].items():
        lines.append(f"| {kind} | {r['events_nonempty']} | {r['candidate_exposures']} | {r['aggregate_cold_node_fraction']:.4f} | {r['aggregate_cold_token_fraction']:.4f} | {r['event_cold_node_fraction_p50']:.4f} / {r['event_cold_node_fraction_p90']:.4f} |")
    lines += ["", f"Victim cold fraction: nodes={s.get('victim_cold_node_fraction')}, tokens={s.get('victim_cold_token_fraction')}", ""]
    for horizon, block in result["predictors"].items():
        lines += [f"## Predict reuse within {horizon} future cache-access events — cold frontier only", "",
                  "| strategy | N | positive rate | AUC | AP | Brier | token-Brier | top10 positive recall |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        if "error" in block:
            lines += [block["error"], ""]; continue
        for name, m in sorted(block["strategies_on_cold_test"].items(), key=lambda kv: kv[1]["brier"]):
            lines.append(f"| {name} | {m['n']} | {m['positive_rate']:.4f} | {fmt(m['auc'])} | {fmt(m['ap'])} | {m['brier']:.5f} | {m['token_brier']:.5f} | {fmt(m['top10_positive_recall'])} |")
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


def main():
    p=argparse.ArgumentParser(); p.add_argument("--trace-dir",type=Path,required=True); p.add_argument("--out-dir",type=Path,required=True)
    args=p.parse_args(); args.out_dir.mkdir(parents=True,exist_ok=True)
    trace=choose_trace(args.trace_dir); frontiers,victims,demands,max_req=load_trace(trace)
    result={"trace":str(trace),"max_req_seq":max_req,"frontier_summary":frontier_summary(frontiers,victims),"predictors":{}}
    for horizon in HORIZONS:
        rows=build_rows(frontiers,demands,max_req,horizon)
        result["predictors"][str(horizon)]=compare(rows)
    (args.out_dir/"results.json").write_text(json.dumps(result,indent=2)+"\n")
    write_report(result,args.out_dir/"report.md"); print(args.out_dir/"report.md")


if __name__=="__main__": main()
