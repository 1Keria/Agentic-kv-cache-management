#!/usr/bin/env python3
"""Export scientific comparisons from both audited checkpoint summaries."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analyze_resizable_native import digest, read


def plot(source, workspace_source, output):
    v3, workspace = read(source), read(workspace_source)
    assert v3["all_checks_passed"] and workspace["all_checks_passed"]
    assert workspace["v3_analysis_sha256"] == digest(source)
    output.mkdir(parents=True, exist_ok=False)
    phases = ("initial", "half", "quarter", "restored")
    variants = ("lru", "v1", "v2", "partial", "v3", "workspace")
    labels = ("Native LRU", "v1", "v2 retained admission", "Partial only", "v3 + downgrade", "v3 + workspace")
    colors = ("#7c8794", "#ac8caf", "#4385b0", "#daab42", "#429676", "#ce6758")
    conditions = {**v3["archived_baselines"], **v3["conditions"], **workspace["conditions"]}
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8), constrained_layout=True)
    x = np.arange(4)
    for axis, profile, title in zip(axes[0], ("constant", "shrink_restore"),
                                    ("Constant capacity control", "Continuous shrink / restore")):
        for offset, (variant, label, color) in enumerate(zip(variants, labels, colors)):
            values = [100 * conditions[profile + "_" + variant]["phases"][p]["hit_rate"] for p in phases]
            axis.bar(x + (offset - 2.5) * .14, values, .135, color=color, label=label)
        axis.set_xticks(x, ("Initial", "Half interval", "Quarter interval", "Restored interval"))
        axis.set_title(title)
        axis.set_ylim(0, 85)
        axis.set_ylabel("Token-weighted hit rate (%)")
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
    axes[0, 0].legend(loc="upper left", fontsize=8, ncol=2, frameon=False)
    rates = [100 * conditions["shrink_restore_" + v]["phases"]["quarter"]["hit_rate"] for v in variants]
    axes[1, 0].bar(np.arange(len(variants)), rates, color=colors)
    axes[1, 0].set_xticks(np.arange(len(variants)), ("LRU", "v1", "v2", "Partial", "v3", "Workspace"))
    axes[1, 0].set_title("Quarter-capacity detail")
    axes[1, 0].set_ylabel("Token-weighted hit rate (%)")
    axes[1, 0].set_ylim(0, max(1.0, max(rates) * 1.25))
    for index, rate in enumerate(rates):
        axes[1, 0].text(index, rate, f"{rate:.3f}", ha="center", va="bottom", fontsize=8)
    comparisons = ((v3, "shrink_restore_partial_vs_v2", "Partial minus v2", colors[3]),
                   (v3, "shrink_restore_v3_vs_partial", "Downgrade increment", colors[4]),
                   (workspace, "shrink_restore_workspace_vs_v3", "Workspace increment", colors[5]))
    for offset, (summary, key, label, color) in enumerate(comparisons):
        values = [summary["comparisons"][key]["phases"][p]["hit_rate_delta_pp"] for p in phases]
        axes[1, 1].bar(x + (offset - 1) * .25, values, .24, color=color, label=label)
    axes[1, 1].set_xticks(x, ("Initial", "Half", "Quarter", "Restored"))
    axes[1, 1].axhline(0, color="#777", linewidth=.8)
    axes[1, 1].set_ylabel("Net hit rate change (percentage points)")
    axes[1, 1].set_title("Mechanism increments, including regressions")
    axes[1, 1].legend(frameon=False, fontsize=8)
    for axis in axes[1]:
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
    fig.suptitle("Resident Full/SWA checkpoints and arrived-request workspace reserve\n"
                 "20 frozen sessions / 1,206 requests per condition; CPU indices, zero policy-added splits", fontsize=12)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(output / ("native_checkpoint_comparison." + suffix), dpi=180)
    plt.close(fig)
    manifest = {"sources_sha256": {str(p.resolve()): digest(p) for p in (source, workspace_source)},
                "outputs_sha256": {p.name: digest(p) for p in output.iterdir()},
                "scope": "Single deterministic trace. No GPU computation, latency measurements or population uncertainty estimates."}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--workspace-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(args.source, args.workspace_source, args.output)
