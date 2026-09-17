#!/usr/bin/env python3
"""Node-level ranking and eviction-victim validation for interpolation methods."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from run_insection_calibration import METHODS, km_risk, load_predict, survival


AGES = (0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120, 180,
        300, 600, 900, 1200, 1800, 2400, 3600)
HORIZONS = (1, 2, 3, 5, 10, 20, 30, 60, 120, 180, 300, 600, 900,
            1200, 1800, 2400, 3600)


def weighted_auc_ap(y, score, weight):
    """Weighted AUROC and average precision, grouping tied scores."""
    y = np.asarray(y, dtype=bool)
    score = np.asarray(score, dtype=float)
    weight = np.asarray(weight, dtype=float)
    positive_total = float(weight[y].sum())
    negative_total = float(weight[~y].sum())
    if positive_total <= 0 or negative_total <= 0:
        return float("nan"), float("nan")

    order = np.argsort(score, kind="mergesort")
    sorted_score = score[order]
    sorted_y = y[order]
    sorted_weight = weight[order]
    auc_numerator = 0.0
    negative_before = 0.0
    for group in np.split(np.arange(len(order)), np.flatnonzero(np.diff(sorted_score)) + 1):
        positive_group = float(sorted_weight[group][sorted_y[group]].sum())
        negative_group = float(sorted_weight[group][~sorted_y[group]].sum())
        auc_numerator += positive_group * (negative_before + 0.5 * negative_group)
        negative_before += negative_group
    auc = auc_numerator / (positive_total * negative_total)

    order = order[::-1]
    sorted_score = score[order]
    sorted_y = y[order]
    sorted_weight = weight[order]
    true_positive = 0.0
    total_seen = 0.0
    ap_numerator = 0.0
    for group in np.split(np.arange(len(order)), np.flatnonzero(np.diff(sorted_score)) + 1):
        positive_group = float(sorted_weight[group][sorted_y[group]].sum())
        group_weight = float(sorted_weight[group].sum())
        true_positive += positive_group
        total_seen += group_weight
        ap_numerator += positive_group * (true_positive / total_seen)
    return auc, ap_numerator / positive_total


def token_fraction_set(score, weight, fraction, highest):
    order = np.argsort(score)
    if highest:
        order = order[::-1]
    cutoff = fraction * float(weight.sum())
    count = max(1, int(np.searchsorted(np.cumsum(weight[order]), cutoff, side="left") + 1))
    chosen = np.zeros(len(score), dtype=bool)
    chosen[order[:count]] = True
    return chosen


def write_csv(path, rows):
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--checkpoint-root", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()

    z = np.load(a.data, allow_pickle=False)
    use = (z["split"] == 2) & (z["history"] >= 1) & (z["duration"] > 1e-6)
    x = z["x"][use]
    duration = z["duration"][use].astype(float)
    event = z["event"][use].astype(bool)
    token_weight = np.maximum(z["weight"][use].astype(float), 1.0)

    hazards = []
    edges = None
    for seed in (41, 42, 43):
        h, edges = load_predict(a.checkpoint_root / f"seed_{seed}" / "initial.pt", x)
        hazards.append(h)

    pairs = [(float(age), float(horizon)) for age in AGES for horizon in HORIZONS
             if age + horizon <= float(edges[-1])]
    times = sorted(set(v for age, horizon in pairs for v in (age, age + horizon)))
    predictions = {}
    for method in METHODS:
        s_cache = {t: np.mean([survival(h, edges, t, method) for h in hazards], axis=0)
                   for t in times}
        for age, horizon in pairs:
            alive = duration > age
            predictions[(method, age, horizon)] = 1.0 - np.clip(
                s_cache[age + horizon][alive] / s_cache[age][alive], 0.0, 1.0)

    rows = []
    selected = {}
    for method in METHODS:
        for age, horizon in pairs:
            alive = duration > age
            dd = duration[alive] - age
            ee = event[alive]
            tw = token_weight[alive]
            pred = predictions[(method, age, horizon)]
            # Censored before the horizon has unknown binary outcome and is
            # excluded only from AUROC/AP. KM victim risks retain censoring.
            known = ee | (dd >= horizon)
            y = ee & (dd <= horizon)
            if y[known].any() and (~y[known]).any():
                auc, ap = weighted_auc_ap(y[known], pred[known], tw[known])
            else:
                auc = ap = float("nan")
            low = token_fraction_set(pred, tw, 0.20, highest=False)
            high = token_fraction_set(pred, tw, 0.20, highest=True)
            selected[(method, age, horizon, "low")] = low
            selected[(method, age, horizon, "high")] = high
            population_risk = float(km_risk(dd, ee, horizon, tw))
            low_risk = float(km_risk(dd[low], ee[low], horizon, tw[low]))
            high_risk = float(km_risk(dd[high], ee[high], horizon, tw[high]))
            rows.append({
                "method": method,
                "age_s": age,
                "horizon_s": horizon,
                "n_at_risk": int(alive.sum()),
                "known_binary_outcomes": int(known.sum()),
                "positive_binary_outcomes": int(y[known].sum()),
                "token_weighted_auroc": auc,
                "token_weighted_average_precision": ap,
                "population_km_risk": population_risk,
                "top20pct_token_km_risk": high_risk,
                "bottom20pct_token_victim_km_risk": low_risk,
                "victim_to_population_risk_ratio": low_risk / max(population_risk, 1e-9),
            })

    overlaps = []
    for age, horizon in pairs:
        alive = duration > age
        tw = token_weight[alive]
        for side in ("low", "high"):
            for left, right in (("log_survival", "linear_survival"),
                                ("log_survival", "right_step")):
                aa = selected[(left, age, horizon, side)]
                bb = selected[(right, age, horizon, side)]
                inter = float(tw[aa & bb].sum())
                union = float(tw[aa | bb].sum())
                overlaps.append({
                    "age_s": age,
                    "horizon_s": horizon,
                    "side": side,
                    "left_method": left,
                    "right_method": right,
                    "token_weighted_jaccard": inter / max(union, 1e-9),
                })

    summary = []
    for method in METHODS:
        for horizon in HORIZONS:
            part = [r for r in rows if r["method"] == method and r["horizon_s"] == horizon]
            if not part:
                continue
            summary.append({
                "method": method,
                "horizon_s": horizon,
                "n_ages": len(part),
                "mean_token_weighted_auroc": float(np.nanmean([r["token_weighted_auroc"] for r in part])),
                "mean_token_weighted_average_precision": float(np.nanmean([r["token_weighted_average_precision"] for r in part])),
                "mean_population_km_risk": float(np.mean([r["population_km_risk"] for r in part])),
                "mean_top20pct_token_km_risk": float(np.mean([r["top20pct_token_km_risk"] for r in part])),
                "mean_bottom20pct_token_victim_km_risk": float(np.mean([r["bottom20pct_token_victim_km_risk"] for r in part])),
                "mean_victim_to_population_risk_ratio": float(np.mean([r["victim_to_population_risk_ratio"] for r in part])),
            })

    overlap_summary = []
    for horizon in HORIZONS:
        for side in ("low", "high"):
            for right in ("linear_survival", "right_step"):
                part = [r for r in overlaps if r["horizon_s"] == horizon and r["side"] == side
                        and r["right_method"] == right]
                overlap_summary.append({
                    "horizon_s": horizon,
                    "side": side,
                    "comparison": f"log_vs_{right}",
                    "mean_token_weighted_jaccard": float(np.mean([r["token_weighted_jaccard"] for r in part])),
                    "min_token_weighted_jaccard": float(np.min([r["token_weighted_jaccard"] for r in part])),
                })

    write_csv(a.out_dir / "node_level_metrics.csv", rows)
    write_csv(a.out_dir / "node_level_summary.csv", summary)
    write_csv(a.out_dir / "node_selection_overlap.csv", overlaps)
    write_csv(a.out_dir / "node_selection_overlap_summary.csv", overlap_summary)
    (a.out_dir / "node_level_results.json").write_text(json.dumps({
        "pairs": len(pairs), "summary": summary, "overlap_summary": overlap_summary,
    }, indent=2) + "\n")
    print(a.out_dir / "node_level_summary.csv")


if __name__ == "__main__":
    main()
