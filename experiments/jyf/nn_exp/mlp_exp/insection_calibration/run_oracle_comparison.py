#!/usr/bin/env python3
"""Compare predictor victims with random and perfect future-window oracle."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from run_insection_calibration import METHODS, load_predict, survival
from run_node_level_validation import AGES, HORIZONS, token_fraction_set


FRACTIONS = (0.1, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95)


def event_token_rate(chosen, label, weight):
    return float(weight[chosen & label].sum() / max(weight[chosen].sum(), 1e-12))


def write_csv(path, rows):
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


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
    rows = []
    for method in METHODS:
        s_cache = {t: np.mean([survival(h, edges, t, method) for h in hazards], axis=0)
                   for t in times}
        for age, horizon in pairs:
            alive = duration > age
            dd = duration[alive] - age
            ee = event[alive]
            tw = token_weight[alive]
            pred = 1.0 - np.clip(s_cache[age + horizon][alive] / s_cache[age][alive], 0.0, 1.0)
            # Exact binary outcome is known for observed events and for samples
            # followed at least through the horizon. Earlier censoring is omitted.
            known = ee | (dd >= horizon)
            pred = pred[known]
            tw = tw[known]
            label = (ee & (dd <= horizon))[known]
            random_rate = float(tw[label].sum() / tw.sum())
            # Oracle score is the true event indicator: negatives are evicted first.
            oracle_score = label.astype(float)
            for fraction in FRACTIONS:
                model_victim = token_fraction_set(pred, tw, fraction, highest=False)
                oracle_victim = token_fraction_set(oracle_score, tw, fraction, highest=False)
                model_rate = event_token_rate(model_victim, label, tw)
                oracle_rate = event_token_rate(oracle_victim, label, tw)
                denom = random_rate - oracle_rate
                regret = (model_rate - oracle_rate) / denom if denom > 1e-12 else float("nan")
                rows.append({
                    "method": method,
                    "age_s": age,
                    "horizon_s": horizon,
                    "evict_token_fraction": fraction,
                    "known_nodes": int(known.sum()),
                    "known_positive_nodes": int(label.sum()),
                    "random_event_token_rate": random_rate,
                    "model_event_token_rate": model_rate,
                    "oracle_event_token_rate": oracle_rate,
                    "normalized_regret": regret,
                    "fraction_random_to_oracle_gap_closed": 1.0 - regret if np.isfinite(regret) else float("nan"),
                })

    summary = []
    for method in METHODS:
        for horizon in HORIZONS:
            for fraction in FRACTIONS:
                part = [r for r in rows if r["method"] == method and r["horizon_s"] == horizon
                        and r["evict_token_fraction"] == fraction]
                if not part:
                    continue
                mean_random = float(np.mean([r["random_event_token_rate"] for r in part]))
                mean_model = float(np.mean([r["model_event_token_rate"] for r in part]))
                mean_oracle = float(np.mean([r["oracle_event_token_rate"] for r in part]))
                aggregate_denom = mean_random - mean_oracle
                summary.append({
                    "method": method,
                    "horizon_s": horizon,
                    "evict_token_fraction": fraction,
                    "n_ages": len(part),
                    "mean_random_event_token_rate": mean_random,
                    "mean_model_event_token_rate": mean_model,
                    "mean_oracle_event_token_rate": mean_oracle,
                    "aggregate_gap_closed": (mean_random - mean_model) / aggregate_denom if aggregate_denom > 1e-12 else float("nan"),
                    "mean_normalized_regret": float(np.nanmean([r["normalized_regret"] for r in part])),
                    "mean_gap_closed": float(np.nanmean([r["fraction_random_to_oracle_gap_closed"] for r in part])),
                })

    write_csv(a.out_dir / "oracle_comparison.csv", rows)
    write_csv(a.out_dir / "oracle_summary.csv", summary)
    (a.out_dir / "oracle_results.json").write_text(json.dumps({
        "oracle_definition": "perfect knowledge of reuse within the horizon; censored-before-horizon omitted",
        "summary": summary,
    }, indent=2) + "\n")
    print(a.out_dir / "oracle_summary.csv")


if __name__ == "__main__":
    main()
