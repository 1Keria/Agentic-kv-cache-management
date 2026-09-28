#!/usr/bin/env python3
"""Train a request-level Agent-like versus Request classifier.

The input is one or more workload.jsonl files. Splits are made by source group,
not by individual turns, so a multi-turn trajectory or a derived workload cannot
leak across splits.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import FEATURE_BUDGETS, FEATURE_GROUPS, FEATURE_NAMES, extract_features
from labels import is_agent_like_row, label_name
from model import RequestClassifierMLP


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def expand_paths(paths: Iterable[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            candidate = path / "workload.jsonl"
            if candidate.exists():
                expanded.append(candidate)
            else:
                nested = sorted(path.rglob("workload.jsonl"))
                if not nested:
                    raise SystemExit(f"directory has no workload.jsonl: {path}")
                expanded.extend(nested)
        else:
            expanded.append(path)
    missing = [path for path in expanded if not path.exists()]
    if missing:
        raise SystemExit("missing input: " + ", ".join(str(path) for path in missing))
    return expanded


def _source_group(row: dict[str, Any], session_id: str) -> str:
    source = row.get("source") or {}
    label_family = label_name(row)
    # GLM trace_id identifies one request.  The workload builder preserves the
    # inferred session_id, which is the stable unit needed to keep multi-turn
    # GLM conversations in one split.
    if source.get("kind") == "glm_online" and session_id:
        return f"{label_family}:session:{session_id}"
    if source.get("kind") == "skillsbench" and source.get("path"):
        return f"{label_family}:path:{source['path']}"
    if source.get("kind") == "wildchat" and source.get("conversation_hash"):
        return f"{label_family}:conversation:{source['conversation_hash']}"
    for field in ("content_sha256", "conversation_hash", "trace_id", "path"):
        value = source.get(field)
        if value:
            return f"{label_family}:{field}:{value}"
    return f"{label_family}:session:{session_id}"


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open(encoding="utf-8")


def _row_key(row: dict[str, Any], session_id: str, path: Path, line_number: int) -> tuple[str, str]:
    source = row.get("source") or {}
    position = source.get("call_idx")
    if position is None:
        position = source.get("turn_identifier")
    if position is None:
        position = row.get("turn_idx")
    body = json.dumps(row.get("prompt_body") or {}, sort_keys=True, ensure_ascii=False)
    payload = f"{session_id}\0{position}\0{row.get('max_tokens', 0)}\0{body}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return session_id, digest


def load_records(paths: Iterable[Path], agent_labels: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in expand_paths(paths):
        with open_text(path) as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                raw_session_id = str(row.get("session_id") or f"{path}:{line_number}")
                session_id = _source_group(row, raw_session_id)
                key = _row_key(row, session_id, path, line_number)
                if key in seen:
                    continue
                seen.add(key)
                traffic_class = str(row.get("traffic_class") or "")
                records.append(
                    {
                        "session_id": session_id,
                        "label": int(
                            is_agent_like_row(row)
                            if traffic_class == "glm"
                            else traffic_class in agent_labels
                        ),
                        "traffic_class": traffic_class,
                        "features": extract_features(row.get("prompt_body"), row.get("max_tokens", 0)),
                    }
                )
    if not records:
        raise SystemExit("no records loaded")
    return records


def split_by_source_group(
    records: list[dict[str, Any]],
    seed: int,
    val_fraction: float,
    test_fraction: float,
) -> tuple[list[int], list[int], list[int]]:
    if val_fraction < 0 or test_fraction < 0 or val_fraction + test_fraction >= 1:
        raise SystemExit("validation and test fractions must sum to less than 1")
    groups: dict[str, list[int]] = defaultdict(list)
    labels: dict[str, int] = {}
    for index, record in enumerate(records):
        session_id = record["session_id"]
        label = int(record["label"])
        if session_id in labels and labels[session_id] != label:
            raise SystemExit(f"session has conflicting labels: {session_id}")
        labels[session_id] = label
        groups[session_id].append(index)

    rng = random.Random(seed)
    train_groups: set[str] = set()
    val_groups: set[str] = set()
    test_groups: set[str] = set()
    for label in (0, 1):
        class_groups = [session_id for session_id, group_label in labels.items() if group_label == label]
        rng.shuffle(class_groups)
        n_groups = len(class_groups)
        n_test = int(round(n_groups * test_fraction))
        n_val = int(round(n_groups * val_fraction))
        if n_groups >= 3:
            n_test = max(1 if test_fraction else 0, min(n_test, n_groups - 2))
            n_val = max(1 if val_fraction else 0, min(n_val, n_groups - n_test - 1))
        test_groups.update(class_groups[:n_test])
        val_groups.update(class_groups[n_test : n_test + n_val])
        train_groups.update(class_groups[n_test + n_val :])

    train_indices = [index for index, record in enumerate(records) if record["session_id"] in train_groups]
    val_indices = [index for index, record in enumerate(records) if record["session_id"] in val_groups]
    test_indices = [index for index, record in enumerate(records) if record["session_id"] in test_groups]
    return train_indices, val_indices, test_indices


def standardize_fit(features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = features.mean(axis=0).astype(np.float32)
    std = features.std(axis=0).astype(np.float32)
    std = np.where(std < 1e-6, 1.0, std).astype(np.float32)
    return mean, std


def arrays(records: list[dict[str, Any]], indices: list[int]) -> tuple[np.ndarray, np.ndarray]:
    features = np.asarray([records[index]["features"] for index in indices], dtype=np.float32)
    labels = np.asarray([records[index]["label"] for index in indices], dtype=np.float32)
    return features, labels


def roc_auc(labels: np.ndarray, probabilities: np.ndarray) -> float | None:
    positives = labels == 1
    negatives = labels == 0
    n_positive = int(positives.sum())
    n_negative = int(negatives.sum())
    if n_positive == 0 or n_negative == 0:
        return None
    order = np.argsort(probabilities, kind="mergesort")
    ranks = np.empty(len(probabilities), dtype=np.float64)
    sorted_probabilities = probabilities[order]
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and sorted_probabilities[end] == sorted_probabilities[start]:
            end += 1
        ranks[order[start:end]] = (start + end + 1) / 2.0
        start = end
    positive_rank_sum = ranks[positives].sum()
    return float((positive_rank_sum - n_positive * (n_positive + 1) / 2) / (n_positive * n_negative))


def average_precision(labels: np.ndarray, probabilities: np.ndarray) -> float | None:
    n_positive = int((labels == 1).sum())
    if n_positive == 0:
        return None
    order = np.argsort(-probabilities, kind="mergesort")
    sorted_labels = labels[order]
    cumulative = np.cumsum(sorted_labels)
    positions = np.arange(1, len(labels) + 1)
    return float((cumulative / positions * sorted_labels).sum() / n_positive)


def log_loss(labels: np.ndarray, probabilities: np.ndarray) -> float:
    clipped = np.clip(probabilities, 1e-7, 1.0 - 1e-7)
    return float(-np.mean(labels * np.log(clipped) + (1.0 - labels) * np.log1p(-clipped)))


def metrics(labels: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict[str, Any]:
    predictions = probabilities >= threshold
    true_positive = int(np.sum(predictions & (labels == 1)))
    false_positive = int(np.sum(predictions & (labels == 0)))
    false_negative = int(np.sum(~predictions & (labels == 1)))
    true_negative = int(np.sum(~predictions & (labels == 0)))
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    accuracy = (true_positive + true_negative) / max(len(labels), 1)
    return {
        "n": int(len(labels)),
        "positive_rate": float(np.mean(labels)) if len(labels) else 0.0,
        "threshold": float(threshold),
        "accuracy": float(accuracy),
        "precision_agent": float(precision),
        "recall_agent": float(recall),
        "f1_agent": float(2 * precision * recall / max(precision + recall, 1e-12)),
        "roc_auc": roc_auc(labels, probabilities),
        "average_precision": average_precision(labels, probabilities),
        "log_loss": log_loss(labels, probabilities),
        "brier": float(np.mean((probabilities - labels) ** 2)),
        "confusion": {
            "true_agent": true_positive,
            "false_agent": false_positive,
            "missed_agent": false_negative,
            "true_request": true_negative,
        },
    }


@torch.no_grad()
def predict(model: RequestClassifierMLP, features: np.ndarray, device: torch.device, batch_size: int) -> np.ndarray:
    model.eval()
    outputs: list[np.ndarray] = []
    tensor = torch.from_numpy(features)
    for start in range(0, len(features), batch_size):
        batch = tensor[start : start + batch_size].to(device)
        outputs.append(torch.sigmoid(model(batch)).cpu().numpy())
    return np.concatenate(outputs) if outputs else np.empty(0, dtype=np.float32)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-path", nargs="+", type=Path, required=True)
    parser.add_argument("--test-path", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("models/request_classifier/checkpoints"))
    parser.add_argument("--agent-labels", default="agent,openhands,glm")
    parser.add_argument("--feature-budget", type=int, choices=sorted(FEATURE_BUDGETS))
    parser.add_argument("--feature-names", help="Comma-separated feature names; overrides --feature-budget")
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--hidden", default="64,32")
    parser.add_argument("--dropout", type=float, default=0.05)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    set_seed(args.seed)
    agent_labels = {label.strip() for label in args.agent_labels.split(",") if label.strip()}
    hidden = tuple(int(width) for width in args.hidden.split(",") if width.strip())
    if not hidden:
        raise SystemExit("--hidden must contain at least one width")
    device = torch.device(args.device)
    if args.feature_budget is not None and args.feature_names:
        raise SystemExit("use only one of --feature-budget and --feature-names")
    if args.feature_names:
        selected_feature_names = tuple(name.strip() for name in args.feature_names.split(",") if name.strip())
    elif args.feature_budget is not None:
        selected_feature_names = tuple(FEATURE_BUDGETS[args.feature_budget])
    else:
        selected_feature_names = tuple(FEATURE_NAMES)
    unknown_features = set(selected_feature_names) - set(FEATURE_NAMES)
    if unknown_features or len(set(selected_feature_names)) != len(selected_feature_names):
        raise SystemExit(f"invalid or duplicate feature names: {sorted(unknown_features)}")
    feature_indices = np.asarray([FEATURE_NAMES.index(name) for name in selected_feature_names], dtype=np.int64)
    records = load_records(args.train_path, agent_labels)
    train_indices, val_indices, internal_test_indices = split_by_source_group(
        records, args.seed, args.val_fraction, 0.0 if args.test_path else args.test_fraction
    )
    train_features, train_labels = arrays(records, train_indices)
    val_features, val_labels = arrays(records, val_indices)
    if args.test_path:
        external_records = load_records(args.test_path, agent_labels)
        external_features, external_labels = arrays(external_records, list(range(len(external_records))))
    else:
        external_records = None
        external_features, external_labels = arrays(records, internal_test_indices)
    train_features = train_features[:, feature_indices]
    val_features = val_features[:, feature_indices]
    external_features = external_features[:, feature_indices]
    mean, std = standardize_fit(train_features)
    train_features = (train_features - mean) / std
    val_features = (val_features - mean) / std
    external_features = (external_features - mean) / std

    model = RequestClassifierMLP(len(selected_feature_names), hidden=hidden, dropout=args.dropout).to(device)
    n_positive = max(float(train_labels.sum()), 1.0)
    n_negative = max(float(len(train_labels) - train_labels.sum()), 1.0)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(n_negative / n_positive, device=device))
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(train_features), torch.from_numpy(train_labels)),
        batch_size=args.batch_size,
        shuffle=True,
    )

    best_log_loss = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    best_epoch = 0
    stale_epochs = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        n_seen = 0
        for batch_features, batch_labels in train_loader:
            batch_features = batch_features.to(device)
            batch_labels = batch_labels.to(device)
            loss = loss_fn(model(batch_features), batch_labels)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            batch_size = len(batch_labels)
            total_loss += float(loss.item()) * batch_size
            n_seen += batch_size
        val_probabilities = predict(model, val_features, device, args.batch_size)
        val_metrics = metrics(val_labels, val_probabilities, args.threshold)
        history.append({"epoch": epoch, "train_loss": total_loss / max(n_seen, 1), "val": val_metrics})
        val_log_loss = float(val_metrics["log_loss"])
        if val_log_loss < best_log_loss:
            best_log_loss = val_log_loss
            best_state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
            best_epoch = epoch
            stale_epochs = 0
        else:
            stale_epochs += 1
        if stale_epochs >= args.patience:
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    train_probabilities = predict(model, train_features, device, args.batch_size)
    val_probabilities = predict(model, val_features, device, args.batch_size)
    external_probabilities = predict(model, external_features, device, args.batch_size)
    report = {
        "device": str(device),
        "cuda_device_name": (
            torch.cuda.get_device_name(device) if device.type == "cuda" else None
        ),
        "agent_labels": sorted(agent_labels),
        "label_names": {"0": "request", "1": "agent_like"},
        "feature_budget": len(selected_feature_names),
        "feature_names": list(selected_feature_names),
        "feature_groups": {
            name: [feature for feature in features if feature in selected_feature_names]
            for name, features in FEATURE_GROUPS.items()
        },
        "train_records": len(train_indices),
        "validation_records": len(val_indices),
        "test_records": len(external_features),
        "train_sessions": len({records[index]["session_id"] for index in train_indices}),
        "validation_sessions": len({records[index]["session_id"] for index in val_indices}),
        "test_sessions": (
            len({record["session_id"] for record in external_records})
            if external_records is not None
            else len({records[index]["session_id"] for index in internal_test_indices})
        ),
        "best_epoch": best_epoch,
        "metrics": {
            "train": metrics(train_labels, train_probabilities, args.threshold),
            "validation": metrics(val_labels, val_probabilities, args.threshold),
            "test": metrics(external_labels, external_probabilities, args.threshold),
        },
        "history": history,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = args.out_dir / "request_classifier.pt"
    checkpoint = {
        "state_dict": model.cpu().state_dict(),
        "n_in": len(selected_feature_names),
        "hidden": list(hidden),
        "dropout": args.dropout,
        "feature_budget": len(selected_feature_names),
        "feature_names": list(selected_feature_names),
        "feature_groups": {
            name: [feature for feature in features if feature in selected_feature_names]
            for name, features in FEATURE_GROUPS.items()
        },
        "x_mean": mean.tolist(),
        "x_std": std.tolist(),
        "agent_labels": sorted(agent_labels),
        "threshold": args.threshold,
        "seed": args.seed,
        "best_epoch": best_epoch,
        "device": str(device),
        "cuda_device_name": (
            torch.cuda.get_device_name(device) if device.type == "cuda" else None
        ),
    }
    torch.save(checkpoint, checkpoint_path)
    report["checkpoint"] = str(checkpoint_path)
    (args.out_dir / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    print(f"[write] {checkpoint_path}")
    print(f"[write] {args.out_dir / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
