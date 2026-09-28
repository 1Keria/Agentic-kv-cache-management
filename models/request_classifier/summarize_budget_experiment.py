#!/usr/bin/env python3
"""Combine searched, holdout, and finalized identity-classifier results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def combine_holdout(report: dict) -> dict:
    entries = list(report["holdout"].values())
    total = sum(item["metrics"]["n"] for item in entries)
    confusion = {
        key: sum(item["metrics"]["confusion"][key] for item in entries)
        for key in ("true_agent", "false_agent", "missed_agent", "true_request")
    }
    return {
        "n": total,
        "accuracy": (confusion["true_agent"] + confusion["true_request"]) / total,
        "precision_agent": confusion["true_agent"] / max(confusion["true_agent"] + confusion["false_agent"], 1),
        "recall_agent": confusion["true_agent"] / max(confusion["true_agent"] + confusion["missed_agent"], 1),
        "f1_agent": 2 * confusion["true_agent"] / max(2 * confusion["true_agent"] + confusion["false_agent"] + confusion["missed_agent"], 1),
        "min_source_accuracy": min(item["metrics"]["accuracy"] for item in entries),
        "min_source_agent_recall": min(item["metrics"]["recall_agent"] for item in entries),
        "confusion": confusion,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("models/request_classifier/checkpoints"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    budgets: dict[str, dict] = {}
    for budget in (1, 2, 4, 8, 12, 16):
        search = json.loads((args.root / f"parallel_search_budget_{budget}.json").read_text(encoding="utf-8"))
        holdout = json.loads((args.root / f"parallel_holdout_budget_{budget}.json").read_text(encoding="utf-8"))
        final = json.loads((args.root / "final_searched" / f"budget_{budget}" / "metrics.json").read_text(encoding="utf-8"))
        searched = search["budgets"][str(budget)]
        budgets[str(budget)] = {
            "features": searched["features"],
            "candidate_count": searched["candidates_evaluated"],
            "validation": searched["validation"],
            "grouped_test": searched["grouped_test"],
            "source_metrics": searched["source_holdout"],
            "cross_source_combined": combine_holdout(holdout),
            "finalized_grouped_test": final["grouped_test"],
            "checkpoint": final["checkpoint"],
        }

    report = {
        "task": "request identity classification: agent application vs ordinary application",
        "protocol": {
            "records": 66592,
            "raw_workload_records": 134629,
            "source_groups": 31166,
            "sources": {
                "glm_online": {"records": 16559, "labels": "16553 agent-like + 6 request"},
                "skillsbench": {"records": 7737, "labels": "7737 agent-like"},
                "wildchat": {"records": 42296, "labels": "42296 request"},
            },
            "deduplication": "source identity + call/turn position + max_tokens + prompt_body",
            "selection": "validation-only candidate search, seed=4200",
            "grouped_split": "source-group stratified 60/20/20",
            "cross_source_holdout": "hold out GLM or SkillsBench and add unseen WildChat negatives",
            "threshold": 0.5,
            "devices": "NVIDIA H100 80GB: cuda:0-cuda:6",
        },
        "budgets": budgets,
        "recommendation": {
            "current_data_smallest_best": 1,
            "current_data_balanced": 4,
            "production_status": "candidate only; labels and protocol semantics still need independent audit",
            "reason": "1/2/4 have identical perfect cross-source metrics; larger budgets add no reliable identity signal and 8/12/16 introduce errors in at least one holdout.",
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[write] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
