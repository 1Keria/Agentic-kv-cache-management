#!/usr/bin/env python3
"""Evaluate completed standalone MLP checkpoints on the observed long-gap mode."""

import argparse
import json
from pathlib import Path

import numpy as np
import torch

import mlp_reuse_offline as exp


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()
    exp.EVAL_AGES = [600.0, 1800.0]
    exp.EVAL_HORIZONS = [600.0, 1800.0, 3600.0, 7200.0]
    z = np.load(args.data, allow_pickle=False)
    data = {name: z[name] for name in z.files}
    device = torch.device(args.device)
    output = []
    for bucket_dir in sorted(args.run_dir.glob("k*")):
        if bucket_dir.name == "k5":
            continue
        for seed_dir in sorted(bucket_dir.glob("seed_*")):
            rows = exp.evaluate_checkpoint(
                data, seed_dir / "initial.pt", seed_dir / "landmark.pt", device
            )
            output.append({"bucket": bucket_dir.name, "seed": seed_dir.name, "metrics": rows})
    path = args.run_dir / "long_horizon_results.json"
    path.write_text(json.dumps(output, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
