"""Dependency-light online inference wrapper for the request classifier."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch

try:
    from .features import extract_features
    from .features import FEATURE_NAMES
    from .model import RequestClassifierMLP
except ImportError:  # Support ``python infer.py`` during local debugging.
    from features import extract_features
    from features import FEATURE_NAMES
    from model import RequestClassifierMLP


class RequestClassifier:
    """Load a checkpoint and classify one OpenAI-compatible request."""

    def __init__(self, checkpoint: dict[str, Any], device: str | torch.device = "cpu") -> None:
        self.device = torch.device(device)
        self.feature_names = tuple(checkpoint["feature_names"])
        self.feature_indices = tuple(FEATURE_NAMES.index(name) for name in self.feature_names)
        self.mean = np.asarray(checkpoint["x_mean"], dtype=np.float32)
        self.std = np.asarray(checkpoint["x_std"], dtype=np.float32)
        self.threshold = float(checkpoint.get("threshold", 0.5))
        self.model = RequestClassifierMLP(
            n_in=int(checkpoint["n_in"]),
            hidden=tuple(int(width) for width in checkpoint["hidden"]),
            dropout=float(checkpoint.get("dropout", 0.0)),
        )
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.to(self.device).eval()

    @classmethod
    def load(cls, path: str | Path, device: str | torch.device = "cpu") -> "RequestClassifier":
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        return cls(checkpoint, device=device)

    @torch.inference_mode()
    def predict_proba(self, prompt_body: dict[str, Any], max_tokens: int | float) -> float:
        features = extract_features(prompt_body, max_tokens)
        features = features[list(self.feature_indices)]
        standardized = (features - self.mean) / self.std
        tensor = torch.from_numpy(standardized).to(self.device).unsqueeze(0)
        return float(torch.sigmoid(self.model(tensor))[0].item())

    def classify(
        self,
        prompt_body: dict[str, Any],
        max_tokens: int | float,
        threshold: float | None = None,
    ) -> str:
        probability = self.predict_proba(prompt_body, max_tokens)
        cutoff = self.threshold if threshold is None else float(threshold)
        return "agent_like" if probability >= cutoff else "request"
