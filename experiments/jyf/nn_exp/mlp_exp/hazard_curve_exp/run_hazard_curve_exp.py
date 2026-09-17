#!/usr/bin/env python3
"""Validate within-bucket survival interpolation on held-out prefix reuse gaps."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


METHODS = ("log_survival", "linear_survival", "right_step")


class HazardMLP(nn.Module):
    def __init__(self, n_in: int, n_out: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 128), nn.ReLU(),
            nn.Linear(128, 128), nn.ReLU(),
            nn.Linear(128, n_out),
        )

    def forward(self, x):
        return self.net(x)


def load_checkpoint(path: Path, device: torch.device):
    blob = torch.load(path, map_location="cpu", weights_only=False)
    model = HazardMLP(int(blob["n_in"]), int(blob["n_out"]))
    model.load_state_dict(blob["state_dict"])
    model.to(device).eval()
    return model, blob


@torch.no_grad()
def predict(model, x: np.ndarray, device: torch.device) -> np.ndarray:
    output = []
    for start in range(0, len(x), 16384):
        xb = torch.from_numpy(x[start:start + 16384]).to(device)
        output.append(torch.sigmoid(model(xb)).cpu().numpy())
    return np.concatenate(output)


def survival_at(h: np.ndarray, edges: np.ndarray, time_s: float, method: str) -> np.ndarray:
    """Survival at one scalar time under a specified within-bin interpolation."""
    s = np.ones(len(h), dtype=np.float64)
    left = 0.0
    for j, right in enumerate(edges):
        q = np.clip(1.0 - h[:, j].astype(np.float64), 1e-9, 1.0)
        if time_s >= right:
            s *= q
        elif time_s > left:
            u = (time_s - left) / (right - left)
            if method == "log_survival":
                s *= np.power(q, u)
            elif method == "linear_survival":
                s *= 1.0 - u * h[:, j]
            elif method == "right_step":
                pass
            else:
                raise ValueError(method)
            break
        else:
            break
        left = right
    return np.clip(s, 1e-12, 1.0)


def scores(p: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict:
    p = np.clip(p.astype(np.float64), 1e-9, 1.0 - 1e-9)
    y = y.astype(np.float64)
    w = w.astype(np.float64)
    err = (p - y) ** 2
    nll = -(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))
    order = np.argsort(p)
    groups = np.array_split(order, 10)
    ece_num = 0.0
    for group in groups:
        if len(group) == 0:
            continue
        wg = w[group]
        ece_num += wg.sum() * abs(np.average(p[group], weights=wg) - np.average(y[group], weights=wg))
    return {
        "n": int(len(p)),
        "positive_rate": float(y.mean()),
        "token_positive_rate": float(np.average(y, weights=w)),
        "brier": float(err.mean()),
        "token_brier": float(np.average(err, weights=w)),
        "bernoulli_nll": float(nll.mean()),
        "token_bernoulli_nll": float(np.average(nll, weights=w)),
        "token_ece10": float(ece_num / w.sum()),
        "mean_probability": float(p.mean()),
        "token_mean_probability": float(np.average(p, weights=w)),
    }


def km_survival(durations: np.ndarray, events: np.ndarray, weights: np.ndarray,
                query_times: list[float]) -> dict[float, float]:
    """Weighted Kaplan-Meier survival at query times; events precede censors at ties."""
    order = np.argsort(durations, kind="stable")
    d = durations[order].astype(np.float64)
    e = events[order].astype(bool)
    w = weights[order].astype(np.float64)
    unique, starts = np.unique(d, return_index=True)
    ends = np.r_[starts[1:], len(d)]
    risk = float(w.sum())
    survival = 1.0
    timeline_t, timeline_s = [], []
    for t, lo, hi in zip(unique, starts, ends):
        event_weight = float(w[lo:hi][e[lo:hi]].sum())
        if risk > 0 and event_weight > 0:
            survival *= max(0.0, 1.0 - event_weight / risk)
        timeline_t.append(float(t))
        timeline_s.append(survival)
        risk -= float(w[lo:hi].sum())
    timeline_t = np.asarray(timeline_t)
    timeline_s = np.asarray(timeline_s)
    result = {}
    for q in query_times:
        idx = np.searchsorted(timeline_t, q, side="right") - 1
        result[float(q)] = 1.0 if idx < 0 else float(timeline_s[idx])
    return result


def empirical_interpolation_test(duration, event, weights, edges, weighted: bool) -> list[dict]:
    points = sorted(set([0.0] + list(edges) + [
        left + u * (right - left)
        for left, right in zip([0.0] + list(edges[:-1]), edges)
        for u in (0.25, 0.5, 0.75)
    ]))
    km_w = weights if weighted else np.ones_like(weights)
    km = km_survival(duration, event, km_w, points)
    rows = []
    left = 0.0
    for bucket, right in enumerate(edges):
        s_left, s_right = km[left], km[float(right)]
        if s_left <= 1e-12:
            left = float(right)
            continue
        endpoint_ratio = np.clip(s_right / s_left, 1e-12, 1.0)
        endpoint_hazard = 1.0 - endpoint_ratio
        at_risk = int((duration >= left).sum())
        interval_events = int((event & (duration >= left) & (duration < right)).sum())
        for u in (0.25, 0.5, 0.75):
            t = left + u * (right - left)
            empirical_ratio = np.clip(km[float(t)] / s_left, 0.0, 1.0)
            predictions = {
                "log_survival": endpoint_ratio ** u,
                "linear_survival": 1.0 - u * endpoint_hazard,
                "right_step": 1.0,
            }
            for method, predicted_ratio in predictions.items():
                rows.append({
                    "weighted_km": weighted,
                    "bucket": bucket,
                    "left_s": left,
                    "right_s": float(right),
                    "u": u,
                    "time_s": t,
                    "at_risk_at_left": at_risk,
                    "interval_events": interval_events,
                    "endpoint_hazard": endpoint_hazard,
                    "method": method,
                    "empirical_conditional_survival": empirical_ratio,
                    "predicted_conditional_survival": float(predicted_ratio),
                    "absolute_error": abs(float(predicted_ratio) - empirical_ratio),
                })
        left = float(right)
    return rows


def model_tests(data: dict, checkpoint_root: Path, device: torch.device):
    duration = data["duration"].astype(np.float64)
    event = data["event"].astype(bool)
    split = data["split"]
    history = data["history"]
    token_weight = np.maximum(data["weight"].astype(np.float64), 1.0)
    test_idx = np.where((split == 2) & (history >= 1) & (duration > 1e-6))[0]
    absolute_rows, shift_rows = [], []
    for bucket_dir in sorted(checkpoint_root.glob("k*"), key=lambda p: int(p.name[1:])):
        for seed_dir in sorted(bucket_dir.glob("seed_*")):
            model, blob = load_checkpoint(seed_dir / "initial.pt", device)
            edges = np.asarray(blob["edges"], dtype=np.float64)
            mean = np.asarray(blob["x_mean"], dtype=np.float32)
            std = np.asarray(blob["x_std"], dtype=np.float32)
            x = ((data["x"][test_idx].astype(np.float32) - mean) / std).astype(np.float32)
            hazards = predict(model, x, device)
            td, te, tw = duration[test_idx], event[test_idx], token_weight[test_idx]
            left = 0.0
            interior_points = []
            for right in edges:
                for u in (0.25, 0.5, 0.75):
                    interior_points.append((left + u * (right - left), left, float(right), u))
                left = float(right)
            for t, bucket_left, bucket_right, u in interior_points:
                known = te | (td >= t)
                y = te[known] & (td[known] <= t)
                for method in METHODS:
                    p = 1.0 - survival_at(hazards[known], edges, t, method)
                    row = scores(p, y, tw[known])
                    row.update({"bucket_config": bucket_dir.name, "seed": seed_dir.name,
                                "method": method, "time_s": t, "bucket_left_s": bucket_left,
                                "bucket_right_s": bucket_right, "u": u})
                    absolute_rows.append(row)

            pairs = [(5, 5), (5, 20), (5, 60), (20, 5), (20, 20), (20, 60),
                     (600, 600), (600, 1800), (600, 3600),
                     (1800, 600), (1800, 1800), (1800, 3600)]
            for age, horizon in pairs:
                if age + horizon > edges[-1]:
                    continue
                survived = td > age + 1e-6
                known = survived & (te | (td >= age + horizon))
                y = te[known] & (td[known] <= age + horizon)
                for method in METHODS:
                    s_age = survival_at(hazards[known], edges, age, method)
                    s_end = survival_at(hazards[known], edges, age + horizon, method)
                    p = 1.0 - np.clip(s_end / s_age, 0.0, 1.0)
                    row = scores(p, y, tw[known])
                    row.update({"bucket_config": bucket_dir.name, "seed": seed_dir.name,
                                "method": method, "age_s": age, "horizon_s": horizon})
                    shift_rows.append(row)
    return absolute_rows, shift_rows


def aggregate(rows: list[dict], keys: list[str], metrics: list[str]) -> list[dict]:
    groups = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        groups.setdefault(key, []).append(row)
    output = []
    for key, members in sorted(groups.items(), key=lambda item: tuple(str(x) for x in item[0])):
        record = {k: v for k, v in zip(keys, key)}
        record["seeds"] = len(members)
        record["n"] = int(round(np.mean([m["n"] for m in members]))) if "n" in members[0] else None
        for metric in metrics:
            values = np.asarray([m[metric] for m in members], dtype=np.float64)
            record[metric + "_mean"] = float(values.mean())
            record[metric + "_std"] = float(values.std())
        output.append(record)
    return output


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def write_report(out_dir: Path, empirical, abs_summary, shift_summary):
    lines = [
        "# Hazard Curve Interpolation Validation", "",
        "This experiment uses only the held-out test split. Lower scores are better.", "",
        "## Empirical Kaplan–Meier within-bin fit", "",
        "| K | weighting | method | mean abs survival error | event-weighted error |", 
        "|---|---|---|---:|---:|",
    ]
    for k in (5, 10, 20):
        edges_path = out_dir / f"k{k}_edges.json"
        if not edges_path.exists():
            continue
        edges = json.loads(edges_path.read_text())
        rows_k = empirical[f"k{k}"]
        for weighted in (False, True):
            for method in METHODS:
                rows = [r for r in rows_k if r["weighted_km"] == weighted and r["method"] == method and r["interval_events"] > 0]
                if not rows:
                    continue
                mae = np.mean([r["absolute_error"] for r in rows])
                event_mae = np.average([r["absolute_error"] for r in rows], weights=[r["interval_events"] for r in rows])
                lines.append(f"| K={k} | {'token' if weighted else 'object'} | {method} | {mae:.6f} | {event_mae:.6f} |")
    lines += ["", "## Model interpolation at all interior points", "",
              "| K | method | token Brier | token Bernoulli NLL | token ECE10 |",
              "|---|---|---:|---:|---:|"]
    for row in abs_summary:
        lines.append(f"| {row['bucket_config']} | {row['method']} | {row['token_brier_mean']:.6f} | {row['token_bernoulli_nll_mean']:.6f} | {row['token_ece10_mean']:.6f} |")
    lines += ["", "## Conditional Shift interpolation", "",
              "| K | age | horizon | method | token Brier | token NLL | token ECE10 |",
              "|---|---:|---:|---|---:|---:|---:|"]
    for row in shift_summary:
        lines.append(f"| {row['bucket_config']} | {row['age_s']:.0f} | {row['horizon_s']:.0f} | {row['method']} | {row['token_brier_mean']:.6f} | {row['token_bernoulli_nll_mean']:.6f} | {row['token_ece10_mean']:.6f} |")
    lines += ["", "## Interpretation guardrails", "",
              "- Existing MLP endpoints are reused; this is a post-hoc interpolation test.",
              "- The original training loss used partial-censor log-survival interpolation, so the model-level comparison mildly favors log-survival. The Kaplan–Meier comparison does not share that training dependency.",
              "- Tail mass beyond the final finite edge cannot be interpolated and is excluded from age+horizon pairs beyond that edge."]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--checkpoint-root", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    z = np.load(args.data, allow_pickle=False)
    data = {name: z[name] for name in z.files}
    eligible = (data["split"] == 2) & (data["history"] >= 1) & (data["duration"] > 1e-6)
    duration = data["duration"][eligible].astype(np.float64)
    event = data["event"][eligible].astype(bool)
    weights = np.maximum(data["weight"][eligible].astype(np.float64), 1.0)
    empirical = {}
    for bucket_dir in sorted(args.checkpoint_root.glob("k*"), key=lambda x: int(x.name[1:])):
        _, blob = load_checkpoint(bucket_dir / "seed_41" / "initial.pt", torch.device("cpu"))
        edges = np.asarray(blob["edges"], dtype=np.float64)
        (args.out_dir / f"{bucket_dir.name}_edges.json").write_text(json.dumps(edges.tolist()) + "\n")
        empirical[bucket_dir.name] = (
            empirical_interpolation_test(duration, event, weights, edges, False)
            + empirical_interpolation_test(duration, event, weights, edges, True)
        )
    absolute_rows, shift_rows = model_tests(data, args.checkpoint_root, torch.device(args.device))
    abs_summary = aggregate(absolute_rows, ["bucket_config", "method"],
                            ["token_brier", "token_bernoulli_nll", "token_ece10"])
    shift_summary = aggregate(shift_rows, ["bucket_config", "age_s", "horizon_s", "method"],
                              ["token_brier", "token_bernoulli_nll", "token_ece10"])
    payload = {"eligible_test_samples": int(eligible.sum()), "empirical": empirical,
               "model_absolute_points": absolute_rows, "model_absolute_summary": abs_summary,
               "shift_points": shift_rows, "shift_summary": shift_summary}
    (args.out_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
    write_csv(args.out_dir / "model_absolute_points.csv", absolute_rows)
    write_csv(args.out_dir / "shift_points.csv", shift_rows)
    for key, rows in empirical.items():
        write_csv(args.out_dir / f"{key}_empirical_km_points.csv", rows)
    write_report(args.out_dir, empirical, abs_summary, shift_summary)
    print(args.out_dir / "report.md")


if __name__ == "__main__":
    main()
