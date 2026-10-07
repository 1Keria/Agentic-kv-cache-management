#!/usr/bin/env python3
"""Plot content demand evidence; these charts do not show runtime candidates."""

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Output filename stem")
    parser.add_argument("--replace", action="store_true", help="Regenerate these explicitly named figure outputs")
    args = parser.parse_args()
    source, output = args.analysis.resolve(), args.output.resolve()
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        raise ValueError("Keep inputs and outputs inside the experiment")
    outputs = [output.with_suffix(suffix) for suffix in (".png", ".svg", ".json")]
    if not args.replace and any(path.exists() for path in outputs):
        raise FileExistsError("Refusing to overwrite existing figures")
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path, histogram_path = source / "summary.json", source / "input_page_demand_histogram.csv"
    summary = json.loads(summary_path.read_text())
    with histogram_path.open(newline="") as stream:
        bins = list(csv.DictReader(stream))
    demand = summary["input_content_demand"]
    tree = summary["unbounded_input_history_tree_reference"]["policies"]["lru"]
    assert sum(int(row["distinct_content_pages"]) for row in bins) == demand["unique_complete_input_content_pages"]

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans", "svg.fonttype": "none"})
    fig, (left, right) = plt.subplots(1, 2, figsize=(12.6, 4.8), gridspec_kw={"width_ratios": [1, 1.15]})
    blue, amber = "#356B8C", "#D59B48"
    values = [int(row["distinct_content_pages"]) for row in bins]
    labels = [row["observed_request_demand_count_bin"].replace("_plus", "+").replace("_", "–") for row in bins]
    bars = left.bar(labels, values,
                    color=[amber] + [blue] * (len(values) - 1), width=0.65)
    left.bar_label(bars, labels=[f"{value:,}" for value in values], padding=4, fontsize=9)
    left.set_ylim(0, max(values) * 1.2)
    left.set_title("Observed demand per distinct input-prefix page", loc="left", fontsize=11)
    left.set_xlabel("Number of requesting inputs")
    left.set_ylabel("Distinct complete pages (256 tokens each)")
    left.set_axisbelow(True)
    left.grid(axis="y", alpha=0.2)

    total = [demand["unique_complete_input_content_pages"], tree["final_history_internal_pages"], tree["final_history_leaf_pages"]]
    repeated = [demand["pages_with_at_least_two_observed_request_demands"], tree["final_history_internal_pages_repeated_demand"], tree["final_history_leaf_pages_repeated_demand"]]
    labels = [f"All input pages\nn={total[0]:,}", f"Internal pages*\nn={total[1]:,}", f"Leaf pages*\nn={total[2]:,}"]
    repeated_pct = [100 * n / d for n, d in zip(repeated, total)]
    once_pct = [100 - value for value in repeated_pct]
    right.barh(labels, repeated_pct, color=blue, label="At least two observed demands")
    right.barh(labels, once_pct, left=repeated_pct, color=amber, label="One observed demand")
    for index, value in enumerate(repeated_pct):
        right.text(101.5, index, f"{value:.2f}%\nrepeated", va="center", fontsize=9, color=blue)
    right.invert_yaxis()
    right.set_xlim(0, 118)
    right.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    right.set_xlabel("Share of distinct complete pages in each group")
    right.set_title("Repeat-demand evidence depends on tree position", loc="left", fontsize=11)
    right.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=1, frameon=False, fontsize=9)
    for axis in (left, right):
        axis.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Agent-only frozen workload: content reuse and growing prefix chains", fontsize=13, y=0.97)
    fig.text(0.04, 0.025,
             "* Final input-history tree: unlimited retention, no locks, no generated outputs.\n"
             "Content pages are not runtime radix nodes or legal eviction candidates; unobserved future remains unknown.",
             fontsize=9, color="#444444")
    fig.subplots_adjust(left=0.07, right=0.96, bottom=0.28, top=0.82, wspace=0.43)
    fig.savefig(outputs[0], dpi=180)
    fig.savefig(outputs[1])
    plt.close(fig)
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    outputs[2].write_text(json.dumps({
        "purpose": "Scientific content-demand figure; not a real eviction-frontier plot",
        "inputs": {str(path.relative_to(ROOT)): digest(path) for path in (summary_path, histogram_path, Path(__file__))},
        "outputs": {path.name: digest(path) for path in outputs[:2]},
    }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"outputs": [str(path) for path in outputs]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
