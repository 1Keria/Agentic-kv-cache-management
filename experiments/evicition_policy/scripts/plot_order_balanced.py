#!/usr/bin/env python3
"""Plot audited repeat metrics using a separate CPU plotting environment."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent.parent


def plot_summary(report, output):
    if not report["all_runs_complete_and_audited"] or not report["all_effective_signatures_equal"]:
        raise ValueError("Plot only complete audited comparisons")
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.7))
    specifications = (
        ("Cache hit rate (%)", lambda row: row["hit_rate"] * 100),
        ("TTFT p95 (s)", lambda row: row["ttft_seconds"]["p95"]),
        ("Replay duration (min)", lambda row: row["measurement_elapsed_seconds"] / 60),
    )
    for axis, (label, value) in zip(axes, specifications):
        for policy, color in (("lru", "#2864ae"), ("slru", "#c96b28")):
            rows = sorted([row for row in report["runs"] if row["policy"] == policy],
                          key=lambda row: row["batch"])
            ys = [value(row) for row in rows]
            axis.plot([1, 2], ys, "o-", label=policy.upper(), color=color, linewidth=1.5)
            for x, y in zip([1, 2], ys):
                axis.annotate(f"{y:.2f}", (x, y), xytext=(6, 5),
                              textcoords="offset points", fontsize=8, color=color)
        axis.set_xticks([1, 2], ["LRU -> SLRU", "SLRU -> LRU"])
        axis.set_xlim(.8, 2.3)
        axis.set_ylabel(label)
        axis.grid(axis="y", alpha=.2)
        axis.spines[["top", "right"]].set_visible(False)
        axis.margins(y=.3)
    axes[0].legend(frameon=False)
    fig.suptitle("Agent-only native policy repeats: 1,206 requests per run", fontsize=12)
    fig.text(.5, .01, "Two runs per policy; connected values show repeat variation, not a causal time trend.",
             ha="center", fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, .045, 1, .95))
    for extension in ("png", "svg"):
        target = output / f"comparison.{extension}"
        if target.exists():
            raise ValueError(f"Refusing to overwrite: {target}")
        fig.savefig(target, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output_dir.resolve()
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        raise ValueError("Keep figures inside this experiment")
    output.mkdir(parents=True, exist_ok=True)
    plot_summary(json.loads(source.read_text()), output)


if __name__ == "__main__":
    main()
