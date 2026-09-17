#!/usr/bin/env python3
"""Leave-one-group-out ablation for the observed-τ LightGBM.

ΔMAE = MAE(without G) − MAE(all), after retraining. Answers how much
absolute error grows if that information is never available. Diagnosis only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
from permute_session_return_lgbm import GROUPS, load_matrix  # noqa: E402
from rank_session_return_features import DEFAULT_RUN  # noqa: E402
from train_session_return_lgbm import fit_lgbm  # noqa: E402


def score(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "r2": float(r2_score(y, pred)),
    }


def eval_obs(model, splits: dict, cols: np.ndarray | slice) -> dict[str, dict]:
    out = {}
    for name, (X, y, d) in splits.items():
        obs = d == 1
        pred = model.predict(X[obs][:, cols])
        out[name] = score(y[obs], pred)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    p.add_argument("--dump-file", default="server_dump/native_pid1681410.jsonl")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "experiments/session_return/lgbm",
    )
    args = p.parse_args()

    names, splits = load_matrix(args.run_dir, args.dump_file)
    name_i = {n: i for i, n in enumerate(names)}
    Xtr, ytr, dtr = splits["train"]
    Xva, yva, dva = splits["val"]
    obs_tr, obs_va = dtr == 1, dva == 1

    full_cols = np.arange(len(names))
    full = fit_lgbm(Xtr[obs_tr], ytr[obs_tr], Xva[obs_va], yva[obs_va])
    full_metrics = eval_obs(full, splits, full_cols)
    mean_tr = float(np.mean(ytr[obs_tr]))
    baseline = {}
    for split, (_X, y, d) in splits.items():
        yo = y[d == 1]
        baseline[split] = score(yo, np.full_like(yo, mean_tr))

    resolved = []
    used = set(names)
    for gname, spec in GROUPS.items():
        feats = [f for f in spec["features"] if f in used]
        if feats:
            resolved.append((gname, feats, spec["why"]))

    rows = []
    for gname, feats, why in resolved:
        drop = {name_i[f] for f in feats}
        keep = np.array([j for j in full_cols if j not in drop], dtype=int)
        model = fit_lgbm(
            Xtr[obs_tr][:, keep],
            ytr[obs_tr],
            Xva[obs_va][:, keep],
            yva[obs_va],
        )
        metrics = eval_obs(model, splits, keep)
        row = {
            "group": gname,
            "dropped": feats,
            "n_kept": int(len(keep)),
            "why": why,
            "best_iteration": int(model.best_iteration_ or model.n_estimators),
            "metrics": metrics,
            "delta_mae": {
                split: float(metrics[split]["mae"] - full_metrics[split]["mae"])
                for split in metrics
            },
            "delta_rmse": {
                split: float(metrics[split]["rmse"] - full_metrics[split]["rmse"])
                for split in metrics
            },
            "delta_r2": {
                split: float(metrics[split]["r2"] - full_metrics[split]["r2"])
                for split in metrics
            },
        }
        rows.append(row)
    rows.sort(key=lambda r: -r["delta_mae"]["val"])

    out = {
        "run_dir": str(args.run_dir),
        "features": names,
        "full": {
            "n_features": len(names),
            "best_iteration": int(full.best_iteration_ or full.n_estimators),
            "metrics": full_metrics,
        },
        "mean_baseline": baseline,
        "ablations": rows,
        "note": (
            "Leave-one-group-out, retrain on δ=1. "
            "ΔMAE = MAE(without G) − MAE(all). Nested small val/test; "
            "val used for early stopping. Do not freeze features here."
        ),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "group_ablation.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")

    print("full MAE", {k: v["mae"] for k, v in full_metrics.items()})
    print("baseline MAE", {k: v["mae"] for k, v in baseline.items()})
    print("ΔMAE without G")
    for r in rows:
        d = r["delta_mae"]
        print(
            f"  {r['group']:20s} val {d['val']:+.4f}  test {d['test']:+.4f}  "
            f"train {d['train']:+.4f}  dropped {r['dropped']}"
        )
    print("wrote", path)


if __name__ == "__main__":
    main()
