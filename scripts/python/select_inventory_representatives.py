#!/usr/bin/env python3
"""Within-group representative selection + nested k-feature sets.

Does not invent fields. Official model still drops sampling.max_new_tokens.
Nested small split is not an official freeze.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
from pipeline_inventory_groups import GROUPS, LEAKY, load_xy  # noqa: E402
from rank_inventory_permutation import SPECS  # noqa: E402
from rank_session_return_features import DEFAULT_RUN  # noqa: E402
from train_session_return_lgbm import fit_lgbm  # noqa: E402

HARD_EXCLUDE_GROUPS = {
    LEAKY,
    "replay_time",
    "identity",
    "native_session",
    "multimodal",
    "container_flags",
    "sampling_stop_penalty",
    "radix_node",
}

# inventory: resource snapshot is controller-only; only used to fill large k.
CONTROLLER_GROUPS = {"resource_pool"}

# Preferred serving names; used to break cliques and to order the nested ladder.
PREFERRED = [
    "req.finished_len",
    "client.temperature",
    "client.max_tokens",
    "req.cached_tokens",
    "client.tools",
    "req.finished_reason",
    "req.fill_len",
    "req.extend_input_len",
    "client.messages",
    "req.reasoning_tokens",
    "req._is_reasoning_over",
    "client.top_p",
    "req.cache_protected_len",
    "req.kv_committed_len",
    "tokenized.input_ids",
    "last_node.key.token_ids",
    "scheduler.cur_batch",
]
CONTROLLER_TAIL = [
    "resource.evictable_size",
    "resource.protected_size",
    "resource.available_size",
]
PREFERRED_RANK = {n: i for i, n in enumerate(PREFERRED)}

GROUP_TIER = {
    "output_len": 0,
    "client_sampling": 1,
    "cache_hit": 2,
    "request_content": 2,
    "this_turn_prefill": 2,
    "reasoning": 2,
    "prompt_occupied": 2,
    "resource_pool": 3,
}

KIND = {s[0]: s[3] for s in SPECS}


def group_of(name: str) -> str:
    for g, spec in GROUPS.items():
        if name in spec["features"]:
            return g
    return "ungrouped"


def availability(name: str) -> tuple[int, str]:
    g = group_of(name)
    if g in ("replay_time",) or name.startswith("time."):
        return 9, "重放时钟，不当特征"
    if name.startswith("client."):
        if KIND.get(name) in {"len"}:
            return 1, "API 收包即可，序列取长度"
        return 0, "API 收包即可，原值标量"
    if name.startswith("tokenized."):
        return 2, "分词后"
    if name.startswith("sampling."):
        return 3, "Req.sampling_params，request_end 可读；常是 client 副本"
    if name.startswith("session."):
        return 8, "原生 Session，Chat 路径常缺失，evict 读不到"
    if name.startswith("last_node.") or name in {
        "req.last_node",
        "req.last_host_node",
        "req.best_match_node",
    }:
        return 5, "需 last_node 对象"
    if name.startswith("resource.") or name.startswith("scheduler."):
        return 6, "分配器/队列快照，清单为控制器专用"
    if KIND.get(name) == "len":
        return 4, "request_end 序列取长度"
    return 3, "request_end 调度器标量"


def latency(name: str) -> tuple[int, str]:
    if KIND.get(name) == "len":
        if name.startswith("last_node."):
            return 3, "走 Radix 节点再取序列长度"
        return 2, "对已有 list/str 取 len"
    if name.startswith("last_node."):
        return 3, "解引用 last_node"
    if name.startswith("resource.") or name.startswith("scheduler."):
        return 2, "读分配器/调度器快照"
    return 1, "已有标量，O(1)"


def spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    ok = np.isfinite(a) & np.isfinite(b)
    if int(ok.sum()) < 8:
        return None
    ra = a[ok].argsort().argsort().astype(np.float64)
    rb = b[ok].argsort().argsort().astype(np.float64)
    if ra.std() < 1e-12 or rb.std() < 1e-12:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def nuniq(col: np.ndarray) -> int:
    finite = col[np.isfinite(col)]
    if finite.size == 0:
        return 0
    return int(len(np.unique(np.round(finite, 12))))


def quality_row(name: str, col: np.ndarray, n_rows: int) -> dict:
    finite = np.isfinite(col)
    av, av_why = availability(name)
    lat, lat_why = latency(name)
    nu = nuniq(col)
    miss = float(1.0 - finite.mean()) if n_rows else 1.0
    g = group_of(name)
    id_like = bool(
        g in {"identity", "replay_time"}
        or name.endswith(".rid")
        or name.endswith(".id")
        or name.endswith("session_id")
        or any(s in name for s in (".parent", ".prev", ".next", ".swa_prev", ".swa_next"))
    )
    constant = nu <= 1
    return {
        "feature": name,
        "group": group_of(name),
        "kind": KIND.get(name),
        "miss_rate": miss,
        "n_unique": nu,
        "n_finite": int(finite.sum()),
        "std": float(np.nanstd(col)) if finite.any() else 0.0,
        "constant": constant,
        "id_like": id_like,
        "availability": av,
        "availability_why": av_why,
        "latency": lat,
        "latency_why": lat_why,
        "hard_excluded": group_of(name) in HARD_EXCLUDE_GROUPS,
        "controller_only": group_of(name) in CONTROLLER_GROUPS,
    }


def quality_key(q: dict) -> tuple:
    return (
        q["hard_excluded"],
        q["constant"],
        q["id_like"],
        q["miss_rate"],
        q["latency"],
        q["availability"],
        q.get("max_cross_rho") if q.get("max_cross_rho") is not None else 0.0,
        q["feature"],
    )


def cliques(names: list[str], rho: dict[tuple[str, str], float], thresh: float) -> list[list[str]]:
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            r = rho.get((a, b))
            if r is not None and abs(r) >= thresh:
                union(a, b)
    buckets: dict[str, list[str]] = {}
    for n in names:
        buckets.setdefault(find(n), []).append(n)
    return list(buckets.values())


def metrics(y, pred) -> dict:
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
        "--out",
        type=Path,
        default=REPO_ROOT / "experiments/session_return/lgbm/within_group_selection.json",
    )
    args = p.parse_args()

    names, X, y, d, sm = load_xy(args.run_dir, args.dump_file)
    idx = {n: i for i, n in enumerate(names)}
    obs = d == 1
    tr, va, te = sm["train"], sm["val"], sm["test"]
    leaky = set(GROUPS[LEAKY]["features"])
    official = [n for n in names if n not in leaky]
    official_idx = np.array([idx[n] for n in official], dtype=int)

    train_all = tr
    qmap = {n: quality_row(n, X[train_all, idx[n]], int(train_all.sum())) for n in names}

    # pairwise rho on train δ=1 for varying columns
    vary = [n for n in names if not qmap[n]["constant"]]
    pair_rho: dict[tuple[str, str], float] = {}
    cols = {n: X[tr & obs, idx[n]] for n in vary}
    for i, a in enumerate(vary):
        for b in vary[i + 1 :]:
            r = spearman(cols[a], cols[b])
            if r is not None:
                pair_rho[(a, b)] = pair_rho[(b, a)] = r

    for n in names:
        others = [
            abs(pair_rho[(n, m)])
            for m in vary
            if m != n and group_of(m) != group_of(n) and (n, m) in pair_rho
        ]
        qmap[n]["max_cross_rho"] = float(max(others)) if others else None
        qmap[n]["max_cross_partner"] = None
        if others:
            partner = max(
                (m for m in vary if m != n and group_of(m) != group_of(n) and (n, m) in pair_rho),
                key=lambda m: abs(pair_rho[(n, m)]),
            )
            qmap[n]["max_cross_partner"] = partner
            qmap[n]["max_cross_rho"] = float(abs(pair_rho[(n, partner)]))

    collapse = []
    representatives = []
    for gname, spec in GROUPS.items():
        feats = spec["features"]
        alive = [f for f in feats if not qmap[f]["constant"] and not qmap[f]["id_like"]]
        components = cliques(alive, pair_rho, 0.99) if alive else []
        picked = []
        for comp in components:
            ranked = sorted(
                comp,
                key=lambda f: (PREFERRED_RANK.get(f, 1000), quality_key(qmap[f])),
            )
            winner = ranked[0]
            picked.append(winner)
            collapse.append(
                {
                    "group": gname,
                    "clique": comp,
                    "kept": winner,
                    "dropped": [x for x in ranked[1:]],
                    "why": (
                        f"miss={qmap[winner]['miss_rate']:.3f} "
                        f"avail={qmap[winner]['availability']} "
                        f"lat={qmap[winner]['latency']} "
                        f"crossρ={qmap[winner]['max_cross_rho']}"
                    ),
                }
            )
        representatives.extend(picked)

    eligible = [
        n
        for n in representatives
        if group_of(n) not in HARD_EXCLUDE_GROUPS and not qmap[n]["constant"]
    ]
    eligible_core = [n for n in eligible if not qmap[n]["controller_only"]]
    eligible_ctrl = [n for n in eligible if qmap[n]["controller_only"]]

    fit_cache: dict[tuple[str, ...], dict] = {}

    def baseline_split(split: str):
        m = (va & obs) if split == "val" else (te & obs)
        return metrics(y[m], np.full(int(m.sum()), float(np.mean(y[tr & obs]))))

    def fit_names(keep_names: list[str]):
        key = tuple(keep_names)
        if key in fit_cache:
            return fit_cache[key]
        if not keep_names:
            out = {
                "val": baseline_split("val"),
                "test": baseline_split("test"),
                "n_features": 0,
                "best_iteration": 0,
            }
            fit_cache[key] = out
            return out
        keep = np.array([idx[n] for n in keep_names], dtype=int)
        model = fit_lgbm(
            X[tr & obs][:, keep],
            y[tr & obs],
            X[va & obs][:, keep],
            y[va & obs],
        )
        out = {}
        for split, mask in (("val", va & obs), ("test", te & obs)):
            pred = model.predict(X[mask][:, keep])
            out[split] = metrics(y[mask], pred)
        out["n_features"] = len(keep_names)
        out["best_iteration"] = int(model.best_iteration_ or model.n_estimators)
        fit_cache[key] = out
        return out

    full = fit_names(official)
    mean_tr = float(np.mean(y[tr & obs]))
    baseline = {
        s: metrics(y[m], np.full(int(m.sum()), mean_tr))
        for s, m in (("val", va & obs), ("test", te & obs))
    }

    def rest_plus(group: str, extra: list[str]) -> list[str]:
        drop = set(GROUPS[group]["features"])
        return [n for n in official if n not in drop] + extra

    combo_groups = [
        "output_len",
        "client_sampling",
        "cache_hit",
        "request_content",
        "this_turn_prefill",
        "reasoning",
        "prompt_occupied",
        "resource_pool",
    ]
    combos = []
    for gname in combo_groups:
        cands = [n for n in eligible if group_of(n) == gname]
        if gname == "output_len":
            # also test the duplicate length field, to confirm interchangeability
            for extra in ("req.output_ids",):
                if extra not in cands and extra in names:
                    cands = cands + [extra]
        if not cands:
            combos.append(
                {
                    "group": gname,
                    "candidates": [],
                    "runs": [
                        {
                            "kept": [],
                            "metrics": fit_names(rest_plus(gname, [])),
                        }
                    ],
                }
            )
            continue
        if len(cands) > 4:
            cands = sorted(cands, key=lambda f: quality_key(qmap[f]))[:4]
        runs = []
        for r in range(0, len(cands) + 1):
            for subset in itertools.combinations(cands, r):
                keep = rest_plus(gname, list(subset))
                met = fit_names(keep)
                runs.append(
                    {
                        "kept": list(subset),
                        "n_kept_in_group": len(subset),
                        "metrics": met,
                        "d_val": met["val"]["mae"] - full["val"]["mae"],
                        "d_test": met["test"]["mae"] - full["test"]["mae"],
                    }
                )
        runs.sort(key=lambda r: (r["metrics"]["val"]["mae"], r["metrics"]["test"]["mae"]))
        combos.append({"group": gname, "candidates": cands, "runs": runs})

    # Nested ladder follows PREFERRED, skipping ρ>=0.95 duplicates.
    allowed = set(eligible_core + eligible_ctrl)
    ladder = []
    skipped_dup = []
    for n in PREFERRED + [x for x in eligible_core + eligible_ctrl if x not in PREFERRED]:
        if n not in allowed or n in ladder:
            continue
        twin = None
        for p in ladder:
            r = pair_rho.get((n, p))
            if r is not None and abs(r) >= 0.95:
                twin = p
                break
        if twin is not None:
            skipped_dup.append({"feature": n, "duplicate_of": twin, "rho": pair_rho[(n, twin)]})
            continue
        ladder.append(n)
    for n in CONTROLLER_TAIL:
        if n in allowed and n not in ladder:
            ladder.append(n)

    budgets = [8, 12, 16, 20, 24]
    nested = {}
    for k in budgets:
        feats = ladder[: min(k, len(ladder))]
        met = fit_names(feats) if feats else None
        nested[str(k)] = {
            "n": len(feats),
            "features": feats,
            "padded_with_controller": any(qmap[f]["controller_only"] for f in feats),
            "metrics": met,
            "d_val_vs_full": None
            if met is None
            else float(met["val"]["mae"] - full["val"]["mae"]),
            "d_test_vs_full": None
            if met is None
            else float(met["test"]["mae"] - full["test"]["mae"]),
            "d_val_vs_mean": None
            if met is None
            else float(met["val"]["mae"] - baseline["val"]["mae"]),
            "d_test_vs_mean": None
            if met is None
            else float(met["test"]["mae"] - baseline["test"]["mae"]),
        }

    remaining = [n for n in eligible_core if n in set(PREFERRED) or n in ladder]
    greedy_path = []
    cur: list[str] = []
    pool = list(remaining)
    while pool and len(cur) < 8:
        best = None
        best_mae = None
        for n in pool:
            mae = fit_names(cur + [n])["val"]["mae"]
            if best_mae is None or mae < best_mae:
                best_mae = mae
                best = n
        if best is None:
            break
        cur = cur + [best]
        pool.remove(best)
        met = fit_names(cur)
        greedy_path.append(
            {
                "k": len(cur),
                "added": best,
                "val_mae": met["val"]["mae"],
                "test_mae": met["test"]["mae"],
            }
        )

    out = {
        "note": (
            "Within-group pick: least missing, then easiest online, then lowest "
            "latency, then least cross-group ρ. ρ>=0.95 skipped as duplicate. "
            "IDs / leaky cap / replay clock / native session / radix pointers excluded. "
            "Nested small is not an official freeze."
        ),
        "n_train_obs": int((tr & obs).sum()),
        "n_val_obs": int((va & obs).sum()),
        "n_test_obs": int((te & obs).sum()),
        "full_official_168": full,
        "mean_baseline": baseline,
        "quality": [qmap[n] for n in names],
        "collapse": collapse,
        "eligible_core": eligible_core,
        "eligible_controller": eligible_ctrl,
        "skipped_duplicate": skipped_dup,
        "ladder_order": ladder,
        "combo_ablation": combos,
        "nested_sets": nested,
        "greedy_forward_val": greedy_path,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print("eligible_core", eligible_core)
    print("skipped_dup", skipped_dup)
    print("ladder", ladder)
    for k, rec in nested.items():
        print(
            f"k={k:2s} n={rec['n']:2d} val={rec['metrics']['val']['mae']:.3f} "
            f"test={rec['metrics']['test']['mae']:.3f}  {rec['features']}"
        )
    print("greedy", [r["added"] for r in greedy_path])
    print("wrote", args.out)


if __name__ == "__main__":
    main()
