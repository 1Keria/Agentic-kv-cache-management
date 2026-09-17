#!/usr/bin/env python3
"""Expanded conditional calibration grid for interpolation validation."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from run_insection_calibration import METHODS, km_risk, load_predict, reliability, survival


def write_csv(path, rows):
    if not rows:
        return
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

    interior = []
    left = 0.0
    for right in edges:
        for fraction in (0.1, 0.25, 0.5, 0.75, 0.9):
            interior.append(left + fraction * (right - left))
        left = right

    # Ages are bucket boundaries. End times cover every later boundary and every
    # later within-bucket point, so the grid includes both long windows and the
    # locations where interpolation actually changes the prediction.
    ages = [0.0, 5.0, 20.0, 60.0, 180.0, 600.0, 1800.0]
    end_times = sorted(set(edges.tolist() + interior))
    edge_set = set(edges.tolist())
    rows = []
    reliability_rows = []

    for method in METHODS:
        survival_cache = {
            t: np.mean([survival(h, edges, t, method) for h in hazards], axis=0)
            for t in sorted(set(ages + end_times))
        }
        for age in ages:
            alive = duration > age
            dd = duration[alive] - age
            ee = event[alive]
            tw = token_weight[alive]
            sa = survival_cache[age][alive]
            for end in end_times:
                if end <= age:
                    continue
                horizon = end - age
                sb = survival_cache[end][alive]
                pred = 1.0 - np.clip(sb / sa, 0.0, 1.0)
                for weighting, weight in (("object", np.ones(len(dd))), ("token", tw)):
                    observed = float(km_risk(dd, ee, horizon, weight))
                    mean_pred = float(np.average(pred, weights=weight))
                    ece, rel = reliability(pred, dd, ee, horizon, weight, method, "long_conditional")
                    for r in rel:
                        r.update({"weighting": weighting, "age_s": age, "end_s": end, "horizon_s": horizon})
                    reliability_rows.extend(rel)
                    rows.append({
                        "method": method,
                        "weighting": weighting,
                        "age_s": age,
                        "end_s": end,
                        "horizon_s": horizon,
                        "end_is_edge": int(end in edge_set),
                        "n_at_risk": int(alive.sum()),
                        "observed_events_by_end": int(np.sum(ee & (dd <= horizon))),
                        "mean_predicted_risk": mean_pred,
                        "km_observed_risk": observed,
                        "signed_bias": mean_pred - observed,
                        "absolute_bias": abs(mean_pred - observed),
                        "relative_absolute_bias": abs(mean_pred - observed) / max(observed, 1e-6),
                        "km_ece10": ece,
                        "prevalence_normalized_ece": ece / max(observed, 1e-6),
                    })

    summaries = []
    for method in METHODS:
        for weighting in ("object", "token"):
            base = [r for r in rows if r["method"] == method and r["weighting"] == weighting]
            slices = {
                "all": base,
                "interior_only": [r for r in base if not r["end_is_edge"]],
                "observed_risk_ge_5pct": [r for r in base if r["km_observed_risk"] >= 0.05],
                "observed_risk_ge_10pct": [r for r in base if r["km_observed_risk"] >= 0.10],
                "long_horizon_ge_600s": [r for r in base if r["horizon_s"] >= 600],
            }
            for name, part in slices.items():
                if not part:
                    continue
                mean_observed = float(np.mean([r["km_observed_risk"] for r in part]))
                mean_ece = float(np.mean([r["km_ece10"] for r in part]))
                summaries.append({
                    "method": method,
                    "weighting": weighting,
                    "slice": name,
                    "n_checks": len(part),
                    "mean_observed_risk": mean_observed,
                    "mean_predicted_risk": float(np.mean([r["mean_predicted_risk"] for r in part])),
                    "mean_ece10": mean_ece,
                    "p90_ece10": float(np.quantile([r["km_ece10"] for r in part], 0.9)),
                    "aggregate_prevalence_normalized_ece": mean_ece / max(mean_observed, 1e-6),
                })

    payload = {
        "eligible_test_samples": len(duration),
        "events": int(event.sum()),
        "censored": int((~event).sum()),
        "edges_s": edges.tolist(),
        "ages_s": ages,
        "summary": summaries,
    }
    (a.out_dir / "long_window_results.json").write_text(json.dumps(payload, indent=2) + "\n")
    write_csv(a.out_dir / "long_window_conditional_calibration.csv", rows)
    write_csv(a.out_dir / "long_window_reliability_bins.csv", reliability_rows)

    lines = [
        "# Expanded long-window conditional calibration",
        "",
        "ECE10 uses Kaplan-Meier observed risk. Normalized ECE is ECE / observed risk.",
        "",
        "| weighting | method | slice | checks | observed risk | predicted risk | mean ECE10 | normalized ECE |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in summaries:
        lines.append(
            f"| {r['weighting']} | {r['method']} | {r['slice']} | {r['n_checks']} | "
            f"{r['mean_observed_risk']:.5f} | {r['mean_predicted_risk']:.5f} | "
            f"{r['mean_ece10']:.5f} | {r['aggregate_prevalence_normalized_ece']:.3f} |"
        )
    (a.out_dir / "long_window_report.md").write_text("\n".join(lines) + "\n")
    print(a.out_dir / "long_window_report.md")


if __name__ == "__main__":
    main()
