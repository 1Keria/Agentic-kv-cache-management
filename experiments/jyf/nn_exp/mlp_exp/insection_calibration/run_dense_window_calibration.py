#!/usr/bin/env python3
"""Dense age x horizon calibration matrix and compact horizon summary."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from run_insection_calibration import METHODS, km_risk, load_predict, reliability, survival


AGES = (0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120, 180,
        300, 600, 900, 1200, 1800, 2400, 3600)
HORIZONS = (1, 2, 3, 5, 10, 20, 30, 60, 120, 180, 300, 600, 900,
            1200, 1800, 2400, 3600)


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
    a.out_dir.mkdir(parents=True, exist_ok=True)

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

    valid_pairs = [(float(age), float(horizon)) for age in AGES for horizon in HORIZONS
                   if age + horizon <= float(edges[-1])]
    times = sorted(set([v for pair in valid_pairs for v in (pair[0], pair[0] + pair[1])]))
    rows = []

    for method in METHODS:
        s_cache = {t: np.mean([survival(h, edges, t, method) for h in hazards], axis=0)
                   for t in times}
        for age, horizon in valid_pairs:
            alive = duration > age
            dd = duration[alive] - age
            ee = event[alive]
            tw = token_weight[alive]
            pred = 1.0 - np.clip(s_cache[age + horizon][alive] / s_cache[age][alive], 0.0, 1.0)
            for weighting, weight in (("object", np.ones(len(dd))), ("token", tw)):
                observed = float(km_risk(dd, ee, horizon, weight))
                mean_pred = float(np.average(pred, weights=weight))
                ece, _ = reliability(pred, dd, ee, horizon, weight, method, "dense_conditional")
                rows.append({
                    "method": method,
                    "weighting": weighting,
                    "age_s": age,
                    "horizon_s": horizon,
                    "end_s": age + horizon,
                    "n_at_risk": int(alive.sum()),
                    "observed_events": int(np.sum(ee & (dd <= horizon))),
                    "mean_predicted_risk": mean_pred,
                    "km_observed_risk": observed,
                    "signed_bias": mean_pred - observed,
                    "km_ece10": ece,
                })

    # Macro-average over all valid ages for each fixed future window.
    summary = []
    for weighting in ("object", "token"):
        for horizon in HORIZONS:
            observed_rows = [r for r in rows if r["weighting"] == weighting
                             and r["method"] == "log_survival" and r["horizon_s"] == horizon]
            if not observed_rows:
                continue
            record = {
                "weighting": weighting,
                "horizon_s": horizon,
                "n_ages": len(observed_rows),
                "mean_km_observed_risk": float(np.mean([r["km_observed_risk"] for r in observed_rows])),
            }
            for method in METHODS:
                part = [r for r in rows if r["weighting"] == weighting
                        and r["method"] == method and r["horizon_s"] == horizon]
                prefix = {"log_survival": "log", "linear_survival": "linear", "right_step": "step"}[method]
                record[f"{prefix}_mean_predicted_risk"] = float(np.mean([r["mean_predicted_risk"] for r in part]))
                record[f"{prefix}_mean_ece10"] = float(np.mean([r["km_ece10"] for r in part]))
                record[f"{prefix}_mean_signed_bias"] = float(np.mean([r["signed_bias"] for r in part]))
            summary.append(record)

    write_csv(a.out_dir / "dense_window_calibration.csv", rows)
    write_csv(a.out_dir / "dense_window_summary.csv", summary)
    (a.out_dir / "dense_window_results.json").write_text(json.dumps({
        "ages_s": AGES,
        "horizons_s": HORIZONS,
        "valid_age_horizon_pairs": len(valid_pairs),
        "eligible_test_samples": len(duration),
        "events": int(event.sum()),
        "censored": int((~event).sum()),
        "summary": summary,
    }, indent=2) + "\n")

    token_summary = [r for r in summary if r["weighting"] == "token"]
    lines = [
        "# Dense window calibration summary",
        "",
        f"Tested {len(valid_pairs)} valid age × horizon pairs. Values are macro-averaged over ages.",
        "",
        "| horizon | ages | KM actual | log pred | log ECE | linear pred | linear ECE | step pred | step ECE |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in token_summary:
        lines.append(
            f"| {r['horizon_s']:g}s | {r['n_ages']} | {r['mean_km_observed_risk']:.4f} | "
            f"{r['log_mean_predicted_risk']:.4f} | {r['log_mean_ece10']:.4f} | "
            f"{r['linear_mean_predicted_risk']:.4f} | {r['linear_mean_ece10']:.4f} | "
            f"{r['step_mean_predicted_risk']:.4f} | {r['step_mean_ece10']:.4f} |"
        )
    (a.out_dir / "dense_window_report.md").write_text("\n".join(lines) + "\n")
    print(a.out_dir / "dense_window_report.md")


if __name__ == "__main__":
    main()
