#!/usr/bin/env python3
"""Plot empirical KM and three within-bucket survival interpolations."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def km_at_times(durations: np.ndarray, events: np.ndarray, weights: np.ndarray,
                query_times: np.ndarray) -> np.ndarray:
    """Kaplan-Meier S(t-) at query times (events exactly at t are excluded)."""
    order = np.argsort(durations, kind="stable")
    d = durations[order].astype(np.float64)
    e = events[order].astype(bool)
    w = weights[order].astype(np.float64)
    unique, starts = np.unique(d, return_index=True)
    ends = np.r_[starts[1:], len(d)]
    risk = float(w.sum())
    survival = 1.0
    event_times = []
    survival_after = []
    for t, lo, hi in zip(unique, starts, ends):
        event_weight = float(w[lo:hi][e[lo:hi]].sum())
        if event_weight > 0 and risk > 0:
            survival *= max(0.0, 1.0 - event_weight / risk)
            event_times.append(float(t))
            survival_after.append(survival)
        risk -= float(w[lo:hi].sum())
    event_times = np.asarray(event_times, dtype=np.float64)
    survival_after = np.asarray(survival_after, dtype=np.float64)
    out = np.ones(len(query_times), dtype=np.float64)
    if len(event_times):
        idx = np.searchsorted(event_times, query_times, side="left") - 1
        valid = idx >= 0
        out[valid] = survival_after[idx[valid]]
    return out


def plot_config(duration, event, token_weight, edges, label, weighted, out_dir):
    n_bins = len(edges)
    cols = 2 if n_bins <= 4 else (3 if n_bins <= 9 else 4)
    rows = math.ceil(n_bins / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(4.8 * cols, 3.8 * rows), squeeze=False)
    weights = token_weight if weighted else np.ones_like(token_weight)
    left = 0.0
    legend_handles = None
    for bucket, right in enumerate(edges):
        ax = axes.flat[bucket]
        # Dense absolute-time grid. Endpoint uses S(right-) to match [left,right).
        grid = np.linspace(left, float(right), 241)
        empirical_abs = km_at_times(duration, event, weights, grid)
        s_left = float(km_at_times(duration, event, weights, np.asarray([left]))[0])
        s_right = float(km_at_times(duration, event, weights, np.asarray([float(right)]))[0])
        empirical = np.clip(empirical_abs / max(s_left, 1e-12), 0.0, 1.0)
        q = np.clip(s_right / max(s_left, 1e-12), 0.0, 1.0)
        u = (grid - left) / max(float(right) - left, 1e-12)
        log_curve = np.power(max(q, 1e-12), u)
        linear_curve = 1.0 - u * (1.0 - q)
        line1, = ax.step(grid, empirical, where="post", color="black", linewidth=2.2,
                         label="Empirical Kaplan–Meier")
        line2, = ax.plot(grid, log_curve, color="#1565c0", linewidth=2,
                         label="Log-survival (constant hazard)")
        line3, = ax.plot(grid, linear_curve, color="#ef6c00", linewidth=2, linestyle="--",
                         label="Linear-survival")
        line4, = ax.plot([left, float(right)], [1.0, 1.0], color="#7b1fa2", linewidth=1.8,
                         linestyle=":", label="No interpolation (right-step)")
        ax.plot([float(right), float(right)], [1.0, q], color="#7b1fa2", linewidth=1.8,
                linestyle=":")
        ax.scatter([float(right)], [q], color="#7b1fa2", s=18, zorder=4)
        if legend_handles is None:
            legend_handles = [line1, line2, line3, line4]
        at_risk = int((duration >= left).sum())
        interval_events = int((event & (duration >= left) & (duration < right)).sum())
        ax.set_title(f"[{left:g}, {float(right):g}) s\nat risk={at_risk:,}, events={interval_events:,}", fontsize=10)
        ax.set_xlim(left, float(right))
        ax.set_ylim(-0.02, 1.03)
        ax.grid(alpha=0.22)
        ax.set_xlabel("Gap time t (seconds)")
        ax.set_ylabel("P(T > t | T ≥ bucket start)")
        left = float(right)
    for ax in axes.flat[n_bins:]:
        ax.axis("off")
    weighting = "token-weighted" if weighted else "object-weighted"
    fig.suptitle(f"{label}: empirical survival vs within-bucket assumptions ({weighting})",
                 fontsize=15, y=0.995)
    fig.legend(legend_handles, [h.get_label() for h in legend_handles], loc="lower center",
               ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.002))
    fig.tight_layout(rect=(0, 0.035, 1, 0.975))
    stem = f"{label}_{'token' if weighted else 'object'}_survival_curves"
    fig.savefig(out_dir / f"{stem}.png", dpi=180, bbox_inches="tight")
    fig.savefig(out_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def plot_focused(duration, event, token_weight, configs, out_dir):
    """One compact figure showing the most informative short-gap buckets."""
    choices = [("K=5", 0), ("K=5", 1), ("K=5", 2), ("K=10", 4), ("K=20", 6), ("K=20", 7)]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), squeeze=False)
    handles = None
    for ax, (name, bucket) in zip(axes.flat, choices):
        edges = configs[name]
        left = 0.0 if bucket == 0 else float(edges[bucket - 1])
        right = float(edges[bucket])
        grid = np.linspace(left, right, 241)
        empirical_abs = km_at_times(duration, event, token_weight, grid)
        s_left = km_at_times(duration, event, token_weight, np.asarray([left]))[0]
        s_right = km_at_times(duration, event, token_weight, np.asarray([right]))[0]
        empirical = np.clip(empirical_abs / max(s_left, 1e-12), 0, 1)
        q = np.clip(s_right / max(s_left, 1e-12), 0, 1)
        u = (grid - left) / (right - left)
        a, = ax.step(grid, empirical, where="post", color="black", linewidth=2.4,
                     label="Empirical Kaplan–Meier")
        b, = ax.plot(grid, np.power(max(q, 1e-12), u), color="#1565c0", linewidth=2.2,
                     label="Log-survival")
        c, = ax.plot(grid, 1-u*(1-q), color="#ef6c00", linestyle="--", linewidth=2.2,
                     label="Linear-survival")
        d, = ax.plot([left, right], [1, 1], color="#7b1fa2", linestyle=":", linewidth=2,
                     label="No interpolation")
        ax.plot([right, right], [1, q], color="#7b1fa2", linestyle=":", linewidth=2)
        ax.scatter([right], [q], color="#7b1fa2", s=18)
        if handles is None:
            handles = [a, b, c, d]
        nevent = int((event & (duration >= left) & (duration < right)).sum())
        ax.set_title(f"{name}, bucket [{left:g}, {right:g}) s, events={nevent:,}")
        ax.set_ylim(-0.02, 1.03); ax.set_xlim(left, right); ax.grid(alpha=.22)
        ax.set_xlabel("Gap time t (seconds)")
        ax.set_ylabel("Conditional survival")
    fig.suptitle("Key short-gap buckets (token-weighted empirical curve)", fontsize=15)
    fig.legend(handles, [h.get_label() for h in handles], loc="lower center", ncol=4,
               frameon=False, bbox_to_anchor=(0.5, 0.005))
    fig.tight_layout(rect=(0, .045, 1, .96))
    fig.savefig(out_dir / "focused_short_gap_survival_comparison.png", dpi=200, bbox_inches="tight")
    fig.savefig(out_dir / "focused_short_gap_survival_comparison.pdf", bbox_inches="tight")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--exp-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    z = np.load(args.data, allow_pickle=False)
    eligible = (z["split"] == 2) & (z["history"] >= 1) & (z["duration"] > 1e-6)
    duration = z["duration"][eligible].astype(np.float64)
    event = z["event"][eligible].astype(bool)
    token_weight = np.maximum(z["weight"][eligible].astype(np.float64), 1.0)
    configs = {}
    for k in (5, 10, 20):
        edges = np.asarray(json.loads((args.exp_dir / f"k{k}_edges.json").read_text()), dtype=np.float64)
        configs[f"K={k}"] = edges
        plot_config(duration, event, token_weight, edges, f"K{k}", False, args.out_dir)
        plot_config(duration, event, token_weight, edges, f"K{k}", True, args.out_dir)
    plot_focused(duration, event, token_weight, configs, args.out_dir)
    readme = [
        "# Hazard curve graphs", "",
        "Each panel conditions on surviving to the bucket's left boundary.",
        "", "- Black steps: held-out Kaplan–Meier empirical survival.",
        "- Blue: log-survival interpolation (piecewise-constant hazard).",
        "- Orange: linear-survival interpolation.",
        "- Purple: no interpolation; probability changes only at the right edge.",
        "- `object` gives every prefix equal weight; `token` weights by estimated incremental tokens.",
        "- Infinite tail buckets are omitted because they have no finite right edge.",
    ]
    (args.out_dir / "README.md").write_text("\n".join(readme) + "\n")
    print(args.out_dir)


if __name__ == "__main__":
    main()
