#!/usr/bin/env python3
"""Train and save the selected feature-budget checkpoints from the corrected cache."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

from features import FEATURE_NAMES
from model import RequestClassifierMLP
from search_budgets import evaluate, split_groups, train_one


SELECTED = {
    1: ("n_system_messages",),
    2: ("has_tools", "n_system_messages"),
    4: ("has_tools", "log_message_count", "n_system_messages", "n_tool_messages"),
    8: (
        "has_tools", "log_tool_count", "log_tool_schema_chars", "log_message_count",
        "n_system_messages", "n_tool_messages", "log_tool_call_count", "log_content_chars",
    ),
    12: (
        "has_tools", "log_tool_count", "log_tool_schema_chars", "log_message_count",
        "n_system_messages", "n_tool_messages", "log_tool_call_count", "log_content_chars",
        "has_tool_calls", "log_system_chars", "log_tool_message_chars", "log_max_tokens",
    ),
    16: FEATURE_NAMES,
}


def fit_full(features: np.ndarray, labels: np.ndarray, selected: tuple[int, ...], device: torch.device, seed: int, epochs: int = 30) -> tuple[RequestClassifierMLP, np.ndarray, np.ndarray]:
    torch.manual_seed(seed)
    x = features[:, selected].astype(np.float32)
    mean = x.mean(axis=0).astype(np.float32)
    std = x.std(axis=0).astype(np.float32)
    std = np.where(std < 1e-6, 1.0, std).astype(np.float32)
    x = (x - mean) / std
    y = labels.astype(np.float32)
    model = RequestClassifierMLP(len(selected), hidden=(32, 16), dropout=0.05).to(device)
    n_positive = max(float(y.sum()), 1.0)
    n_negative = max(float(len(y) - y.sum()), 1.0)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(n_negative / n_positive, device=device))
    optimizer = torch.optim.Adam(model.parameters(), lr=2e-3, weight_decay=1e-4)
    tx, ty = torch.from_numpy(x), torch.from_numpy(y)
    for _ in range(epochs):
        permutation = torch.randperm(len(ty))
        model.train()
        for start in range(0, len(ty), 4096):
            batch = permutation[start : start + 4096]
            xb, yb = tx[batch].to(device), ty[batch].to(device)
            loss = loss_fn(model(xb), yb)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
    return model, mean, std


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("models/request_classifier/checkpoints/final"))
    parser.add_argument(
        "--selection-dir",
        type=Path,
        help="Directory containing parallel_search_budget_<budget>.json files",
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--budgets", default="1,2,4,8,12,16", help="Comma-separated budgets to train")
    args = parser.parse_args()
    requested_budgets = tuple(int(value.strip()) for value in args.budgets.split(",") if value.strip())
    if not requested_budgets or any(value not in SELECTED for value in requested_budgets):
        raise SystemExit("--budgets must contain values from 1,2,4,8,12,16")
    selected_by_budget = dict(SELECTED)
    if args.selection_dir:
        for budget in requested_budgets:
            report_path = args.selection_dir / f"parallel_search_budget_{budget}.json"
            if not report_path.exists():
                raise SystemExit(f"missing selection report: {report_path}")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            names = tuple(report["budgets"][str(budget)]["features"])
            if len(names) != budget or len(set(names)) != budget or any(name not in FEATURE_NAMES for name in names):
                raise SystemExit(f"invalid selected features for budget {budget}: {names}")
            selected_by_budget[budget] = names
    data = np.load(args.cache, allow_pickle=True)
    x = data["features"]
    y = data["labels"].astype(np.float32)
    groups = data["groups"]
    kinds = data["kinds"]
    train_indices, val_indices, test_indices = split_groups(y, groups, args.seed)
    device = torch.device(args.device)
    summary: dict[str, object] = {
        "protocol": {
            "cache": str(args.cache), "split": "source-group stratified 60/20/20, seed=42",
            "records": int(len(y)), "groups": int(len(set(groups.tolist()))),
            "device": str(device), "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
            "selection_dir": str(args.selection_dir) if args.selection_dir else None,
        },
        "budgets": {},
    }
    for budget in requested_budgets:
        names = selected_by_budget[budget]
        selected = tuple(FEATURE_NAMES.index(name) for name in names)
        model, _, validation = train_one(x, y, train_indices, val_indices, selected, device, args.seed + budget)
        test_metrics = evaluate(model, x[train_indices], y[train_indices], x[test_indices], y[test_indices], selected, device)
        source_metrics = {}
        for kind in sorted(set(kinds.tolist())):
            indices = np.flatnonzero(kinds == kind)
            source_metrics[kind] = evaluate(model, x[train_indices], y[train_indices], x[indices], y[indices], selected, device)
        production, mean, std = fit_full(x, y, selected, device, args.seed + 100 + budget)
        target = args.out_dir / f"budget_{budget}"
        target.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "state_dict": production.cpu().state_dict(), "n_in": len(selected), "hidden": [32, 16], "dropout": 0.05,
            "feature_budget": budget, "feature_names": list(names), "x_mean": mean.tolist(), "x_std": std.tolist(),
            "agent_labels": ["agent", "glm", "openhands"], "threshold": 0.5, "seed": args.seed,
            "device": str(device), "cuda_device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        }
        checkpoint_path = target / "request_classifier.pt"
        torch.save(checkpoint, checkpoint_path)
        report = {
            "feature_budget": budget, "feature_names": list(names), "train_records": int(len(train_indices)),
            "validation_records": int(len(val_indices)), "test_records": int(len(test_indices)),
            "validation": validation, "grouped_test": test_metrics, "source_metrics": source_metrics,
            "checkpoint": str(checkpoint_path), "production_fit_records": int(len(y)),
        }
        (target / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary["budgets"][str(budget)] = report
        print(json.dumps({"budget": budget, "features": names, "test": test_metrics}, ensure_ascii=False), flush=True)
    return_code = args.out_dir / "final_budget_summary.json"
    return_code.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[write] {return_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
