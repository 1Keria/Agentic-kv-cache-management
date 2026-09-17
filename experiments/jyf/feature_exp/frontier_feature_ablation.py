#!/usr/bin/env python3
"""Ablate server-visible features on real SGLang eviction-frontier traces."""

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


# 预测三个 request-count horizon；*_events 实际由 req_seq 差值计算，不是 wall-clock 秒。
HORIZONS = (5, 20, 100)

#TODO: some features might not be suitable; this is the original settings
# 原始 16 维 serving-side 特征；node/tree/LRU 属性来自 serving 生成的 frontier trace。
# 本脚本读取这些 candidate，不在离线阶段重建 radix tree。
ORIGINAL = [
    "node_tokens", "path_tokens", "depth", "age_events", "lru_frac",
    "parent_hits", "siblings", "warm_sibling_fraction", "owner_turn",
    "is_cold", "hits", "gap_present", "recent_gap_events",
    "is_openhands", "is_request", "is_swa",
]
EXTRAS = ["idle_events", "gap_ewma_events", "gap_std_events"]
ALL_NAMES = ORIGINAL + EXTRAS


def without(names, *removed):
    removed = set(removed)
    return [name for name in names if name not in removed]


COMPACT14 = without(ORIGINAL, "depth", "is_request")
REVISED17 = COMPACT14 + EXTRAS
CANONICAL13 = without(ORIGINAL, "depth", "is_request", "is_cold")
CANDIDATE11 = without(
    REVISED17, "is_cold", "parent_hits", "siblings", "warm_sibling_fraction",
    "owner_turn", "is_swa",
)
FEATURE_SETS = {
    "original16": ORIGINAL,
    "original_no_depth": without(ORIGINAL, "depth"),
    "original_no_gap_present": without(ORIGINAL, "gap_present"),
    "original_no_is_request": without(ORIGINAL, "is_request"),
    "original_no_is_cold": without(ORIGINAL, "is_cold"),
    "original_compact14": COMPACT14,
    "canonical13": CANONICAL13,
    "canonical_plus_idle": CANONICAL13 + ["idle_events"],
    "canonical_plus_gap_stats": CANONICAL13 + ["gap_ewma_events", "gap_std_events"],
    "revised16_drop_cold": without(REVISED17, "is_cold"),
    "revised16_drop_node_tokens": without(REVISED17, "node_tokens"),
    "revised17": REVISED17,
    "revised_minus_sizes": without(REVISED17, "node_tokens", "path_tokens"),
    "revised_minus_lru": without(REVISED17, "lru_frac"),
    "revised_minus_family": without(REVISED17, "parent_hits", "siblings", "warm_sibling_fraction"),
    "revised_minus_owner_turn": without(REVISED17, "owner_turn"),
    "revised_minus_traffic": without(REVISED17, "is_openhands"),
    "revised_minus_history": without(
        REVISED17, "age_events", "idle_events", "is_cold", "hits",
        "gap_present", "recent_gap_events", "gap_ewma_events", "gap_std_events",
    ),
    "revised_minus_swa": without(REVISED17, "is_swa"),
    "only_history": [
        "age_events", "idle_events", "is_cold", "hits", "gap_present",
        "recent_gap_events", "gap_ewma_events", "gap_std_events",
    ],
    "only_family": ["parent_hits", "siblings", "warm_sibling_fraction"],
    "only_lru": ["lru_frac"],
    "only_sizes": ["node_tokens", "path_tokens"],
    "candidate11": CANDIDATE11,
    "candidate_plus_parent_hits": CANDIDATE11 + ["parent_hits"],
    "candidate_plus_siblings": CANDIDATE11 + ["siblings"],
    "candidate_plus_warm_sibling_fraction": CANDIDATE11 + ["warm_sibling_fraction"],
    "candidate_plus_owner_turn": CANDIDATE11 + ["owner_turn"],
    "candidate_plus_swa": CANDIDATE11 + ["is_swa"],
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
    # 读取已构造的 frontier candidate，以及按 digest 保存的 demand request 序号。
    frontiers = []
    demands = defaultdict(list)
    max_req = 0
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            req = int(row.get("req_seq") or 0)
            max_req = max(max_req, req)
            if row.get("kind") == "frontier":
                frontiers.append(row)
            elif row.get("kind") == "demand":
                demands[row["digest"]].append(req)
    for values in demands.values():
        values.sort()
    return frontiers, demands, max_req


def log1p(value):
    return math.log1p(max(0.0, float(value)))


# make feature for candidates
def make_features(candidate, req, past_demands):
    # 将一个 frontier candidate 转成固定顺序特征；历史 gap 由 past_demands 补充。
    siblings = max(0, int(candidate.get("siblings", 0)))
    warm_siblings = max(0, int(candidate.get("warm_siblings", 0)))
    recent_gap = int(candidate.get("recent_gap_req", -1))
    cold = int(candidate.get("cold", 0))
    traffic = candidate.get("owner_traffic", "")

    # Cold node 没有历史 demand，gap 统计为空，idle 用 age 近似。
    if cold:
        idle = max(0, int(candidate.get("age_requests", 0)))
        idle_known = True
        gap_values = []
    else:
        idle_known = bool(past_demands)
        idle = req - past_demands[-1] if past_demands else 0
        historical_gaps = np.diff(past_demands[-9:]).astype(np.float64).tolist() if len(past_demands) >= 2 else []
        # The logged value belongs to the current node incarnation. Fall back
        # to it if trace-left truncation makes the reconstructed sequence stale.
        if recent_gap >= 0 and (not historical_gaps or int(historical_gaps[-1]) != recent_gap):
            historical_gaps = [float(recent_gap)]
        gap_values = historical_gaps[-8:]

    if gap_values:
        ewma = gap_values[0]
        for value in gap_values[1:]:
            ewma = 0.6 * value + 0.4 * ewma
        gap_std = float(np.std(gap_values))
    else:
        ewma = 0.0
        gap_std = 0.0

    values = {
        "node_tokens": log1p(candidate.get("node_tokens", 0)),
        "path_tokens": log1p(candidate.get("path_tokens", 0)),
        "depth": log1p(candidate.get("depth", 0)),
        "age_events": log1p(candidate.get("age_requests", 0)),
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
        "idle_events": log1p(idle),
        "gap_ewma_events": log1p(ewma),
        "gap_std_events": log1p(gap_std),
    }
    return [values[name] for name in ALL_NAMES], idle_known


def build_dataset(frontiers, demands, max_req):
    # 每个 frontier candidate 生成一行样本；标签是各 request-count horizon 内是否复用。
    # trace 末尾无法确认未来时，用 known mask 实现 censoring。
    x, y, known, splits, cold, tokens, digests = [], [], [], [], [], [], []
    skipped_left_truncated_warm = 0
    gap_checked = gap_matched = 0
    for event in frontiers:
        req = int(event.get("req_seq") or 0)
        for candidate in event.get("candidates") or []:
            digest = candidate["digest"]
            times = demands.get(digest, ())
            past_end = bisect.bisect_right(times, req)
            past = list(times[:past_end])
            future_req = times[past_end] if past_end < len(times) else None
            features, idle_known = make_features(candidate, req, past)
            if not idle_known:
                skipped_left_truncated_warm += 1
                continue
            recent_gap = int(candidate.get("recent_gap_req", -1))
            if recent_gap >= 0 and len(past) >= 2:
                gap_checked += 1
                gap_matched += int(past[-1] - past[-2] == recent_gap)
            labels, masks = [], []
            for horizon in HORIZONS:
                positive = future_req is not None and future_req - req <= horizon
                fully_observed = req + horizon <= max_req
                labels.append(float(positive))
                masks.append(float(positive or fully_observed))
            x.append(features)
            y.append(labels)
            known.append(masks)
            splits.append(split_digest(digest))
            cold.append(int(candidate.get("cold", 0)))
            tokens.append(max(1, int(candidate.get("kv_tokens", 0))))
            digests.append(digest)
    return {
        "x": np.asarray(x, np.float32),
        "y": np.asarray(y, np.float32),
        "known": np.asarray(known, np.float32),
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
        },
    }


class HorizonNet(nn.Module):
    def __init__(self, n_in):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 64), nn.ReLU(),
            nn.Linear(64, 64), nn.ReLU(),
            nn.Linear(64, len(HORIZONS)),
        )

    def forward(self, x):
        # Outputs interval hazards; cumulative probabilities are monotone.
        hazards = torch.sigmoid(self.net(x))
        return 1.0 - torch.cumprod(1.0 - hazards, dim=1)


def masked_bce(probability, labels, mask):
    probability = probability.clamp(1e-6, 1 - 1e-6)
    loss = -(labels * torch.log(probability) + (1 - labels) * torch.log(1 - probability))
    return (loss * mask).sum() / mask.sum().clamp_min(1)


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


def metric_block(y, probability, mask, tokens, subset):
    result = {}
    for index, horizon in enumerate(HORIZONS):
        selected = subset & (mask[:, index] > 0.5)
        yy = y[selected, index]
        pp = np.clip(probability[selected, index], 1e-6, 1 - 1e-6)
        weight = tokens[selected]
        brier = (pp - yy) ** 2
        nll = -(yy * np.log(pp) + (1 - yy) * np.log(1 - pp))
        result[str(horizon)] = {
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
    # 训练指定特征子集的 MLP；被消融的列置零，保持固定 16 列输入宽度。
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
    train_y = torch.from_numpy(data["y"][train]).to(device)
    train_m = torch.from_numpy(data["known"][train]).to(device)
    val_x = torch.from_numpy(z[val]).to(device)
    val_y = torch.from_numpy(data["y"][val]).to(device)
    val_m = torch.from_numpy(data["known"][val]).to(device)
    # Every ablation uses the same input width. For a fixed seed, all weights
    # start identically; excluded features are represented by zero columns.
    model = HorizonNet(len(ALL_NAMES)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    generator = torch.Generator(device=device).manual_seed(seed)
    best_loss, best_state, stale = float("inf"), None, 0
    for epoch in range(args.epochs):
        model.train()
        permutation = torch.randperm(len(train_x), generator=generator, device=device)
        for start in range(0, len(train_x), args.batch_size):
            index = permutation[start : start + args.batch_size]
            loss = masked_bce(model(train_x[index]), train_y[index], train_m[index])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            validation = float(masked_bce(model(val_x), val_y, val_m).cpu())
        if validation < best_loss - 1e-5:
            best_loss = validation
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= args.patience:
            break
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        probability = model(torch.from_numpy(z).to(device)).cpu().numpy()
    blocks = {}
    for subset_name, subset in {
        "all": test,
        "cold": test & (data["cold"] == 1),
        "warm": test & (data["cold"] == 0),
    }.items():
        blocks[subset_name] = metric_block(data["y"], probability, data["known"], data["tokens"], subset)
    return {"seed": seed, "epochs": epoch + 1, "best_val_nll": best_loss, "metrics": blocks}, probability


def summarize(runs):
    summary = {}
    for feature_set, feature_runs in runs.items():
        summary[feature_set] = {}
        for subset in ("all", "cold", "warm"):
            summary[feature_set][subset] = {}
            for horizon in map(str, HORIZONS):
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
        "# Real-frontier feature ablation",
        "",
        f"Each learned row uses the same fixed-width two-layer 64-hidden-unit MLP and a {seed_count}-seed probability ensemble. Prefix digests are split 70/15/15.",
        "",
        f"Rows: {data['meta']['rows']}; unique digests: {data['meta']['unique_digests']}; "
        f"left-truncated warm rows excluded: {data['meta']['skipped_left_truncated_warm']}.",
        "",
    ]
    for subset in ("all", "cold", "warm"):
        lines += [
            f"## {subset}", "",
            "| features | NLL@5 ↓ | AUC@5 ↑ | NLL@20 ↓ | AUC@20 ↑ | NLL@100 ↓ | AUC@100 ↑ |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for feature_set in FEATURE_SETS:
            block = ensemble_metrics[feature_set][subset]
            lines.append(
                f"| {feature_set} | {block['5']['nll']:.5f} | {block['5']['auc']:.4f} | "
                f"{block['20']['nll']:.5f} | {block['20']['auc']:.4f} | "
                f"{block['100']['nll']:.5f} | {block['100']['auc']:.4f} |"
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
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    trace = choose_trace(args.trace_dir)
    frontiers, demands, max_req = load_trace(trace)
    data = build_dataset(frontiers, demands, max_req)
    print(json.dumps(data["meta"], indent=2), flush=True)
    runs = {}
    ensemble_metrics = {}
    # 对完整集、删特征集和子集逐一训练，并汇总 ensemble test 指标。
    for feature_set, names in FEATURE_SETS.items():
        runs[feature_set] = []
        probabilities = []
        for seed in args.seeds:
            print(f"[train] {feature_set} seed={seed}", flush=True)
            run, probability = fit_one(data, names, seed, args)
            runs[feature_set].append(run)
            probabilities.append(probability)
            print(f"  val={run['best_val_nll']:.6f} epochs={run['epochs']}", flush=True)
        ensemble_probability = np.mean(probabilities, axis=0)
        test = data["split"] == 2
        ensemble_metrics[feature_set] = {}
        for subset_name, subset in {
            "all": test,
            "cold": test & (data["cold"] == 1),
            "warm": test & (data["cold"] == 0),
        }.items():
            ensemble_metrics[feature_set][subset_name] = metric_block(
                data["y"], ensemble_probability, data["known"], data["tokens"], subset
            )
    summary = summarize(runs)
    payload = {
        "trace": str(trace), "meta": data["meta"], "all_feature_names": ALL_NAMES,
        "feature_sets": FEATURE_SETS, "runs": runs, "summary": summary,
        "ensemble_metrics": ensemble_metrics,
    }
    (args.output_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
    write_report(args.output_dir / "report.md", data, summary, ensemble_metrics, len(args.seeds))
    print(args.output_dir / "report.md")


if __name__ == "__main__":
    main()
