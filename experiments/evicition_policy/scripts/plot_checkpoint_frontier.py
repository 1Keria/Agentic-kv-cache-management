#!/usr/bin/env python3
"""Standalone scientific phase comparison from the audited v3 summary."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_resizable_native import digest, read


def plot(source, output):
    summary = read(source)
    assert summary["all_checks_passed"]
    output.mkdir(parents=True, exist_ok=False)
    phases = ("initial", "half", "quarter", "restored")
    colors = {"lru": "#7c8794", "v2": "#4385b0", "partial": "#daab42", "v3": "#429676"}
    names = {"lru": "Native LRU (archived)", "v2": "v2 retained admission",
             "partial": "Partial checkpoints only", "v3": "v3 + resident downgrade"}
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True, constrained_layout=True)
    for axis, profile, title in zip(axes, ("constant", "shrink_restore"),
                                    ("Constant capacity control", "Continuous shrink / restore")):
        x = np.arange(4)
        for offset, variant in enumerate(("lru", "v2", "partial", "v3")):
            name = profile + "_" + variant
            metrics = summary["conditions"].get(name, summary["archived_baselines"].get(name))
            values = [100 * metrics["phases"][phase]["hit_rate"] for phase in phases]
            axis.bar(x + (offset - 1.5) * .19, values, .18, color=colors[variant], label=names[variant])
        axis.set_xticks(x, ("Initial", "Half interval", "Quarter interval", "Restored interval"))
        axis.set_title(title)
        axis.set_ylim(0, 100)
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Token-weighted cache hit rate (%)")
    axes[0].legend(loc="upper left", frameon=False, fontsize=8)
    fig.suptitle("Native Full/SWA cache: real checkpoint retention\n"
                 "20 frozen sessions / 1,206 requests per condition; CPU indices only", fontsize=12)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(output / ("phase_comparison." + suffix), dpi=180)
    plt.close(fig)
    manifest = {"source": str(source.resolve()), "source_sha256": digest(source),
                "outputs_sha256": {p.name: digest(p) for p in output.iterdir()},
                "scope": "Deterministic single-trace mechanism comparison. No model/latency measurements or statistical significance claim."}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(args.source, args.output)
