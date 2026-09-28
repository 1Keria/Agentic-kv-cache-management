#!/usr/bin/env python3
"""Evaluate one searched feature budget on source-family holdouts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from features import FEATURE_NAMES
from search_budgets import evaluate, split_groups, train_one


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, required=True)
    parser.add_argument("--search-report", type=Path, required=True)
    parser.add_argument("--features", help="Comma-separated feature names; overrides --search-report")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=4200)
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    data = np.load(args.cache, allow_pickle=True)
    features = data["features"]
    labels = data["labels"].astype(np.float32)
    kinds = data["kinds"]
    groups = data["groups"]
    if args.features:
        names = [name.strip() for name in args.features.split(",") if name.strip()]
    else:
        report = json.loads(args.search_report.read_text(encoding="utf-8"))
        names = report["budgets"][str(args.budget)]["features"]
    if len(names) != args.budget or len(set(names)) != args.budget or any(name not in FEATURE_NAMES for name in names):
        raise SystemExit(f"expected {args.budget} valid unique features, got {names}")
    selected = tuple(FEATURE_NAMES.index(name) for name in names)
    device = torch.device(args.device)
    result: dict[str, object] = {
        "budget": args.budget,
        "features": names,
        "device": str(device),
        "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "holdout": {},
    }

    for held_kind in ("glm_online", "skillsbench"):
        pool = np.flatnonzero(kinds != held_kind)
        train_local, val_local, _ = split_groups(labels[pool], groups[pool], args.seed)
        train_indices = pool[train_local]
        val_indices = pool[val_local]
        model, _, validation = train_one(
            features,
            labels,
            train_indices,
            val_indices,
            selected,
            device,
            args.seed + args.budget,
            epochs=args.epochs,
            patience=args.patience,
        )
        held_indices = np.flatnonzero(kinds == held_kind)
        wildchat_indices = val_indices[kinds[val_indices] == "wildchat"]
        test_indices = np.concatenate((held_indices, wildchat_indices))
        result["holdout"][held_kind] = {
            "train_records": int(len(train_indices)),
            "validation": validation,
            "held_source_records": int(len(held_indices)),
            "wildchat_records": int(len(wildchat_indices)),
            "test_records": int(len(test_indices)),
            "metrics": evaluate(
                model,
                features[train_indices],
                labels[train_indices],
                features[test_indices],
                labels[test_indices],
                selected,
                device,
            ),
        }

    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
