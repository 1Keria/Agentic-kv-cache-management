"""Small request-level classifier used before cache ownership accounting."""

from __future__ import annotations

from collections.abc import Sequence

import torch
from torch import nn


class RequestClassifierMLP(nn.Module):
    def __init__(
        self,
        n_in: int,
        hidden: Sequence[int] = (64, 32),
        dropout: float = 0.05,
    ) -> None:
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
