#!/usr/bin/env python3
"""Evaluate candidate feature sets with source-family holdouts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from features import FEATURE_BUDGETS, FEATURE_NAMES
from search_budgets import split_groups, train_one, evaluate


def selected_from_names(names: list[str]) -> tuple[int, ...]:
    return tuple(FEATURE_NAMES.index(name) for name in names)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--search-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    data = np.load(args.cache, allow_pickle=True)
    x = data["features"]
    y = data["labels"].astype(np.float32)
    kinds = data["kinds"]
    groups = data["groups"]
    previous = json.loads(args.search_report.read_text(encoding="utf-8"))["budgets"]
    candidates: dict[str, set[tuple[int, ...]]] = {}
    for budget in (1, 2, 4, 8, 12, 16):
        choices = {selected_from_names(list(FEATURE_BUDGETS[budget]))}
        choices.add(selected_from_names(list(previous[str(budget)]["features"])))
        for item in previous[str(budget)].get("top_validation", []):
            choices.add(selected_from_names(item["features"]))
        if budget == 1:
            choices.update((index,) for index in range(len(FEATURE_NAMES)))
        if budget == 2:
            import itertools
            choices.update(itertools.combinations(range(len(FEATURE_NAMES)), 2))
        candidates[str(budget)] = choices

    device = torch.device(args.device)
    report: dict[str, object] = {
        "protocol": {
            "holdouts": ["glm_online", "skillsbench"],
            "training": "the other two source families, grouped 80/20 train/validation",
            "selection": "mean held-out accuracy with GLM agent recall tie-break",
            "device": str(device),
            "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        },
        "budgets": {},
    }
    for budget in (1, 2, 4, 8, 12, 16):
        rows: list[dict[str, object]] = []
        for number, selected in enumerate(sorted(candidates[str(budget)]), 1):
            result: dict[str, object] = {"features": [FEATURE_NAMES[index] for index in selected], "holdout": {}}
            for held_kind in ("glm_online", "skillsbench"):
                pool = np.flatnonzero(kinds != held_kind)
                train_local, val_local, _ = split_groups(y[pool], groups[pool], args.seed)
                train_indices = pool[train_local]
                val_indices = pool[val_local]
                model, _, validation = train_one(
                    x, y, train_indices, val_indices, selected, device, args.seed + number, epochs=20, patience=4
                )
                held_indices = np.flatnonzero(kinds == held_kind)
                wild_validation = val_indices[kinds[val_indices] == "wildchat"]
                test_indices = np.concatenate((held_indices, wild_validation))
                held_metrics = evaluate(model, x[train_indices], y[train_indices], x[test_indices], y[test_indices], selected, device)
                result["holdout"][held_kind] = {
                    "train_records": int(len(train_indices)),
                    "held_source_records": int(len(held_indices)),
                    "wildchat_test_records": int(len(wild_validation)),
                    "test_records": int(len(test_indices)),
                    "validation": validation,
                    "metrics": held_metrics,
                }
            glm = result["holdout"]["glm_online"]["metrics"]
            skills = result["holdout"]["skillsbench"]["metrics"]
            result["robust_score"] = float(
                0.5 * (min(glm["accuracy"], skills["accuracy"]) + glm["recall_agent"])
            )
            rows.append(result)
            if number % 16 == 0 or number == len(candidates[str(budget)]):
                print(f"budget={budget} candidate={number}/{len(candidates[str(budget)])}", flush=True)
        rows.sort(key=lambda row: (row["robust_score"], row["holdout"]["glm_online"]["metrics"]["accuracy"], -row["holdout"]["glm_online"]["metrics"]["log_loss"]), reverse=True)
        report["budgets"][str(budget)] = {
            "candidates_evaluated": len(rows),
            "best": rows[0],
            "top": rows[:10],
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[write] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
