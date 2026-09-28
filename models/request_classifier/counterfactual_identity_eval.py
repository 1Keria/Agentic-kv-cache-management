#!/usr/bin/env python3
"""Stress-test identity checkpoints under system-message counterfactuals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from model import RequestClassifierMLP


def predict(model: RequestClassifierMLP, features: np.ndarray, indices: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    outputs: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(features), 8192):
            batch = (features[start : start + 8192][:, indices] - mean) / std
            outputs.append(torch.sigmoid(model(torch.from_numpy(batch))).numpy())
    return np.concatenate(outputs) if outputs else np.empty(0, dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--neutral-system-chars", type=int, default=32)
    args = parser.parse_args()

    data = np.load(args.cache, allow_pickle=True)
    all_features = data["features"].astype(np.float32)
    labels = data["labels"].astype(np.int8)
    feature_names = data["feature_names"].tolist()
    system_index = feature_names.index("n_system_messages")
    system_chars_index = feature_names.index("log_system_chars")
    message_index = feature_names.index("log_message_count")
    content_index = feature_names.index("log_content_chars")
    ordinary = all_features[labels == 0].copy()
    agents = all_features[labels == 1].copy()

    ordinary_counterfactual = ordinary.copy()
    ordinary_counterfactual[:, system_index] = 1.0
    ordinary_counterfactual[:, system_chars_index] = np.log1p(args.neutral_system_chars)
    ordinary_counterfactual[:, message_index] = np.log1p(np.expm1(ordinary_counterfactual[:, message_index]) + 1.0)
    ordinary_counterfactual[:, content_index] = np.log1p(
        np.expm1(ordinary_counterfactual[:, content_index]) + args.neutral_system_chars
    )

    agent_counterfactual = agents.copy()
    original_system_count = agent_counterfactual[:, system_index].copy()
    original_system_chars = np.expm1(agent_counterfactual[:, system_chars_index])
    agent_counterfactual[:, system_index] = 0.0
    agent_counterfactual[:, system_chars_index] = 0.0
    agent_counterfactual[:, message_index] = np.log1p(
        np.maximum(np.expm1(agent_counterfactual[:, message_index]) - original_system_count, 0.0)
    )
    agent_counterfactual[:, content_index] = np.log1p(
        np.maximum(np.expm1(agent_counterfactual[:, content_index]) - original_system_chars, 0.0)
    )

    result: dict[str, object] = {
        "protocol": {
            "ordinary_counterfactual": "add one neutral system message",
            "agent_counterfactual": "remove all system messages",
            "neutral_system_chars": args.neutral_system_chars,
            "note": "Counterfactuals keep the original identity labels and diagnose reliance on system-template signals.",
        },
        "budgets": {},
    }
    for budget in (1, 2, 4, 8, 12, 16):
        checkpoint = torch.load(
            args.checkpoint_dir / f"budget_{budget}" / "request_classifier.pt",
            map_location="cpu",
            weights_only=False,
        )
        model = RequestClassifierMLP(
            int(checkpoint["n_in"]),
            hidden=tuple(checkpoint["hidden"]),
            dropout=float(checkpoint["dropout"]),
        )
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        indices = np.asarray([feature_names.index(name) for name in checkpoint["feature_names"]])
        mean = np.asarray(checkpoint["x_mean"], dtype=np.float32)
        std = np.asarray(checkpoint["x_std"], dtype=np.float32)
        ordinary_original = predict(model, ordinary, indices, mean, std)
        ordinary_changed = predict(model, ordinary_counterfactual, indices, mean, std)
        agent_changed = predict(model, agent_counterfactual, indices, mean, std)
        result["budgets"][str(budget)] = {
            "features": checkpoint["feature_names"],
            "ordinary_original_agent_rate": float(np.mean(ordinary_original >= 0.5)),
            "ordinary_add_system_false_agent_rate": float(np.mean(ordinary_changed >= 0.5)),
            "agent_remove_system_missed_rate": float(np.mean(agent_changed < 0.5)),
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[write] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
