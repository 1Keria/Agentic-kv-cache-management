#!/usr/bin/env python3
"""Export the observed-history gap decomposition; not avoidable policy loss."""

import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    from pathlib import Path
    summary = json.loads(Path(args.summary).read_text())
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, run in enumerate(summary["runs"]):
        values = run["match_tokens"]
        missing = values["history_beyond_resident_full"] / 1e6
        stranded = values["resident_full_without_joint_match"] / 1e6
        ax.barh(i, missing, color="#d08b47", height=.44,
                label="History beyond resident Full" if i == 0 else None)
        ax.barh(i, stranded, left=missing, color="#327da0", height=.44,
                label="Full resident, joint match unavailable" if i == 0 else None)
        ax.text(missing + stranded + .15, i,
                f"{values['resident_full_without_joint_share']:.2%}\nFull still resident",
                va="center", fontsize=10)
    ax.set_yticks(range(len(summary["runs"])), [run["policy"].upper() for run in summary["runs"]])
    ax.invert_yaxis()
    ax.set_xlim(0, 17)
    ax.set_xlabel("Observed materialization shortfall (million tokens)")
    ax.set_title("Missing joint reuse is mostly behind resident Full prefixes", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=.18)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.23), frameon=False, fontsize=9)
    fig.text(.5, .02, "One observed run per policy; finite-budget avoidable loss is not estimated.",
             ha="center", fontsize=9, color="#555555")
    fig.subplots_adjust(bottom=.3, top=.83, left=.09, right=.98)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(output.with_suffix("." + suffix), dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
