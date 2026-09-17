#!/usr/bin/env python3
"""Train remaining-return τ on the locked 8 native features (small split).

Protocol B: fit on train δ=1, early-stop on val δ=1, report test δ=1.
Nested small is not an official freeze.
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
from pipeline_inventory_groups import load_xy  # noqa: E402
from rank_session_return_features import DEFAULT_RUN  # noqa: E402
from select_inventory_representatives import PREFERRED  # noqa: E402
from train_session_return_lgbm import fit_lgbm  # noqa: E402

K8 = PREFERRED[:8]


def score(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "r2": float(r2_score(y, pred)),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    p.add_argument("--dump-file", default="server_dump/native_pid1681410.jsonl")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "experiments/session_return/lgbm/k8",
    )
    args = p.parse_args()

    names, X, y, d, sm = load_xy(args.run_dir, args.dump_file)
    missing = [n for n in K8 if n not in names]
    if missing:
        raise SystemExit(f"missing features: {missing}")
    keep = np.array([names.index(n) for n in K8], dtype=int)
    obs = d == 1
    tr, va, te = sm["train"], sm["val"], sm["test"]

    model = fit_lgbm(
        X[tr & obs][:, keep],
        y[tr & obs],
        X[va & obs][:, keep],
        y[va & obs],
    )
    mean_tr = float(np.mean(y[tr & obs]))
    report = {"features": K8, "n_features": 8, "run_dir": str(args.run_dir)}
    for split, mask in (("train", tr), ("val", va), ("test", te)):
        m = mask & obs
        pred = model.predict(X[m][:, keep])
        report[split] = {
            "observed": score(y[m], pred),
            "mean_baseline": score(y[m], np.full(int(m.sum()), mean_tr)),
            "n_all": int(mask.sum()),
            "n_observed": int(m.sum()),
            "n_censored": int((mask & ~obs).sum()),
        }
    gain = model.booster_.feature_importance(importance_type="gain")
    report["best_iteration"] = int(model.best_iteration_ or model.n_estimators)
    report["feature_importance_gain"] = [
        {"feature": K8[i], "gain": float(gain[i])} for i in range(8)
    ]
    report["feature_importance_gain"].sort(key=lambda r: -r["gain"])
    report["note"] = (
        "LightGBM on small split, δ=1 only. val used for early stopping. "
        "Nested small is not an official freeze."
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.out_dir / "k8_metrics.json"
    metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    model_path = args.out_dir / "k8_lgbm.txt"
    model.booster_.save_model(str(model_path))
    print(json.dumps({s: report[s]["observed"] for s in ("train", "val", "test")}, indent=2))
    print("gain", report["feature_importance_gain"])
    print("wrote", metrics_path)
    print("wrote", model_path)


if __name__ == "__main__":
    main()
