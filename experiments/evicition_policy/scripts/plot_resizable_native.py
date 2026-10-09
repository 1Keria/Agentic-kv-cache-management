#!/usr/bin/env python3
"""Export cache-state figures; no CPU wall time is used as serving latency."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"lru": "#497ca7", "frontier": "#bd713c"}
LABELS = ("Initial", "Half", "Quarter", "Restored")
PHASES = ("initial", "half", "quarter", "restored")


def read_rows(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream]


def export(fig, destination, stem):
    for extension in ("png", "svg", "pdf"):
        fig.savefig(destination / (stem + "." + extension), dpi=180, bbox_inches="tight")
    plt.close(fig)


def mark_phases(axis):
    for index in (301, 603, 904):
        axis.axvline(index, color="#888888", linewidth=0.8, linestyle=":")


def plot(summary_path, destination):
    summary_path, destination = summary_path.resolve(), destination.resolve()
    if not destination.is_relative_to(ROOT / "reports") or destination.exists():
        raise ValueError("Use a new figure directory under reports")
    summary = json.loads(summary_path.read_text())
    assert summary["all_checks_passed"]
    source = ROOT / summary["source"]
    data = {name: read_rows(source / name / "requests.jsonl") for name in summary["conditions"]}
    destination.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), sharey=True)
    for axis, profile in zip(axes, ("constant", "shrink_restore"), strict=True):
        for offset, policy in zip((-0.18, 0.18), ("lru", "frontier"), strict=True):
            condition = summary["conditions"][profile + "_" + policy]
            missing_full = [condition["phases"][p]["full_history_missing_tokens"] / 1e6 for p in PHASES]
            joint_gap = [condition["phases"][p]["full_resident_but_joint_unavailable_tokens"] / 1e6 for p in PHASES]
            positions = np.arange(4) + offset
            axis.bar(positions, missing_full, width=0.33, color=COLORS[policy],
                     label=policy.upper() + ": missing Full history")
            axis.bar(positions, joint_gap, bottom=missing_full, width=0.33, color=COLORS[policy],
                     alpha=0.4, hatch="//", label=policy.upper() + ": Full present, joint unavailable")
        axis.set_xticks(np.arange(4), LABELS)
        axis.set_title("Constant budget" if profile == "constant" else "Shrink and restore")
        axis.grid(axis="y", alpha=0.15)
    axes[0].set_ylabel("Lost historical reuse (million tokens)")
    axes[1].legend(fontsize=8)
    fig.suptitle("Same 1,206 input requests: loss decomposition under a changing Agent budget")
    fig.text(0.5, 0.01, "Constant-budget bars use the same request slices; no budget changes in that control.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.055, 1, 0.94))
    export(fig, destination, "loss_decomposition")

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    for profile in ("constant", "shrink_restore"):
        for policy in ("lru", "frontier"):
            rows = data[profile + "_" + policy]
            prompt = np.array([r["prompt_tokens"] for r in rows], dtype=float)
            cached = np.array([r["matched_tokens"] for r in rows], dtype=float)
            cumulative_prompt = np.r_[0, np.cumsum(prompt)]
            cumulative_cached = np.r_[0, np.cumsum(cached)]
            end = np.arange(1, len(rows) + 1)
            start = np.maximum(0, end - 50)
            rolling = (cumulative_cached[end] - cumulative_cached[start]) / (
                cumulative_prompt[end] - cumulative_prompt[start]) * 100
            axes[0].plot(end - 1, rolling, color=COLORS[policy],
                         linestyle="-" if profile == "shrink_restore" else "--",
                         alpha=1 if profile == "shrink_restore" else 0.45,
                         label=policy.upper() + (" changing" if profile == "shrink_restore" else " constant"))
    for policy in ("lru", "frontier"):
        rows = data["shrink_restore_" + policy]
        axes[1].plot([r["after"]["resident"]["full"] / 1000 for r in rows],
                     color=COLORS[policy], linewidth=0.9, label=policy.upper() + " resident")
        axes[2].plot([r["after"]["frontier"]["units"] for r in rows],
                     color=COLORS[policy], linewidth=0.9, label=policy.upper() + " protected boundaries")
    changing = data["shrink_restore_frontier"]
    axes[1].step(range(len(changing)), [r["hard_budget"]["full"] / 1000 for r in changing],
                 where="post", color="black", linestyle="--", label="Agent Full hard budget")
    axes[0].set_ylabel("Rolling 50-request\ntoken hit rate (%)")
    axes[1].set_ylabel("Full token slots (thousands)")
    axes[2].set_ylabel("Protected boundaries")
    axes[2].set_xlabel("Frozen request index")
    for axis in axes:
        mark_phases(axis)
        axis.grid(alpha=0.12)
        axis.legend(fontsize=8, loc="upper left")
    axes[0].set_title("One uninterrupted instance per condition: initial -> half -> quarter -> restored")
    fig.text(0.5, 0.01, "Official tree and allocator on CPU; input-only replay. These are cache-state metrics, not TTFT.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    export(fig, destination, "resize_timeline")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(args.summary, args.output)
