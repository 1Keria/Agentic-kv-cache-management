#!/usr/bin/env python3
"""Censor-aware remaining-return τ on the locked 8 features (small split).

Observed returns are all < 60s; train/val administrative cuts are ~1h. The
cache-relevant process is therefore modeled under a 60s horizon: τ' = min(τ, 60),
δ' = 1 iff a return is observed by 60s. Discrete-hazard NLL matches the project
convention. Nested small is not an official freeze.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from torch import nn

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
from pipeline_inventory_groups import load_xy  # noqa: E402
from rank_session_return_features import DEFAULT_RUN, harrell_c  # noqa: E402
from select_inventory_representatives import PREFERRED  # noqa: E402
from train_session_return_lgbm import fit_lgbm  # noqa: E402

K8 = PREFERRED[:8]
HORIZON = 60.0
EDGES = np.array([2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 36.0, 60.0], dtype=np.float64)
HORIZONS = (5.0, 10.0, 20.0, 60.0)


def score_obs(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "r2": float(r2_score(y, pred)),
    }


def auc_score(y, score):
    y = np.asarray(y, dtype=bool)
    score = np.asarray(score)
    positive, negative = int(y.sum()), int((~y).sum())
    if not positive or not negative:
        return None
    order = np.argsort(score, kind="stable")
    sorted_score = score[order]
    ranks = np.empty(len(score), float)
    start = 0
    while start < len(score):
        end = start + 1
        while end < len(score) and sorted_score[end] == sorted_score[start]:
            end += 1
        ranks[order[start:end]] = 0.5 * (start + 1 + end)
        start = end
    return float((ranks[y].sum() - positive * (positive + 1) / 2) / (positive * negative))


class HazardNet(nn.Module):
    def __init__(self, n_in: int, n_buckets: int, emp_logit: torch.Tensor | None = None):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 32),
            nn.ReLU(),
            nn.Linear(32, 32),
            nn.ReLU(),
            nn.Linear(32, n_buckets),
        )
        if emp_logit is not None:
            with torch.no_grad():
                self.net[-1].weight.mul_(0.01)
                self.net[-1].bias.copy_(emp_logit)

    def forward(self, x):
        return self.net(x)


class AFTNet(nn.Module):
    def __init__(self, n_in: int, log_med: float, log_sigma: float):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 32),
            nn.ReLU(),
            nn.Linear(32, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )
        with torch.no_grad():
            self.net[-1].weight.mul_(0.01)
            self.net[-1].bias.fill_(log_med)
        self.log_sigma = nn.Parameter(torch.tensor(float(log_sigma)))

    def forward(self, x):
        return self.net(x).squeeze(-1), self.log_sigma.clamp(-2.5, 2.0)


def hazard_nll(logits, duration, event, edges):
    log_h = torch.nn.functional.logsigmoid(logits)
    log_s = torch.nn.functional.logsigmoid(-logits)
    index = torch.bucketize(duration, edges, right=True)
    positions = torch.arange(edges.numel(), device=logits.device).unsqueeze(0)
    ll = (log_s * (positions < index.unsqueeze(1))).sum(dim=1)
    finite_event = (event > 0.5) & (index < edges.numel())
    if finite_event.any():
        rows = torch.nonzero(finite_event, as_tuple=False).squeeze(1)
        ll[rows] += log_h[rows, index[rows]]
    partial_censor = (event <= 0.5) & (index < edges.numel())
    if partial_censor.any():
        rows = torch.nonzero(partial_censor, as_tuple=False).squeeze(1)
        j = index[rows]
        left = torch.where(j == 0, torch.zeros_like(duration[rows]), edges[j - 1])
        width = (edges[j] - left).clamp_min(1e-6)
        fraction = ((duration[rows] - left) / width).clamp(0, 1)
        ll[rows] += fraction * log_s[rows, j]
    return (-ll).mean()


def aft_nll(mu, log_sigma, duration, event):
    sigma = log_sigma.exp()
    log_t = duration.clamp_min(1e-6).log()
    z = (log_t - mu) / sigma
    nll_obs = 0.5 * math.log(2 * math.pi) + log_sigma + log_t + 0.5 * z.square()
    surv = 0.5 * torch.erfc(z / math.sqrt(2.0))
    nll_c = -torch.log(surv.clamp_min(1e-12))
    return torch.where(event > 0.5, nll_obs, nll_c).mean()


def phi(z: torch.Tensor) -> torch.Tensor:
    return 0.5 * torch.erfc(-z / math.sqrt(2.0))


def lognormal_trunc_mean(mu: np.ndarray, sigma: float, h: float) -> np.ndarray:
    mu_t = torch.tensor(mu, dtype=torch.float64)
    sig = torch.tensor(sigma, dtype=torch.float64)
    s2 = sig * sig
    log_h = math.log(h)
    a = (log_h - mu_t) / sig
    b = (log_h - mu_t - s2) / sig
    denom = phi(a).clamp_min(1e-12)
    return (torch.exp(mu_t + 0.5 * s2) * phi(b) / denom).numpy()


def lognormal_restricted_mean(mu: np.ndarray, sigma: float, h: float) -> np.ndarray:
    mu_t = torch.tensor(mu, dtype=torch.float64)
    sig = torch.tensor(sigma, dtype=torch.float64)
    z = (math.log(h) - mu_t) / sig
    p_le = phi(z).numpy()
    cond = lognormal_trunc_mean(mu, sigma, h)
    return cond * p_le + h * (1.0 - p_le)


def survival_at(hazards: np.ndarray, edges: np.ndarray, times) -> np.ndarray:
    hazards = np.clip(np.asarray(hazards, np.float64), 1e-9, 1 - 1e-9)
    times = np.asarray(times, np.float64)
    if times.ndim == 0:
        times = np.full(len(hazards), float(times))
    log_int = np.log(1.0 - hazards)
    log_s = np.zeros(len(hazards), np.float64)
    left = 0.0
    for j, right in enumerate(edges):
        full = times >= right
        log_s[full] += log_int[full, j]
        partial = (times > left) & (times < right)
        if partial.any():
            log_s[partial] += ((times[partial] - left) / (right - left)) * log_int[partial, j]
        left = right
    return np.exp(log_s)


def discrete_mass(hazards: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    hazards = np.clip(hazards, 1e-9, 1 - 1e-9)
    surv = np.ones((len(hazards), 1))
    masses = []
    left = 0.0
    mids = []
    for j, right in enumerate(edges):
        s_left = surv[:, 0]
        p = s_left * hazards[:, j]
        masses.append(p)
        mids.append(0.5 * (left + right))
        surv = (s_left * (1.0 - hazards[:, j]))[:, None]
        left = right
    return np.stack(masses, axis=1), np.array(mids)


def conditional_mean(hazards: np.ndarray, edges: np.ndarray, h: float) -> np.ndarray:
    mass, mids = discrete_mass(hazards, edges)
    keep = edges <= h + 1e-9
    num = (mass[:, keep] * mids[keep]).sum(axis=1)
    den = mass[:, keep].sum(axis=1)
    out = np.full(len(hazards), h)
    ok = den > 1e-8
    out[ok] = num[ok] / den[ok]
    return out


def restricted_mean(hazards: np.ndarray, edges: np.ndarray, h: float) -> np.ndarray:
    mass, mids = discrete_mass(hazards, edges)
    keep = edges <= h + 1e-9
    p_le = mass[:, keep].sum(axis=1)
    cond = conditional_mean(hazards, edges, h)
    return cond * np.clip(p_le, 0, 1) + h * np.clip(1.0 - p_le, 0, 1)


def official_tau(logits: np.ndarray, edges: np.ndarray = EDGES, horizon: float = HORIZON) -> np.ndarray:
    """Serving scalar: E[min(τ, horizon)]. Smaller means return sooner; evict larger first."""
    hazards = 1.0 / (1.0 + np.exp(-np.asarray(logits, np.float64)))
    return restricted_mean(hazards, edges, horizon)


def empirical_hazards(y: np.ndarray, d: np.ndarray, edges: np.ndarray) -> np.ndarray:
    h = []
    left = 0.0
    for right in edges:
        at_risk = int((y > left).sum())
        n_event = int(((d == 1) & (y > left) & (y <= right)).sum())
        h.append(n_event / max(at_risk, 1))
        left = right
    return np.clip(np.array(h, dtype=np.float64), 1e-4, 1 - 1e-4)


def pack(X, y, d, mask, mean, std):
    x = np.where(np.isfinite(X[mask]), X[mask], mean)
    x = (x - mean) / std
    return (
        torch.tensor(x, dtype=torch.float32),
        torch.tensor(y[mask], dtype=torch.float32),
        torch.tensor((d[mask] == 1).astype(np.float32)),
    )


def fit_torch(model, loss_fn, train, val, epochs=2000, lr=1e-3, patience=80, seed=0):
    torch.manual_seed(seed)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    best_val = float("inf")
    wait = 0
    stopped = 0
    xtr, ytr, etr = train
    xva, yva, eva = val
    for epoch in range(1, epochs + 1):
        model.train()
        opt.zero_grad()
        loss = loss_fn(model(xtr), ytr, etr)
        if not torch.isfinite(loss):
            break
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()
        model.eval()
        with torch.no_grad():
            vloss = float(loss_fn(model(xva), yva, eva))
        if vloss < best_val - 1e-5:
            best_val = vloss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
            stopped = epoch
        else:
            wait += 1
            if wait >= patience:
                break
    model.load_state_dict(best_state)
    return best_val, stopped, epoch


def horizon_block(y: np.ndarray, d: np.ndarray, mask: np.ndarray, p_by_h: dict) -> dict:
    out = {}
    for h in HORIZONS:
        known = mask & (((d == 1) & (y <= h)) | (y >= h))
        yy = ((d[known] == 1) & (y[known] <= h)).astype(np.float64)
        pp = np.clip(p_by_h[h][known], 1e-6, 1 - 1e-6)
        brier = float(((pp - yy) ** 2).mean()) if known.any() else None
        nll = float((-(yy * np.log(pp) + (1 - yy) * np.log(1 - pp))).mean()) if known.any() else None
        out[str(int(h))] = {
            "n": int(known.sum()),
            "positive_rate": float(yy.mean()) if known.any() else None,
            "auc": auc_score(yy, pp) if known.any() else None,
            "brier": brier,
            "nll": nll,
        }
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    p.add_argument("--dump-file", default="server_dump/native_pid1681410.jsonl")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "experiments/session_return/k8_model",
    )
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    names, Xall, y_raw, d_raw, sm = load_xy(args.run_dir, args.dump_file)
    missing = [n for n in K8 if n not in names]
    if missing:
        raise SystemExit(f"missing features: {missing}")
    X = Xall[:, np.array([names.index(n) for n in K8], dtype=int)]
    y = np.minimum(y_raw, HORIZON)
    d = ((d_raw == 1) & (y_raw <= HORIZON)).astype(np.int32)
    tr, va, te = sm["train"], sm["val"], sm["test"]

    finite = np.isfinite(X[tr])
    mean = np.where(finite.any(0), np.nanmean(np.where(finite, X[tr], np.nan), axis=0), 0.0)
    std = np.where(finite.any(0), np.nanstd(np.where(finite, X[tr], np.nan), axis=0), 1.0)
    std = np.where(std < 1e-8, 1.0, std)

    x_all = torch.tensor((np.where(np.isfinite(X), X, mean) - mean) / std, dtype=torch.float32)
    train = pack(X, y, d, tr, mean, std)
    val = pack(X, y, d, va, mean, std)
    edges_t = torch.tensor(EDGES, dtype=torch.float32)

    emp_h = empirical_hazards(y[tr], d[tr], EDGES)
    emp_logit = torch.tensor(np.log(emp_h / (1.0 - emp_h)), dtype=torch.float32)
    km_logits = emp_logit.unsqueeze(0).expand(len(X), -1).contiguous()
    km_haz = 1.0 / (1.0 + np.exp(-km_logits.numpy()))

    obs_tr = y[tr & (d == 1)]
    log_med = float(np.log(np.median(obs_tr)))
    log_sigma0 = float(np.log(np.std(np.log(obs_tr.clip(1e-6))) + 1e-6))

    # --- discrete hazard ---
    haz = HazardNet(8, len(EDGES), emp_logit)

    def haz_loss(logits, duration, event):
        return hazard_nll(logits, duration, event, edges_t)

    haz_val, haz_best, haz_ran = fit_torch(haz, haz_loss, train, val, seed=args.seed)
    haz.eval()
    with torch.no_grad():
        h_logits = haz(x_all).numpy()
    h = 1.0 / (1.0 + np.exp(-h_logits))
    haz_cond = conditional_mean(h, EDGES, HORIZON)
    haz_rmst = restricted_mean(h, EDGES, HORIZON)
    p_haz = {hh: 1.0 - survival_at(h, EDGES, hh) for hh in HORIZONS}

    # --- log-normal AFT on the same 60s-admin labels ---
    aft = AFTNet(8, log_med, log_sigma0)

    def aft_loss(out, duration, event):
        mu, log_sigma = out
        return aft_nll(mu, log_sigma, duration, event)

    aft_val, aft_best, aft_ran = fit_torch(aft, aft_loss, train, val, seed=args.seed)
    aft.eval()
    with torch.no_grad():
        mu_all, log_sigma_t = aft(x_all)
    mu_np = mu_all.numpy()
    aft_sigma = float(log_sigma_t.exp())
    aft_cond = lognormal_trunc_mean(mu_np, aft_sigma, HORIZON)
    aft_rmst = lognormal_restricted_mean(mu_np, aft_sigma, HORIZON)
    with torch.no_grad():
        p_aft = {hh: phi((math.log(hh) - mu_all) / aft_sigma).numpy() for hh in HORIZONS}

    # --- LightGBM observed-only ---
    lgbm = fit_lgbm(X[tr & (d == 1)], y[tr & (d == 1)], X[va & (d == 1)], y[va & (d == 1)])
    lgbm_pred = lgbm.predict(X)
    scale = float(np.std(obs_tr)) or 5.0
    p_lgbm = {
        hh: 1.0 / (1.0 + np.exp((lgbm_pred - hh) / scale)) for hh in HORIZONS
    }

    def nll_on(mask, kind: str) -> float:
        xt, yt, et = pack(X, y, d, mask, mean, std)
        with torch.no_grad():
            if kind == "hazard":
                return float(hazard_nll(haz(xt), yt, et, edges_t))
            if kind == "aft":
                mu, ls = aft(xt)
                return float(aft_nll(mu, ls, yt, et))
            return float(hazard_nll(km_logits[mask], yt, et, edges_t))

    def pack_model(pred_time, rank_score, nlls, p_by_h, extra):
        rec = dict(extra)
        rec["metrics"] = {}
        for split, mask in (("train", tr), ("val", va), ("test", te)):
            obs = mask & (d == 1)
            rec["metrics"][split] = {
                "n": int(mask.sum()),
                "n_observed": int(obs.sum()),
                "censor_nll": nlls[split] if nlls else None,
                "observed_conditional": score_obs(y[obs], pred_time[obs]) if obs.any() else None,
                "c_index": harrell_c(y[mask], d[mask], rank_score[mask]),
                "horizons": horizon_block(y, d, mask, p_by_h) if p_by_h else None,
            }
        return rec

    km_nll = {s: nll_on(m, "km") for s, m in (("train", tr), ("val", va), ("test", te))}
    haz_nlls = {s: nll_on(m, "hazard") for s, m in (("train", tr), ("val", va), ("test", te))}
    aft_nlls = {s: nll_on(m, "aft") for s, m in (("train", tr), ("val", va), ("test", te))}
    p_km = {hh: 1.0 - survival_at(km_haz, EDGES, hh) for hh in HORIZONS}
    km_rmst = restricted_mean(km_haz, EDGES, HORIZON)

    report = {
        "features": K8,
        "n_features": 8,
        "horizon_s": HORIZON,
        "edges_s": EDGES.tolist(),
        "run_dir": str(args.run_dir),
        "seed": args.seed,
        "empirical_bucket_hazard": emp_h.tolist(),
        "counts": {
            s: {
                "n": int(m.sum()),
                "n_observed": int((m & (d == 1)).sum()),
                "n_censored": int((m & (d == 0)).sum()),
            }
            for s, m in (("train", tr), ("val", va), ("test", te))
        },
        "models": {
            "km_constant": pack_model(
                km_rmst,
                km_rmst,
                km_nll,
                p_km,
                {"train_on": "train empirical bucket hazards (no features)"},
            ),
            "lgbm_observed_only": pack_model(
                lgbm_pred,
                lgbm_pred,
                None,
                p_lgbm,
                {
                    "train_on": "δ=1 only, no censoring likelihood",
                    "best_iteration": int(lgbm.best_iteration_ or lgbm.n_estimators),
                },
            ),
            "lognormal_aft": pack_model(
                aft_cond,
                aft_rmst,
                aft_nlls,
                p_aft,
                {
                    "train_on": "all rows, 60s-admin right-censored log-normal NLL",
                    "sigma": aft_sigma,
                    "best_epoch": aft_best,
                    "ran_epochs": aft_ran,
                    "val_censor_nll": aft_val,
                },
            ),
            "discrete_hazard_mlp": pack_model(
                haz_rmst,
                haz_rmst,
                haz_nlls,
                p_haz,
                {
                    "official_output": "restricted_mean_E[min(tau,60)]",
                    "train_on": "all rows, 60s-admin discrete-hazard NLL",
                    "hidden": [32, 32],
                    "n_buckets": int(len(EDGES)),
                    "best_epoch": haz_best,
                    "ran_epochs": haz_ran,
                    "val_censor_nll": haz_val,
                    "internal_conditional_mean_mae_val": score_obs(
                        y[va & (d == 1)], haz_cond[va & (d == 1)]
                    ),
                },
            ),
        },
        "official_output": "restricted_mean_E[min(tau,60)]",
        "note": (
            "Serving output is the scalar τ̂ = E[min(τ, 60)] from the 9 hazards. "
            "Evict larger τ̂ first. Nested small split, not an official freeze."
        ),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "k8_censor_metrics.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    torch.save(
        {
            "kind": "discrete_hazard_mlp",
            "official_output": "restricted_mean_E[min(tau,60)]",
            "state_dict": haz.state_dict(),
            "features": K8,
            "mean": mean,
            "std": std,
            "edges": EDGES,
            "horizon_s": HORIZON,
        },
        args.out_dir / "k8_hazard.pt",
    )
    torch.save(
        {
            "kind": "lognormal_aft",
            "state_dict": aft.state_dict(),
            "features": K8,
            "mean": mean,
            "std": std,
            "horizon_s": HORIZON,
        },
        args.out_dir / "k8_aft.pt",
    )

    def line(name, rec):
        m = rec["metrics"]
        h10 = m["val"]["horizons"]["10"] if m["val"]["horizons"] else {}
        nll = m["val"].get("censor_nll")
        mae = m["val"]["observed_conditional"]["mae"]
        tmae = m["test"]["observed_conditional"]["mae"]
        bits = f"{name:22s} val_cond_mae={mae:.3f} test_cond_mae={tmae:.3f}"
        bits += f" val_C={m['val']['c_index']['c_index']:.3f} test_C={m['test']['c_index']['c_index']:.3f}"
        if nll is not None:
            bits += f" val_nll={nll:.4f}"
        if h10.get("auc") is not None:
            bits += f" val_auc@10s={h10['auc']:.3f}"
        print(bits)

    for name, rec in report["models"].items():
        line(name, rec)
    print("wrote", path)


if __name__ == "__main__":
    main()
