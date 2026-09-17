#!/usr/bin/env python3
"""Freeze K8 serving tensors: scaler, edges, finished_reason map, official τ̂ recipe."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
from pipeline_inventory_groups import load_xy  # noqa: E402
from rank_inventory_permutation import (  # noqa: E402
    SPECS,
    extract_row,
    load_dump_map,
)
from rank_session_return_features import DEFAULT_RUN, load_client  # noqa: E402
from train_session_return_k8_censor import K8  # noqa: E402

KIND = {s[0]: s[3] for s in SPECS}


def main() -> None:
    ckpt_path = REPO_ROOT / "experiments/session_return/k8_model/k8_hazard.pt"
    out_path = REPO_ROOT / "experiments/session_return/k8_model/k8_serving.json"
    dump_file = "server_dump/native_pid1681410.jsonl"
    names, Xall, _y, _d, sm = load_xy(DEFAULT_RUN, dump_file)
    keep = np.array([names.index(n) for n in K8], dtype=int)
    X = Xall[:, keep]
    tr = sm["train"]
    finite = np.isfinite(X[tr])
    mean = np.where(finite.any(0), np.nanmean(np.where(finite, X[tr], np.nan), axis=0), 0.0)
    std = np.where(finite.any(0), np.nanstd(np.where(finite, X[tr], np.nan), axis=0), 1.0)
    std = np.where(std < 1e-8, 1.0, std)

    clients = load_client(DEFAULT_RUN / "client" / "small_2200.client.jsonl")
    dump = load_dump_map(DEFAULT_RUN / dump_file)
    ids = sorted(
        rid for rid, rec in clients.items() if rid in dump and rec.get("small_split")
    )
    raw = [extract_row(clients[rid], dump[rid]) for rid in ids]
    splits = [clients[rid]["small_split"] for rid in ids]
    train_idx = [i for i, s in enumerate(splits) if s == "train"]
    mapping: dict[str, float] = {}
    next_id = 0
    for i in train_idx:
        v = raw[i].get("req.finished_reason")
        if isinstance(v, str) and v not in mapping:
            mapping[v] = float(next_id)
            next_id += 1

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    spec = {
        "official_output": "restricted_mean_E[min(tau,60)]",
        "evict_rule": "larger tau_hat first; missing tau_hat falls back to LRU",
        "features": K8,
        "mean": [float(x) for x in mean],
        "std": [float(x) for x in std],
        "edges": [float(x) for x in np.asarray(ckpt.get("edges"))],
        "horizon_s": 60.0,
        "finished_reason_map": mapping,
        "ckpt": str(ckpt_path),
        "kinds": {n: KIND[n] for n in K8},
    }
    ckpt["official_output"] = spec["official_output"]
    ckpt["finished_reason_map"] = mapping
    ckpt["mean"] = mean
    ckpt["std"] = std
    torch.save(ckpt, ckpt_path)
    out_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    print("wrote", out_path)
    print("finished_reason_map", mapping)


if __name__ == "__main__":
    main()
