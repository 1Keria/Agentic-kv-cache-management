#!/usr/bin/env python3
"""Evaluate the locked serving scalar τ̂ = E[min(τ, 60)] as an eviction priority.

Does not retrain the hazard net. Nested small split is not an official freeze.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
from pipeline_inventory_groups import load_xy  # noqa: E402
from rank_session_return_features import DEFAULT_RUN, harrell_c  # noqa: E402
from train_session_return_k8_censor import (  # noqa: E402
    EDGES,
    HORIZON,
    K8,
    HazardNet,
    auc_score,
    official_tau,
    restricted_mean,
    survival_at,
)
from train_session_return_lgbm import fit_lgbm  # noqa: E402


def score(y, pred) -> dict[str, float]:
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "r2": float(r2_score(y, pred)),
    }


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    if ra.std() < 1e-12 or rb.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(ra.astype(np.float64), rb.astype(np.float64))[0, 1])


def known_min_tau(y_raw: np.ndarray, d_raw: np.ndarray, horizon: float) -> np.ndarray:
    return ((d_raw == 1) & (y_raw <= horizon)) | (y_raw >= horizon)


def ident_event(y: np.ndarray, d: np.ndarray, mask: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
    known = mask & (((d == 1) & (y <= t)) | (y >= t))
    yy = ((d[known] == 1) & (y[known] <= t))
    return known, yy


def quintiles(tau_hat: np.ndarray, y: np.ndarray, d: np.ndarray, mask: np.ndarray) -> list[dict]:
    idx = np.where(mask)[0]
    order = idx[np.argsort(tau_hat[idx], kind="stable")]
    chunks = np.array_split(order, 5)
    rows = []
    for q, part in enumerate(chunks, start=1):
        known10, yy10 = ident_event(y, d, np.isin(np.arange(len(y)), part), 10.0)
        known20, yy20 = ident_event(y, d, np.isin(np.arange(len(y)), part), 20.0)
        obs = part[(d[part] == 1)]
        rows.append(
            {
                "quintile": q,
                "meaning": "smallest τ̂ / keep first" if q == 1 else ("largest τ̂ / evict first" if q == 5 else ""),
                "n": int(len(part)),
                "mean_tau_hat": float(tau_hat[part].mean()),
                "p_return_10s": float(yy10.mean()) if known10.any() else None,
                "p_return_20s": float(yy20.mean()) if known20.any() else None,
                "n_observed": int(len(obs)),
                "mean_observed_tau": float(y[obs].mean()) if len(obs) else None,
            }
        )
    return rows


def false_evict(tau_hat: np.ndarray, y: np.ndarray, d: np.ndarray, mask: np.ndarray, frac=0.2, t=10.0) -> dict:
    idx = np.where(mask)[0]
    n_drop = max(1, int(round(frac * len(idx))))
    drop = idx[np.argsort(-tau_hat[idx], kind="stable")[:n_drop]]
    drop_mask = np.zeros(len(y), dtype=bool)
    drop_mask[drop] = True
    known, yy = ident_event(y, d, drop_mask, t)
    rand = idx.copy()
    rng = np.random.default_rng(0)
    rng.shuffle(rand)
    rand_drop = rand[:n_drop]
    rmask = np.zeros(len(y), dtype=bool)
    rmask[rand_drop] = True
    rknown, ryy = ident_event(y, d, rmask, t)
    return {
        "frac": frac,
        "n_evicted": int(n_drop),
        "return_within_t_among_evicted": float(yy.mean()) if known.any() else None,
        "n_identifiable_evicted": int(known.sum()),
        "random_return_within_t": float(ryy.mean()) if rknown.any() else None,
        "horizon_s": t,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    p.add_argument("--dump-file", default="server_dump/native_pid1681410.jsonl")
    p.add_argument(
        "--ckpt",
        type=Path,
        default=REPO_ROOT / "experiments/session_return/k8_model/k8_hazard.pt",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "experiments/session_return/k8_model/k8_official_tau.json",
    )
    args = p.parse_args()

    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    names, Xall, y_raw, d_raw, sm = load_xy(args.run_dir, args.dump_file)
    X = Xall[:, np.array([names.index(n) for n in K8], dtype=int)]
    y = np.minimum(y_raw, HORIZON)
    d = ((d_raw == 1) & (y_raw <= HORIZON)).astype(np.int32)
    label = np.minimum(y_raw, HORIZON)
    known = known_min_tau(y_raw, d_raw, HORIZON)
    tr, va, te = sm["train"], sm["val"], sm["test"]

    mean = np.asarray(ckpt["mean"], dtype=np.float64)
    std = np.asarray(ckpt["std"], dtype=np.float64)
    edges = np.asarray(ckpt.get("edges", EDGES), dtype=np.float64)
    z = (np.where(np.isfinite(X), X, mean) - mean) / std
    net = HazardNet(8, len(edges))
    net.load_state_dict(ckpt["state_dict"])
    net.eval()
    with torch.no_grad():
        logits = net(torch.tensor(z, dtype=torch.float32)).numpy()
    tau_hat = official_tau(logits, edges, HORIZON)
    hazards = 1.0 / (1.0 + np.exp(-logits))
    p10 = 1.0 - survival_at(hazards, edges, 10.0)
    p20 = 1.0 - survival_at(hazards, edges, 20.0)

    const = float(label[tr & known].mean())
    const_pred = np.full(len(X), const)

    lgbm = fit_lgbm(X[tr & (d == 1)], y[tr & (d == 1)], X[va & (d == 1)], y[va & (d == 1)])
    lgbm_pred = lgbm.predict(X)

    def split_block(mask: np.ndarray) -> dict:
        k = mask & known
        obs = mask & (d == 1)
        k10, y10 = ident_event(y, d, mask, 10.0)
        k20, y20 = ident_event(y, d, mask, 20.0)
        return {
            "n": int(mask.sum()),
            "n_identified_min_tau60": int(k.sum()),
            "n_observed": int(obs.sum()),
            "official_tau": {
                "vs_identified_min_tau60": score(label[k], tau_hat[k]) if k.any() else None,
                "vs_observed_only": score(y[obs], tau_hat[obs]) if obs.any() else None,
                "c_index": harrell_c(y[mask], d[mask], tau_hat[mask]),
                "auc_return_10s_using_-tau": auc_score(y10, -tau_hat[k10]) if k10.any() else None,
                "auc_return_10s_using_p10": auc_score(y10, p10[k10]) if k10.any() else None,
                "auc_return_20s_using_-tau": auc_score(y20, -tau_hat[k20]) if k20.any() else None,
                "spearman_vs_p10": spearman(tau_hat[mask], -p10[mask]),
                "spearman_vs_p20": spearman(tau_hat[mask], -p20[mask]),
                "mean": float(tau_hat[mask].mean()),
                "p50": float(np.median(tau_hat[mask])),
            },
            "constant_identified_mean": {
                "vs_identified_min_tau60": score(label[k], const_pred[k]) if k.any() else None,
            },
            "lgbm_observed_only": {
                "vs_identified_min_tau60": score(label[k], lgbm_pred[k]) if k.any() else None,
                "vs_observed_only": score(y[obs], lgbm_pred[obs]) if obs.any() else None,
                "c_index": harrell_c(y[mask], d[mask], lgbm_pred[mask]),
                "auc_return_10s_using_-pred": auc_score(y10, -lgbm_pred[k10]) if k10.any() else None,
            },
            "quintiles_by_tau_hat": quintiles(tau_hat, y, d, mask),
            "evict_largest_20pct": {
                "official_tau": false_evict(tau_hat, y, d, mask),
                "lgbm": false_evict(lgbm_pred, y, d, mask),
                "minus_p10": false_evict(-p10, y, d, mask),
            },
        }

    report = {
        "official_output": "restricted_mean_E[min(tau,60)]",
        "unit": "seconds",
        "evict_rule": "larger τ̂ first",
        "features": K8,
        "horizon_s": HORIZON,
        "edges_s": edges.tolist(),
        "ckpt": str(args.ckpt),
        "constant_baseline": const,
        "splits": {name: split_block(m) for name, m in (("train", tr), ("val", va), ("test", te))},
        "note": (
            "min(τ,60) is identified only if a return is observed by 60s or follow-up ≥ 60s. "
            "Nested val/test windows differ: val almost fully identified, test mostly only δ=1. "
            "Not an official freeze."
        ),
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    ckpt["official_output"] = "restricted_mean_E[min(tau,60)]"
    torch.save(ckpt, args.ckpt)

    for split in ("val", "test"):
        b = report["splits"][split]
        o = b["official_tau"]
        idm = o["vs_identified_min_tau60"]
        ev = b["evict_largest_20pct"]["official_tau"]
        print(
            f"{split:5s} ident_MAE={idm['mae']:.3f} n={idm['n']}  "
            f"obs_MAE={o['vs_observed_only']['mae']:.3f}  "
            f"C={o['c_index']['c_index']:.3f}  "
            f"AUC@10(-τ̂)={o['auc_return_10s_using_-tau']:.3f}  "
            f"AUC@10(p10)={o['auc_return_10s_using_p10']:.3f}  "
            f"evict20_hit10={ev['return_within_t_among_evicted']:.3f} "
            f"(random {ev['random_return_within_t']:.3f})"
        )
        print(f"      LGBM ident_MAE={b['lgbm_observed_only']['vs_identified_min_tau60']['mae']:.3f} "
              f"obs_MAE={b['lgbm_observed_only']['vs_observed_only']['mae']:.3f} "
              f"C={b['lgbm_observed_only']['c_index']['c_index']:.3f}")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
