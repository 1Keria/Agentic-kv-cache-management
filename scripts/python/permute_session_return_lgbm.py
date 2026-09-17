#!/usr/bin/env python3
"""Grouped permutation importance for the observed-τ LightGBM.

ΔMAE = MAE(permuted) − MAE(intact) on δ=1 rows. The same row permutation is
applied to every column in a group so within-group collinearity is preserved.
Diagnosis only; do not freeze features from the nested small split.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import mean_absolute_error

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
from rank_session_return_features import (  # noqa: E402
    DEFAULT_RUN,
    client_features,
    load_client,
    load_request_end,
)
from train_session_return_lgbm import DROP, fit_lgbm, split_xy  # noqa: E402

# Groups from Spearman on small-train δ=1 plus native-field semantics.
# seq_occupied is one snapshot (ρ=1). resource_pool is complementary pool
# sizes (evictable vs protected ρ≈−0.89). client_* are generation knobs.
GROUPS: dict[str, dict] = {
    "seq_occupied": {
        "features": [
            "req.fill_len",
            "req.cache_protected_len",
            "req.kv_committed_len",
        ],
        "why": "Spearman ρ=1.0; same occupied KV / fill snapshot",
    },
    "resource_pool": {
        "features": [
            "resource.available_size",
            "resource.evictable_size",
            "resource.protected_size",
        ],
        "why": "Pool snapshot; evictable vs protected ρ≈−0.89. Inventory: controller-only",
    },
    "client_sampling": {
        "features": [
            "client.max_tokens",
            "client.temperature",
            "client.top_p",
        ],
        "why": "Client generation knobs; temperature–max_tokens ρ≈0.62",
    },
    "output_len": {
        "features": ["req.finished_len"],
        "why": "Actual completion length; strongest univariate rank vs τ",
    },
    "reasoning": {
        "features": ["req.reasoning_tokens", "req._is_reasoning_over"],
        "why": "Reasoning state; tokens vs over ρ≈−0.34",
    },
    "cache_hit": {
        "features": ["req.cached_tokens"],
        "why": "Recorded cache-hit tokens; not collinear with seq_occupied",
    },
    "this_turn_prefill": {
        "features": ["req.extend_input_len"],
        "why": "Tokens to prefill this turn; nearly independent of other scalars",
    },
}


def varying_names(Xtr: np.ndarray, names: list[str]) -> list[str]:
    keep = []
    for j, name in enumerate(names):
        col = Xtr[:, j]
        finite = col[np.isfinite(col)]
        if finite.size == 0:
            continue
        if len(np.unique(np.round(finite, 12))) < 2:
            continue
        keep.append(name)
    return keep


def load_matrix(run_dir: Path, dump_file: str):
    clients = load_client(run_dir / "client" / "small_2200.client.jsonl")
    dump = load_request_end(run_dir / dump_file)
    merged = {}
    for rid, rec in clients.items():
        if rid not in dump:
            continue
        row = {**dump[rid], **client_features(rec)}
        for name in DROP:
            row.pop(name, None)
        merged[rid] = row
    all_names = sorted(next(iter(merged.values())).keys())
    Xtr_all, _, _ = split_xy(clients, merged, all_names, "train")
    names = varying_names(Xtr_all, all_names)
    Xtr, ytr, dtr = split_xy(clients, merged, names, "train")
    Xva, yva, dva = split_xy(clients, merged, names, "val")
    Xte, yte, dte = split_xy(clients, merged, names, "test")
    return names, {
        "train": (Xtr, ytr, dtr),
        "val": (Xva, yva, dva),
        "test": (Xte, yte, dte),
    }


def perm_mae(
    model,
    X: np.ndarray,
    y: np.ndarray,
    cols: list[int],
    n_repeats: int,
    seed: int,
) -> np.ndarray:
    intact = float(mean_absolute_error(y, model.predict(X)))
    rng = np.random.default_rng(seed)
    out = np.empty(n_repeats, dtype=np.float64)
    n = len(X)
    for i in range(n_repeats):
        perm = rng.permutation(n)
        Xp = X.copy()
        Xp[:, cols] = X[perm][:, cols]
        out[i] = float(mean_absolute_error(y, model.predict(Xp))) - intact
    return out


def summarize(deltas: np.ndarray, intact: float) -> dict:
    return {
        "intact_mae": intact,
        "delta_mae_mean": float(np.mean(deltas)),
        "delta_mae_std": float(np.std(deltas, ddof=1)),
        "delta_mae_p05": float(np.quantile(deltas, 0.05)),
        "delta_mae_p95": float(np.quantile(deltas, 0.95)),
        "frac_positive": float(np.mean(deltas > 0)),
        "n_repeats": int(len(deltas)),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    p.add_argument("--dump-file", default="server_dump/native_pid1681410.jsonl")
    p.add_argument("--n-repeats", type=int, default=40)
    p.add_argument("--seed", type=int, default=0)
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
    model = fit_lgbm(Xtr[obs_tr], ytr[obs_tr], Xva[obs_va], yva[obs_va])

    used = set(names)
    grouped = set()
    resolved = {}
    for gname, spec in GROUPS.items():
        feats = [f for f in spec["features"] if f in used]
        missing = [f for f in spec["features"] if f not in used]
        if not feats:
            continue
        grouped.update(feats)
        resolved[gname] = {**spec, "features": feats, "missing": missing}
    leftover = sorted(used - grouped)
    if leftover:
        resolved["ungrouped"] = {
            "features": leftover,
            "why": "Varying scalars not assigned to a correlation group",
            "missing": [],
        }

    eval_splits = {
        "val": (Xva[obs_va], yva[obs_va]),
        "test": (splits["test"][0][splits["test"][2] == 1], splits["test"][1][splits["test"][2] == 1]),
    }
    intact = {
        split: float(mean_absolute_error(y, model.predict(X)))
        for split, (X, y) in eval_splits.items()
    }

    group_rows = []
    for gname, spec in resolved.items():
        cols = [name_i[f] for f in spec["features"]]
        row = {
            "group": gname,
            "features": spec["features"],
            "why": spec["why"],
            "n_features": len(spec["features"]),
        }
        for split, (X, y) in eval_splits.items():
            deltas = perm_mae(model, X, y, cols, args.n_repeats, args.seed)
            row[split] = summarize(deltas, intact[split])
        group_rows.append(row)
    group_rows.sort(key=lambda r: -r["val"]["delta_mae_mean"])

    single_rows = []
    for name in names:
        row = {"feature": name, "group": next(g for g, s in resolved.items() if name in s["features"])}
        for split, (X, y) in eval_splits.items():
            deltas = perm_mae(model, X, y, [name_i[name]], args.n_repeats, args.seed + 1000)
            row[split] = summarize(deltas, intact[split])
        single_rows.append(row)
    single_rows.sort(key=lambda r: -r["val"]["delta_mae_mean"])

    all_cols = list(range(len(names)))
    all_row = {"group": "all_features"}
    for split, (X, y) in eval_splits.items():
        deltas = perm_mae(model, X, y, all_cols, args.n_repeats, args.seed + 2000)
        all_row[split] = summarize(deltas, intact[split])

    out = {
        "run_dir": str(args.run_dir),
        "n_repeats": args.n_repeats,
        "seed": args.seed,
        "n_features": len(names),
        "features": names,
        "n_observed": {k: int(len(v[1])) for k, v in eval_splits.items()},
        "intact_mae": intact,
        "best_iteration": int(model.best_iteration_ or model.n_estimators),
        "groups": group_rows,
        "singles": single_rows,
        "all_features": all_row,
        "note": (
            "ΔMAE = MAE(permuted) − MAE(intact) on δ=1. Same row shuffle "
            "within a group. Nested small val/test; val also used for early "
            "stopping. Do not freeze features from this ranking."
        ),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "permutation_groups.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")

    print("intact MAE", intact)
    print("groups (val ΔMAE mean ± std)")
    for r in group_rows:
        v, t = r["val"], r["test"]
        print(
            f"  {r['group']:20s} val {v['delta_mae_mean']:+.4f}±{v['delta_mae_std']:.4f}  "
            f"test {t['delta_mae_mean']:+.4f}±{t['delta_mae_std']:.4f}  {r['features']}"
        )
    print("wrote", path)


if __name__ == "__main__":
    main()
