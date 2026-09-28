"""Request classification used by the first cache-region prototype.

The classifier is intentionally small and runs once in the tokenizer process.
The scheduler and cache only consume the resulting region label.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import torch
from torch import nn


class _RequestClassifierMLP(nn.Module):
    def __init__(self, n_in: int, hidden: Sequence[int], dropout: float) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        previous = n_in
        for width in hidden:
            layers.extend((nn.Linear(previous, int(width)), nn.ReLU(), nn.Dropout(dropout)))
            previous = int(width)
        layers.append(nn.Linear(previous, 1))
        self.network = nn.Sequential(*layers)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features).squeeze(-1)


def _content_chars(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, Mapping):
        if "__cache_char_count__" in value:
            return int(value["__cache_char_count__"])
        return sum(_content_chars(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return sum(_content_chars(item) for item in value)
    return len(str(value))


def _json_chars(value: Any) -> int:
    if not value:
        return 0
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except (TypeError, ValueError):
        return _content_chars(value)


def _log1p(value: int | float) -> float:
    return math.log1p(max(float(value), 0.0))


def extract_features(prompt_body: Mapping[str, Any] | None, max_tokens: int | float) -> dict[str, float]:
    """Extract the four system-independent production features."""
    body = prompt_body if isinstance(prompt_body, Mapping) else {}
    messages = body.get("messages") or []
    tools = body.get("tools") or []
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        messages = []
    if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
        tools = []

    tool_call_count = 0
    content_chars = 0
    has_tool_calls = False
    for message in messages:
        if not isinstance(message, Mapping):
            content_chars += _content_chars(message)
            continue
        content_chars += _content_chars(message.get("content"))
        tool_calls = message.get("tool_calls") or []
        if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes)):
            tool_call_count += len(tool_calls)
        elif tool_calls:
            tool_call_count += 1
        if tool_calls or message.get("function_call"):
            has_tool_calls = True

    return {
        "has_tools": float(bool(tools)),
        "log_tool_count": _log1p(len(tools)),
        "has_tool_calls": float(has_tool_calls),
        "log_content_chars": _log1p(content_chars),
        "log_tool_schema_chars": _log1p(_json_chars(tools)),
        "log_tool_call_count": _log1p(tool_call_count),
        "log_message_count": _log1p(len(messages)),
        "log_max_tokens": _log1p(max_tokens),
    }


class RequestRegionClassifier:
    """CPU inference wrapper for the request identity checkpoint."""

    def __init__(self, checkpoint: dict[str, Any], threshold: float | None = None) -> None:
        self.feature_names = tuple(checkpoint["feature_names"])
        supported = {
            "has_tools",
            "log_tool_count",
            "has_tool_calls",
            "log_content_chars",
            "log_tool_schema_chars",
            "log_tool_call_count",
            "log_message_count",
            "log_max_tokens",
        }
        unsupported = set(self.feature_names) - supported
        if unsupported:
            raise ValueError(
                "request classifier checkpoint uses unavailable online features: "
                + ", ".join(sorted(unsupported))
            )
        if int(checkpoint["n_in"]) != len(self.feature_names):
            raise ValueError("request classifier checkpoint feature count is inconsistent")
        self.mean = torch.tensor(checkpoint["x_mean"], dtype=torch.float32)
        self.std = torch.tensor(checkpoint["x_std"], dtype=torch.float32)
        self.std = torch.where(self.std.abs() < 1e-6, torch.ones_like(self.std), self.std)
        self.threshold = float(checkpoint.get("threshold", 0.5) if threshold is None else threshold)
        self.model = _RequestClassifierMLP(
            int(checkpoint["n_in"]),
            tuple(int(width) for width in checkpoint["hidden"]),
            float(checkpoint.get("dropout", 0.0)),
        )
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.eval()

    @classmethod
    def load(cls, path: str | Path, threshold: float | None = None) -> "RequestRegionClassifier":
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        return cls(checkpoint, threshold=threshold)

    @torch.inference_mode()
    def predict_proba(self, prompt_body: Mapping[str, Any] | None, max_tokens: int | float) -> float:
        values = extract_features(prompt_body, max_tokens)
        features = torch.tensor(
            [values.get(name, 0.0) for name in self.feature_names], dtype=torch.float32
        )
        probability = torch.sigmoid(self.model(((features - self.mean) / self.std).unsqueeze(0)))
        return float(probability.item())

    def classify(self, prompt_body: Mapping[str, Any] | None, max_tokens: int | float) -> str:
        return "agent" if self.predict_proba(prompt_body, max_tokens) >= self.threshold else "request"
