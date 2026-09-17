#!/usr/bin/env python3
"""Rank every extracted native scalar by permutation ΔMAE.

No grouping, no dropping. Constants land at ~0. sampling.max_new_tokens is
kept and flagged as the replay completion cap.
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
from train_session_return_lgbm import fit_lgbm, split_xy  # noqa: E402

LEAKY = {"sampling.max_new_tokens"}


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

    clients = load_client(args.run_dir / "client" / "small_2200.client.jsonl")
    dump = load_request_end(args.run_dir / args.dump_file)
    merged = {}
    for rid, rec in clients.items():
        if rid not in dump:
            continue
        merged[rid] = {**dump[rid], **client_features(rec)}
    names = sorted(next(iter(merged.values())).keys())
    Xtr, ytr, dtr = split_xy(clients, merged, names, "train")
    Xva, yva, dva = split_xy(clients, merged, names, "val")
    Xte, yte, dte = split_xy(clients, merged, names, "test")
    obs_tr, obs_va = dtr == 1, dva == 1
    obs_te = dte == 1

    flags = {}
    for j, name in enumerate(names):
        col = Xtr[:, j]
        finite = col[np.isfinite(col)]
        nuniq = int(len(np.unique(np.round(finite, 12)))) if finite.size else 0
        flag = []
        if name in LEAKY:
            flag.append("leaky_replay_cap")
        if nuniq < 2:
            flag.append("constant")
        flags[name] = {"n_unique_train": nuniq, "flags": flag}

    # exact duplicate of an earlier column
    for j, name in enumerate(names):
        if "constant" in flags[name]["flags"]:
            continue
        for k in range(j):
            a, b = Xtr[:, j], Xtr[:, k]
            mask = np.isfinite(a) & np.isfinite(b)
            if mask.sum() < 2:
                continue
            if np.allclose(a[mask], b[mask], equal_nan=True):
                flags[name]["flags"].append(f"duplicate_of:{names[k]}")
                break

    model = fit_lgbm(Xtr[obs_tr], ytr[obs_tr], Xva[obs_va], yva[obs_va])
    gain = model.booster_.feature_importance(importance_type="gain")
    intact = {
        "val": float(mean_absolute_error(yva[obs_va], model.predict(Xva[obs_va]))),
        "test": float(mean_absolute_error(yte[obs_te], model.predict(Xte[obs_te]))),
    }

    evals = {"val": (Xva[obs_va], yva[obs_va]), "test": (Xte[obs_te], yte[obs_te])}
    rows = []
    for j, name in enumerate(names):
        row = {
            "rank": 0,
            "feature": name,
            "gain": float(gain[j]),
            **flags[name],
        }
        rng = np.random.default_rng(args.seed + j)
        for split, (X, y) in evals.items():
            deltas = np.empty(args.n_repeats, dtype=np.float64)
            n = len(X)
            for i in range(args.n_repeats):
                perm = rng.permutation(n)
                Xp = X.copy()
                Xp[:, j] = X[perm, j]
                deltas[i] = float(mean_absolute_error(y, model.predict(Xp))) - intact[split]
            row[split] = {
                "delta_mae_mean": float(np.mean(deltas)),
                "delta_mae_std": float(np.std(deltas, ddof=1)),
                "frac_positive": float(np.mean(deltas > 0)),
            }
        rows.append(row)

    rows.sort(key=lambda r: (-r["val"]["delta_mae_mean"], -r["gain"], r["feature"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    out = {
        "run_dir": str(args.run_dir),
        "n_features": len(names),
        "n_repeats": args.n_repeats,
        "n_observed": {"val": int(obs_va.sum()), "test": int(obs_te.sum())},
        "intact_mae": intact,
        "best_iteration": int(model.best_iteration_ or model.n_estimators),
        "ranking": rows,
        "note": (
            "All extracted native scalars. ΔMAE = MAE(permuted) − MAE(intact) "
            "on δ=1, 40 shuffles. Model trained on every column. "
            "Do not freeze from nested small val."
        ),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "permutation_all.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print("intact", intact, "n", len(names))
    for r in rows:
        mark = ",".join(r["flags"]) or "-"
        print(
            f"{r['rank']:2d} {r['feature']:36s} "
            f"val {r['val']['delta_mae_mean']:+.4f}±{r['val']['delta_mae_std']:.3f}  "
            f"test {r['test']['delta_mae_mean']:+.4f}±{r['test']['delta_mae_std']:.3f}  "
            f"gain {r['gain']:.1f}  {mark}"
        )
    print("wrote", path)


if __name__ == "__main__":
    main()
