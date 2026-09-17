#!/usr/bin/env python3
"""LightGBM regression of remaining return time τ on native scalars.

Protocol A trains on all rows, including censored τ (time to split cut).
Protocol B trains only on observed returns (δ=1), which is the only setting
where MAE / RMSE / R² are defined on a true remaining-return label.

Drops the replay completion cap (sampling.max_new_tokens).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
from rank_session_return_features import (  # noqa: E402
    DEFAULT_RUN,
    client_features,
    load_client,
    load_request_end,
)

DROP = {
    "sampling.max_new_tokens",
    "sampling.temperature",
    "sampling.top_p",
    "req.cached_tokens_device",
    "req.kv_allocated_len",
}


def metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "r2": float(r2_score(y, pred)),
    }


def y_summary(y: np.ndarray) -> dict[str, float]:
    qs = np.quantile(y, [0.0, 0.5, 0.9, 0.99, 1.0])
    return {
        "n": int(len(y)),
        "mean": float(np.mean(y)),
        "std": float(np.std(y)),
        "min": float(qs[0]),
        "p50": float(qs[1]),
        "p90": float(qs[2]),
        "p99": float(qs[3]),
        "max": float(qs[4]),
    }


def split_xy(
    clients: dict,
    feats: dict,
    names: list[str],
    split: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ids = [
        rid
        for rid, rec in clients.items()
        if rec.get("small_split") == split and rid in feats
    ]
    ids.sort()
    X = np.array(
        [[feats[rid].get(name) for name in names] for rid in ids],
        dtype=np.float64,
    )
    y = np.array([float(clients[i]["tau_s_small"]) for i in ids], dtype=np.float64)
    delta = np.array([int(clients[i]["delta_small"]) for i in ids], dtype=np.int32)
    return X, y, delta


def fit_lgbm(Xtr, ytr, Xva, yva) -> lgb.LGBMRegressor:
    model = lgb.LGBMRegressor(
        objective="regression",
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=0,
        verbose=-1,
    )
    model.fit(
        Xtr,
        ytr,
        eval_X=Xva,
        eval_y=yva,
        callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    return model


def eval_splits(
    pred: dict[str, np.ndarray],
    ys: dict[str, np.ndarray],
    ds: dict[str, np.ndarray],
    mean_tr: float,
) -> dict:
    report = {}
    for split in ("train", "val", "test"):
        y = ys[split]
        p_hat = pred[split]
        d = ds[split]
        base = np.full_like(y, mean_tr)
        obs = d == 1
        report[split] = {
            "all": {
                "model": metrics(y, p_hat),
                "mean_baseline": metrics(y, base),
            },
            "observed": {
                "model": metrics(y[obs], p_hat[obs]) if obs.any() else None,
                "mean_baseline": metrics(y[obs], base[obs]) if obs.any() else None,
            },
            "n_observed": int(obs.sum()),
            "n_censored": int((~obs).sum()),
            "y": y_summary(y),
            "y_observed": y_summary(y[obs]) if obs.any() else None,
        }
    return report


def importance(model: lgb.LGBMRegressor, names: list[str]) -> list[dict]:
    gain = model.booster_.feature_importance(importance_type="gain")
    return sorted(
        [{"feature": names[i], "gain": float(gain[i])} for i in range(len(names))],
        key=lambda r: -r["gain"],
    )


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
    clients = load_client(args.run_dir / "client" / "small_2200.client.jsonl")
    dump = load_request_end(args.run_dir / args.dump_file)
    merged = {}
    for rid, rec in clients.items():
        if rid not in dump:
            continue
        row = {**dump[rid], **client_features(rec)}
        for name in DROP:
            row.pop(name, None)
        merged[rid] = row
    names = sorted(next(iter(merged.values())).keys())
    Xtr, ytr, dtr = split_xy(clients, merged, names, "train")
    Xva, yva, dva = split_xy(clients, merged, names, "val")
    Xte, yte, dte = split_xy(clients, merged, names, "test")

    keep = []
    for j, name in enumerate(names):
        col = Xtr[:, j]
        finite = col[np.isfinite(col)]
        if finite.size == 0:
            continue
        if len(np.unique(np.round(finite, 12))) < 2:
            continue
        keep.append(j)
    names = [names[j] for j in keep]
    Xtr, Xva, Xte = Xtr[:, keep], Xva[:, keep], Xte[:, keep]
    ys = {"train": ytr, "val": yva, "test": yte}
    ds = {"train": dtr, "val": dva, "test": dte}

    all_model = fit_lgbm(Xtr, ytr, Xva, yva)
    all_pred = {
        "train": all_model.predict(Xtr),
        "val": all_model.predict(Xva),
        "test": all_model.predict(Xte),
    }

    obs_tr, obs_va = dtr == 1, dva == 1
    obs_model = fit_lgbm(Xtr[obs_tr], ytr[obs_tr], Xva[obs_va], yva[obs_va])
    obs_pred = {
        "train": obs_model.predict(Xtr),
        "val": obs_model.predict(Xva),
        "test": obs_model.predict(Xte),
    }

    log_model = fit_lgbm(
        Xtr[obs_tr],
        np.log1p(ytr[obs_tr]),
        Xva[obs_va],
        np.log1p(yva[obs_va]),
    )
    log_pred = {
        split: np.expm1(np.clip(log_model.predict(X), 0.0, 20.0))
        for split, X in (("train", Xtr), ("val", Xva), ("test", Xte))
    }

    out = {
        "run_dir": str(args.run_dir),
        "n_features": len(names),
        "features": names,
        "dropped": sorted(DROP),
        "protocols": {
            "A_all_rows": {
                "train_on": "all small-train rows, including censored τ",
                "best_iteration": int(all_model.best_iteration_ or all_model.n_estimators),
                "metrics": eval_splits(all_pred, ys, ds, float(np.mean(ytr))),
                "feature_importance_gain": importance(all_model, names),
            },
            "B_observed": {
                "train_on": "δ=1 remaining return time only",
                "best_iteration": int(obs_model.best_iteration_ or obs_model.n_estimators),
                "metrics": eval_splits(obs_pred, ys, ds, float(np.mean(ytr[obs_tr]))),
                "feature_importance_gain": importance(obs_model, names),
            },
            "C_observed_log1p": {
                "train_on": "δ=1, target=log1p(τ), metrics on original seconds",
                "best_iteration": int(log_model.best_iteration_ or log_model.n_estimators),
                "metrics": eval_splits(log_pred, ys, ds, float(np.mean(ytr[obs_tr]))),
                "feature_importance_gain": importance(log_model, names),
            },
        },
        "note": (
            "Protocol A uses censored τ = time to the small-split cut, so train/val "
            "labels are thousands of seconds while test labels collapse to ~18s. "
            "MAE/RMSE/R² on remaining return time are only valid under B/C (δ=1). "
            "sampling.max_new_tokens dropped (replay completion cap)."
        ),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "lgbm_metrics.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")

    def brief(proto: str, split: str) -> dict:
        block = out["protocols"][proto]["metrics"][split]
        return {
            "all": block["all"]["model"],
            "observed": block["observed"]["model"],
            "baseline_observed": block["observed"]["mean_baseline"],
        }

    summary = {
        proto: {split: brief(proto, split) for split in ("train", "val", "test")}
        for proto in out["protocols"]
    }
    print(json.dumps(summary, indent=2))
    print("B top gain", out["protocols"]["B_observed"]["feature_importance_gain"][:8])
    print("wrote", path)


if __name__ == "__main__":
    main()
