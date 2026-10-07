#!/usr/bin/env python3
"""Make standalone figures from completed, audited serving measurements."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COLORS = {"native": "#6f7580", "unified": "#5376ae", "fixed": "#d39337", "borrow": "#208478"}
SCENARIOS = [
    ("phase_mem035_threeway", "Phase stress (n=1,261)"),
    ("bidirectional_mem035_threeway", "Large request set (n=275)"),
    ("calibrated_mem035_threeway", "Terminal probes + scan (n=1,277)"),
]


def save(fig, output: Path, name: str) -> None:
    fig.savefig(output / f"{name}.png", dpi=180, bbox_inches="tight")
    fig.savefig(output / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    data = json.loads((root / "analysis.json").read_text())
    output = root / "figures"
    output.mkdir(exist_ok=True)
    cases = []
    for scenario, label in SCENARIOS:
        modes = dict(data.get(scenario, {}).get("modes", {}))
        if scenario == "calibrated_mem035_threeway":
            modes.update(data.get("calibrated_mem035_native", {}).get("modes", {}))
        if modes:
            cases.append((label, modes))
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.7))
    for ax, (label, modes) in zip(axes, cases):
        names = [mode for mode in COLORS if mode in modes]
        values = [100 * modes[mode]["summary"]["overall_hit"] for mode in names]
        bars = ax.bar(names, values, color=[COLORS[mode] for mode in names], width=.65)
        ax.bar_label(bars, fmt="%.2f%%", padding=3, fontsize=9)
        ax.set_ylim(0, 100)
        ax.set_ylabel("Token-weighted hit rate (%)")
        ax.set_title(label, fontsize=11)
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle("Controlled pressure workload; one serving run per condition; fixed output = 16 tokens")
    fig.tight_layout()
    save(fig, output, "overall_hit")

    terminal = dict(data.get("calibrated_mem035_threeway", {}).get("modes", {}))
    terminal.update(data.get("calibrated_mem035_native", {}).get("modes", {}))
    if terminal:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
        names = [mode for mode in COLORS if mode in terminal]
        for ax, first in zip(axes, (True, False)):
            values = []
            for mode in names:
                phase = terminal[mode]["phases"]["request_second"]
                key = "first_turn_token_weighted_hit" if first else "token_weighted_hit"
                values.append(100 * (phase[key] or 0))
            bars = ax.bar(names, values, color=[COLORS[mode] for mode in names], width=.65)
            ax.bar_label(bars, fmt="%.2f%%", padding=3)
            ax.set_ylim(0, 105)
            ax.set_ylabel("Token-weighted hit rate (%)")
            ax.set_title("First return probes (n=2)" if first else "All return requests (n=8)")
            ax.grid(axis="y", alpha=.2)
            ax.set_axisbelow(True)
        fig.suptitle("First-probe hits measure retention; later requests may warm the cache again")
        fig.tight_layout()
        save(fig, output, "terminal_return_hits")

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex="col")
    plotted = False
    for col, mode in enumerate(("fixed", "borrow")):
        path = root / "calibrated_mem035_threeway" / mode / "controller_trajectory.jsonl"
        if not path.exists():
            continue
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        rows = [row for row in rows if row.get("regions")]
        if not rows:
            continue
        plotted = True
        times = np.array([row["elapsed_s"] for row in rows])
        for ax, pool in zip(axes[:, col], ("full", "swa")):
            for region, color in (("agent", "#4775a8"), ("request", "#bf7337")):
                used = [row["regions"][region][f"{pool}_used_tokens"] / 1000 for row in rows]
                base = rows[0]["regions"][region][f"base_{pool}_capacity_tokens"] / 1000
                ax.plot(times, used, color=color, label=f"{region} used")
                ax.axhline(base, color=color, linestyle="--", alpha=.7, label=f"{region} guarantee")
            ax.set_title(f"{mode}: {pool.upper()} pool")
            ax.set_ylabel("Resident tokens (thousands)")
            ax.grid(alpha=.2)
            ax.legend(fontsize=8, ncol=2)
        axes[1, col].set_xlabel("Replay elapsed time (s)")
    if plotted:
        fig.suptitle("Same region rule for both pools; separate physical accounting")
        fig.tight_layout()
        save(fig, output, "region_occupancy")
    else:
        plt.close(fig)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
