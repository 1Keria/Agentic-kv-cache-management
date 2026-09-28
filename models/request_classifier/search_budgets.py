#!/usr/bin/env python3
"""Search request-classifier feature sets on de-duplicated source groups.

The workload directory contains many derived copies of the same source rows.  This
script builds a source-aware cache, performs grouped train/validation/test splits,
selects nested feature sets without looking at the final test split, and evaluates
the selected models on both the grouped test split and feasible cross-source tests.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from features import FEATURE_NAMES, extract_features
from labels import is_agent_like_row
from model import RequestClassifierMLP
from train import _row_key, _source_group, metrics, predict


def load_cache(paths: list[Path], cache_path: Path) -> dict[str, np.ndarray]:
    if cache_path.exists():
        data = np.load(cache_path, allow_pickle=True)
        return {key: data[key] for key in data.files}
    seen: set[tuple[str, str]] = set()
    features: list[np.ndarray] = []
    labels: list[int] = []
    kinds: list[str] = []
    groups: list[str] = []
    raw_records = 0
    for path in sorted(paths):
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                raw_records += 1
                row = json.loads(line)
                source = row.get("source") or {}
                traffic_class = str(row.get("traffic_class") or "")
                raw_session = str(row.get("session_id") or f"{path}:{line_number}")
                group = _source_group(row, raw_session)
                key = _row_key(row, group, path, line_number)
                if key in seen:
                    continue
                seen.add(key)
                features.append(extract_features(row.get("prompt_body"), row.get("max_tokens", 0)))
                labels.append(int(is_agent_like_row(row)))
                kinds.append(str(source.get("kind") or traffic_class))
                groups.append(group)
    if not features:
        raise SystemExit("no workload records found")
    data = {
        "features": np.asarray(features, dtype=np.float32),
        "labels": np.asarray(labels, dtype=np.int8),
        "kinds": np.asarray(kinds),
        "groups": np.asarray(groups),
        "feature_names": np.asarray(FEATURE_NAMES),
        "raw_records": np.asarray([raw_records], dtype=np.int64),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_path, **data)
    return data


def split_groups(
    labels: np.ndarray,
    groups: np.ndarray,
    seed: int,
    val_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    group_labels: dict[str, int] = {}
    members: dict[str, list[int]] = defaultdict(list)
    for index, group in enumerate(groups.tolist()):
        group = str(group)
        label = int(labels[index])
        if group in group_labels and group_labels[group] != label:
            raise ValueError(f"mixed labels in source group {group}")
        group_labels[group] = label
        members[group].append(index)
    rng = random.Random(seed)
    train_groups: set[str] = set()
    val_groups: set[str] = set()
    test_groups: set[str] = set()
    for label in (0, 1):
        candidates = [group for group, value in group_labels.items() if value == label]
        rng.shuffle(candidates)
        n_test = max(1, int(round(len(candidates) * test_fraction)))
        n_val = max(1, int(round(len(candidates) * val_fraction)))
        n_test = min(n_test, max(len(candidates) - 2, 0))
        n_val = min(n_val, max(len(candidates) - n_test - 1, 0))
        test_groups.update(candidates[:n_test])
        val_groups.update(candidates[n_test : n_test + n_val])
        train_groups.update(candidates[n_test + n_val :])
    choose = lambda selected: np.asarray(
        [index for group in selected for index in members[group]], dtype=np.int64
    )
    return choose(train_groups), choose(val_groups), choose(test_groups)


def standardize(train: np.ndarray, *others: np.ndarray) -> tuple[np.ndarray, ...]:
    mean = train.mean(axis=0).astype(np.float32)
    std = train.std(axis=0).astype(np.float32)
    std = np.where(std < 1e-6, 1.0, std).astype(np.float32)
    return tuple((array - mean) / std for array in (train, *others))


def train_one(
    features: np.ndarray,
    labels: np.ndarray,
    train_indices: np.ndarray,
    val_indices: np.ndarray,
    selected: tuple[int, ...],
    device: torch.device,
    seed: int,
    epochs: int = 35,
    patience: int = 6,
) -> tuple[RequestClassifierMLP, np.ndarray, dict[str, Any]]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    x_train = features[train_indices][:, selected].astype(np.float32)
    x_val = features[val_indices][:, selected].astype(np.float32)
    x_train, x_val = standardize(x_train, x_val)
    y_train = labels[train_indices].astype(np.float32)
    y_val = labels[val_indices].astype(np.float32)
    model = RequestClassifierMLP(len(selected), hidden=(32, 16), dropout=0.05).to(device)
    n_positive = max(float(y_train.sum()), 1.0)
    n_negative = max(float(len(y_train) - y_train.sum()), 1.0)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(n_negative / n_positive, device=device))
    optimizer = torch.optim.Adam(model.parameters(), lr=2e-3, weight_decay=1e-4)
    x_tensor = torch.from_numpy(x_train)
    y_tensor = torch.from_numpy(y_train)
    best_state: dict[str, torch.Tensor] | None = None
    best_loss = float("inf")
    stale = 0
    best_epoch = 0
    for epoch in range(1, epochs + 1):
        model.train()
        permutation = torch.randperm(len(y_tensor))
        for start in range(0, len(y_tensor), 4096):
            batch = permutation[start : start + 4096]
            xb = x_tensor[batch].to(device)
            yb = y_tensor[batch].to(device)
            loss = loss_fn(model(xb), yb)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        probabilities = predict(model, x_val, device, 4096)
        current = metrics(y_val, probabilities, 0.5)
        if current["log_loss"] < best_loss:
            best_loss = float(current["log_loss"])
            best_state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
            best_epoch = epoch
            stale = 0
        else:
            stale += 1
        if stale >= patience:
            break
    if best_state is not None:
        model.load_state_dict(best_state)
    probabilities = predict(model, x_val, device, 4096)
    result = metrics(y_val, probabilities, 0.5)
    result["score"] = 0.5 * (result["accuracy"] + result["recall_agent"])
    result["best_epoch"] = best_epoch
    return model, probabilities, result


def evaluate(
    model: RequestClassifierMLP,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    test_features: np.ndarray,
    test_labels: np.ndarray,
    selected: tuple[int, ...],
    device: torch.device,
) -> dict[str, Any]:
    x_train = train_features[:, selected].astype(np.float32)
    x_test = test_features[:, selected].astype(np.float32)
    x_train, x_test = standardize(x_train, x_test)
    probabilities = predict(model, x_test, device, 4096)
    return metrics(test_labels.astype(np.float32), probabilities, 0.5)


def make_candidates(previous: list[tuple[int, ...]], target: int, all_features: int, limit: int = 160) -> list[tuple[int, ...]]:
    candidates: set[tuple[int, ...]] = set()
    for base in previous:
        remaining = [index for index in range(all_features) if index not in base]
        add_count = target - len(base)
        if add_count <= 2:
            additions = itertools.combinations(remaining, add_count)
        else:
            # Exhaustive combinations become large at 8/12 dimensions.  Keep
            # deterministic random extensions from each top validation beam.
            local_rng = random.Random(hash(base) ^ target ^ all_features)
            sampled: set[tuple[int, ...]] = set()
            for _ in range(64):
                sampled.add(tuple(sorted(local_rng.sample(remaining, add_count))))
            additions = sampled
        for addition in additions:
            candidate = tuple(sorted(base + tuple(addition)))
            if len(candidate) == target:
                candidates.add(candidate)
    if len(candidates) > limit:
        ranked = sorted(candidates, key=lambda item: hashlib.sha1(str(item).encode()).hexdigest())
        candidates = set(ranked[:limit])
    return sorted(candidates)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload-root", type=Path, default=Path("workloads"))
    parser.add_argument("--cache", type=Path, default=Path("models/request_classifier/cache/raw_source_unique_corrected.npz"))
    parser.add_argument("--out", type=Path, default=Path("models/request_classifier/checkpoints/feature_budget_search.json"))
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("models/request_classifier/checkpoints/search"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--budgets", default="1,2,4,8,12,16", help="Comma-separated budgets to search")
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--candidate-limit", type=int, default=64)
    args = parser.parse_args()
    torch.set_num_threads(max(1, int(os.environ.get("REQUEST_CLASSIFIER_TORCH_THREADS", "4"))))
    requested_budgets = tuple(int(value.strip()) for value in args.budgets.split(",") if value.strip())
    if not requested_budgets or any(value not in (1, 2, 4, 8, 12, 16) for value in requested_budgets):
        raise SystemExit("--budgets must contain values from 1,2,4,8,12,16")
    device = torch.device(args.device)
    data = load_cache(list(args.workload_root.rglob("workload.jsonl")), args.cache)
    x = data["features"]
    y = data["labels"].astype(np.float32)
    groups = data["groups"]
    kinds = data["kinds"]
    train_indices, val_indices, test_indices = split_groups(y, groups, args.seed)
    print(json.dumps({
        "records": len(y),
        "raw_records": int(data.get("raw_records", [0])[0]),
        "groups": len(set(groups.tolist())),
        "kinds": Counter(kinds.tolist()),
        "train": len(train_indices), "validation": len(val_indices), "test": len(test_indices),
        "device": str(device), "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
    }, default=dict), flush=True)

    by_budget: dict[str, Any] = {}
    beam: list[tuple[int, ...]] = []
    for budget in requested_budgets:
        if budget == 1:
            candidates = [tuple([index]) for index in range(len(FEATURE_NAMES))]
        elif budget == 2:
            candidates = list(itertools.combinations(range(len(FEATURE_NAMES)), 2))
        elif budget == 16:
            candidates = [tuple(range(len(FEATURE_NAMES)))]
        elif not beam:
            all_combinations = list(itertools.combinations(range(len(FEATURE_NAMES)), budget))
            rng = random.Random(args.seed + budget)
            limit = max(args.candidate_limit - 1, 1)
            if len(all_combinations) > limit:
                candidates = rng.sample(all_combinations, limit)
            else:
                candidates = all_combinations
            canonical = tuple(FEATURE_NAMES.index(name) for name in {
                4: ("has_tools", "log_message_count", "n_system_messages", "n_tool_messages"),
                8: ("has_tools", "log_tool_count", "log_tool_schema_chars", "log_message_count", "n_system_messages", "n_tool_messages", "log_tool_call_count", "log_content_chars"),
                12: ("has_tools", "log_tool_count", "log_tool_schema_chars", "log_message_count", "n_system_messages", "n_tool_messages", "log_tool_call_count", "log_content_chars", "has_tool_calls", "log_system_chars", "log_tool_message_chars", "log_max_tokens"),
            }[budget])
            if canonical not in candidates:
                candidates.append(canonical)
        else:
            candidates = make_candidates(beam[:12], budget, len(FEATURE_NAMES), limit=192)
        scored: list[tuple[float, tuple[int, ...], dict[str, Any], RequestClassifierMLP]] = []
        for number, selected in enumerate(candidates, 1):
            model, _, validation = train_one(
                x, y, train_indices, val_indices, selected, device, args.seed + number,
                epochs=args.epochs, patience=args.patience
            )
            scored.append((float(validation["score"]), selected, validation, model))
            if number % 32 == 0 or number == len(candidates):
                print(f"budget={budget} candidate={number}/{len(candidates)}", flush=True)
        scored.sort(key=lambda item: (item[0], item[2]["recall_agent"], item[2]["accuracy"], -item[2]["log_loss"]), reverse=True)
        best_score, best_selected, best_validation, best_model = scored[0]
        beam = [item[1] for item in scored[:12]]
        test_metrics = evaluate(best_model, x[train_indices], y[train_indices], x[test_indices], y[test_indices], best_selected, device)
        source_metrics: dict[str, Any] = {}
        for kind in sorted(set(kinds.tolist())):
            held_out = np.flatnonzero(kinds == kind)
            source_metrics[kind] = {
                "records": int(len(held_out)),
                "groups": int(len(set(groups[held_out].tolist()))),
                "note": "test-only source evaluation uses the all-source model; it is not feature-selection data",
                "metrics": evaluate(best_model, x[train_indices], y[train_indices], x[held_out], y[held_out], best_selected, device),
            }
        names = [FEATURE_NAMES[index] for index in best_selected]
        checkpoint = {
            "state_dict": best_model.cpu().state_dict(),
            "n_in": len(best_selected), "hidden": [32, 16], "dropout": 0.05,
            "feature_budget": budget, "feature_names": names,
            "x_mean": x[train_indices][:, best_selected].mean(axis=0).tolist(),
            "x_std": np.where(x[train_indices][:, best_selected].std(axis=0) < 1e-6, 1.0, x[train_indices][:, best_selected].std(axis=0)).tolist(),
            "threshold": 0.5, "seed": args.seed, "device": str(device),
        }
        args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        torch.save(checkpoint, args.checkpoint_dir / f"budget_{budget}.pt")
        by_budget[str(budget)] = {
            "features": names, "validation": best_validation, "grouped_test": test_metrics,
            "source_holdout": source_metrics, "candidates_evaluated": len(candidates),
            "top_validation": [
                {"features": [FEATURE_NAMES[index] for index in item[1]], "validation": item[2]}
                for item in scored[:5]
            ],
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "protocol": {
            "cache": str(args.cache), "deduplication": "source identity + call/turn position + max_tokens + prompt_body",
            "split": "stratified source-group 60/20/20, seed=42", "feature_selection": "nested beam search on validation only",
            "sources": {kind: {"records": int(np.sum(kinds == kind)), "groups": len(set(groups[kinds == kind].tolist()))} for kind in sorted(set(kinds.tolist()))},
            "device": str(device), "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        },
        "budgets": by_budget,
        "recommendation": "Prefer the smallest budget whose grouped and source-holdout metrics remain stable; retain the full model only when its extra signals are needed.",
    }
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[write] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
