#!/usr/bin/env python3
"""Compare per-node predicted next-request time with observed exact time."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from run_insection_calibration import METHODS, load_predict, survival


def rankdata(values):
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=float)
    starts = np.r_[0, np.flatnonzero(np.diff(sorted_values)) + 1]
    ends = np.r_[starts[1:], len(values)]
    for start, end in zip(starts, ends):
        ranks[order[start:end]] = 0.5 * (start + end - 1)
    return ranks


def weighted_mean(values, weight):
    return float(np.average(values, weights=weight))


def predicted_times(hazards, edges, method, grid):
    s = np.stack([
        np.mean([survival(h, edges, float(t), method) for h in hazards], axis=0)
        for t in grid
    ], axis=1)
    final_survival = s[:, -1]
    event_probability = np.clip(1.0 - final_survival, 1e-9, 1.0)
    conditional_cdf = (1.0 - s) / event_probability[:, None]

    # Conditional median among requests predicted to return by the final edge.
    crossing = conditional_cdf >= 0.5
    right_idx = np.argmax(crossing, axis=1)
    right_idx = np.maximum(right_idx, 1)
    left_idx = right_idx - 1
    row = np.arange(len(s))
    f0 = conditional_cdf[row, left_idx]
    f1 = conditional_cdf[row, right_idx]
    alpha = np.clip((0.5 - f0) / np.maximum(f1 - f0, 1e-12), 0.0, 1.0)
    median = grid[left_idx] + alpha * (grid[right_idx] - grid[left_idx])

    # E[T | T <= H] from integral identity, using a dense within-bucket grid.
    restricted_integral = np.trapz(s, grid, axis=1)
    mean = (restricted_integral - grid[-1] * final_survival) / event_probability
    return np.clip(median, 0.0, grid[-1]), np.clip(mean, 0.0, grid[-1]), event_probability


def metrics(true_time, predicted, weight):
    abs_error = np.abs(predicted - true_time)
    log_error = np.abs(np.log1p(predicted) - np.log1p(true_time))
    ratio = np.maximum((predicted + 1.0) / (true_time + 1.0),
                       (true_time + 1.0) / (predicted + 1.0))
    spearman = float(np.corrcoef(rankdata(true_time), rankdata(predicted))[0, 1])
    return {
        "mae_s": weighted_mean(abs_error, weight),
        "median_absolute_error_s": float(np.median(abs_error)),
        "mean_absolute_log1p_error": weighted_mean(log_error, weight),
        "within_2x_fraction": weighted_mean((ratio <= 2.0).astype(float), weight),
        "within_4x_fraction": weighted_mean((ratio <= 4.0).astype(float), weight),
        "spearman_rank_correlation": spearman,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--checkpoint-root", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()

    z = np.load(a.data, allow_pickle=False)
    base = (z["split"] == 2) & (z["history"] >= 1) & (z["duration"] > 1e-6)
    x_all = z["x"][base]
    duration_all = z["duration"][base].astype(float)
    event_all = z["event"][base].astype(bool)
    weight_all = np.maximum(z["weight"][base].astype(float), 1.0)

    all_hazards = []
    edges = None
    for seed in (41, 42, 43):
        h, edges = load_predict(a.checkpoint_root / f"seed_{seed}" / "initial.pt", x_all)
        all_hazards.append(h)

    exact = event_all & (duration_all <= edges[-1])
    true_time = duration_all[exact]
    token_weight = weight_all[exact]
    hazards = [h[exact] for h in all_hazards]

    # 64 subintervals per model bucket, preserving all original boundaries.
    pieces = []
    left = 0.0
    for right in edges:
        pieces.append(np.linspace(left, right, 65)[1:])
        left = right
    grid = np.r_[0.0, np.concatenate(pieces)]

    rows = []
    per_node = [{"sample_index": int(i), "true_next_request_s": float(t),
                 "token_weight": float(w)} for i, (t, w) in enumerate(zip(true_time, token_weight))]
    for method in METHODS:
        median, mean, event_probability = predicted_times(hazards, edges, method, grid)
        for weighting, weight in (("object", np.ones(len(true_time))), ("token", token_weight)):
            for estimator, predicted in (("conditional_median", median), ("conditional_mean", mean)):
                row = {"method": method, "weighting": weighting, "estimator": estimator}
                row.update(metrics(true_time, predicted, weight))
                rows.append(row)
        for i in range(len(per_node)):
            prefix = {"log_survival": "log", "linear_survival": "linear", "right_step": "step"}[method]
            per_node[i][f"{prefix}_conditional_median_s"] = float(median[i])
            per_node[i][f"{prefix}_conditional_mean_s"] = float(mean[i])
            per_node[i][f"{prefix}_return_probability_by_7200s"] = float(event_probability[i])

    # Discrete bucket prediction, common to the interpolation methods.
    masses = []
    for h in all_hazards:
        survival_before = np.cumprod(np.c_[np.ones(len(h)), 1.0 - h[:, :-1]], axis=1)
        masses.append(survival_before * h)
    mean_mass = np.mean(masses, axis=0)[exact]
    predicted_bucket = np.argmax(mean_mass, axis=1)
    true_bucket = np.searchsorted(edges, true_time, side="left")
    bucket_rows = []
    for weighting, weight in (("object", np.ones(len(true_time))), ("token", token_weight)):
        bucket_rows.append({
            "weighting": weighting,
            "top1_bucket_accuracy": weighted_mean((predicted_bucket == true_bucket).astype(float), weight),
            "within_one_bucket_accuracy": weighted_mean((np.abs(predicted_bucket - true_bucket) <= 1).astype(float), weight),
        })

    def write_csv(path, data):
        fields = list(data[0])
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)

    write_csv(a.out_dir / "next_request_time_metrics.csv", rows)
    write_csv(a.out_dir / "next_request_time_predictions.csv", per_node)
    write_csv(a.out_dir / "next_request_bucket_metrics.csv", bucket_rows)
    payload = {
        "exact_observed_reuses_within_7200s": int(exact.sum()),
        "excluded_censored": int((~event_all).sum()),
        "excluded_observed_after_7200s": int((event_all & (duration_all > edges[-1])).sum()),
        "metrics": rows,
        "bucket_metrics": bucket_rows,
    }
    (a.out_dir / "next_request_time_results.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(a.out_dir / "next_request_time_metrics.csv")


if __name__ == "__main__":
    main()
