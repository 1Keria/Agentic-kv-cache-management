#!/usr/bin/env python3
"""Full inventory pipeline: group → grouped permutation → group ablation.

Covers every slot in rank_inventory_permutation.SPECS. The official full
model drops sampling.max_new_tokens (replay completion cap). That leaky
column is still its own group, evaluated in a model that includes it.
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
from rank_inventory_permutation import (  # noqa: E402
    SPECS,
    extract_row,
    factorize,
    load_dump_map,
)
from rank_session_return_features import DEFAULT_RUN, load_client  # noqa: E402
from train_session_return_lgbm import fit_lgbm  # noqa: E402

LEAKY = "leaky_replay_cap"

GROUPS: dict[str, dict] = {
    "leaky_replay_cap": {
        "why": "sampling.max_new_tokens = logged completion, not serving max_tokens",
        "features": ["sampling.max_new_tokens"],
    },
    "output_len": {
        "why": "This request's actual completion length / stop",
        "features": [
            "req.finished_len",
            "req.output_ids",
            "req.finished_reason",
            "req.to_finish",
        ],
    },
    "prompt_occupied": {
        "why": "Occupied KV / prompt length; fill_len ρ=1 with cache_protected/kv",
        "features": [
            "client.input_ids",
            "tokenized.input_text",
            "tokenized.input_ids",
            "req.origin_input_ids",
            "req.origin_input_ids_unpadded",
            "req.full_untruncated_fill_ids",
            "req.fill_len",
            "req.prefix_indices",
            "req.cache_protected_len",
            "req.kv_committed_len",
            "req.kv_allocated_len",
            "last_node.key.token_ids",
            "last_node.value",
        ],
    },
    "this_turn_prefill": {
        "why": "Tokens prefilled this turn",
        "features": ["req.extend_input_len"],
    },
    "cache_hit": {
        "why": "Prefix cache hit counters by layer",
        "features": [
            "req.cached_tokens",
            "req.cached_tokens_device",
            "req.cached_tokens_host",
            "req.cached_tokens_storage",
            "req.host_hit_length",
            "req.swa_host_hit_length",
            "req.mamba_host_hit_length",
            "req.num_matched_prefix_tokens",
            "req.storage_hit_length",
            "req.swa_evicted_seqlen",
        ],
    },
    "client_sampling": {
        "why": "Generation knobs (client + req.sampling copies)",
        "features": [
            "client.max_tokens",
            "client.max_completion_tokens",
            "client.min_tokens",
            "client.n",
            "client.temperature",
            "client.top_p",
            "client.top_k",
            "client.min_p",
            "client.seed",
            "sampling.temperature",
            "sampling.top_p",
            "sampling.top_k",
            "sampling.min_p",
            "sampling.n",
            "sampling.min_new_tokens",
            "sampling.seed",
        ],
    },
    "sampling_stop_penalty": {
        "why": "Stop conditions and repetition penalties",
        "features": [
            "client.stop",
            "client.stop_token_ids",
            "client.stop_regex",
            "client.frequency_penalty",
            "client.presence_penalty",
            "client.repetition_penalty",
            "client.ignore_eos",
            "client.no_stop_trim",
            "client.continue_final_message",
            "sampling.frequency_penalty",
            "sampling.presence_penalty",
            "sampling.repetition_penalty",
            "sampling.ignore_eos",
            "sampling.no_stop_trim",
            "sampling.stop_strs",
            "sampling.stop_token_ids",
            "sampling.stop_regex_strs",
        ],
    },
    "request_content": {
        "why": "Request body / tools / stream flags (sequences as length)",
        "features": [
            "client.messages",
            "client.tools",
            "client.model",
            "client.tool_choice",
            "client.parallel_tool_calls",
            "client.response_format",
            "client.reasoning_effort",
            "client.task",
            "client.stream",
            "req.stream",
            "tokenized.stream",
        ],
    },
    "reasoning": {
        "why": "Reasoning state of this request",
        "features": [
            "req.reasoning_tokens",
            "req._is_reasoning_over",
            "req.require_reasoning",
        ],
    },
    "multimodal": {
        "why": "Image/audio/video and mm containers",
        "features": [
            "client.image_content",
            "client.audio_content",
            "client.video_content",
            "client.max_dynamic_patch",
            "client.min_dynamic_patch",
            "client.use_audio_in_video",
            "tokenized.mm_inputs",
            "req.input_embeds",
            "req.multimodal_inputs",
        ],
    },
    "identity": {
        "why": "IDs, extra_key, LoRA, routing, priority — not τ semantics",
        "features": [
            "client.user",
            "client.extra_key",
            "client.cache_salt",
            "client.lora_path",
            "client.priority",
            "client.session_params",
            "client.rid",
            "tokenized.extra_key",
            "tokenized.routing_key",
            "tokenized.priority",
            "tokenized.session_params",
            "req.rid",
            "req.extra_key",
            "req.lora_id",
            "req.routing_key",
            "req.priority",
        ],
    },
    "container_flags": {
        "why": "Object present/absent only",
        "features": ["tokenized.sampling_params", "req.sampling_params"],
    },
    "replay_time": {
        "why": "Replay-clock timestamps; not original GLM start_time",
        "features": [
            "tokenized.time_stats",
            "time.created_time",
            "time.tokenize_finish_time",
            "time.api_server_dispatch_time",
            "time.api_server_dispatch_finish_time",
            "time.first_token_time",
            "time.last_time",
            "time.finished_time",
            "time.response_sent_to_client_time",
            "time.scheduler_recv_time",
            "time.wait_queue_entry_time",
            "time.forward_entry_time",
            "time.prefill_finished_time",
            "time.completion_time",
            "last_node.last_access_time",
            "last_node.creation_time",
        ],
    },
    "native_session": {
        "why": "SGLang Session object; usually missing on Chat",
        "features": [
            "req.session",
            "session.session_id",
            "session.capacity_of_str_len",
            "session.streaming",
            "session.timeout",
            "session.last_active_time",
            "session.req_nodes",
            "session.close_on_finish",
            "session._inflight",
        ],
    },
    "radix_node": {
        "why": "last_node structure / lock / LRU pointers (not token length)",
        "features": [
            "req.last_node",
            "req.last_host_node",
            "req.best_match_node",
            "last_node.children",
            "last_node.parent",
            "last_node.key",
            "last_node.key.extra_key",
            "last_node.key.is_bigram",
            "last_node.host_value",
            "last_node.hash_value",
            "last_node.id",
            "last_node.hit_count",
            "last_node.lock_ref",
            "last_node.host_ref_counter",
            "last_node.write_through_pending_id",
            "last_node.priority",
            "last_node.swa_tombstone",
            "last_node.full_lock_ref",
            "last_node.swa_lock_ref",
            "last_node.prev",
            "last_node.next",
            "last_node.swa_prev",
            "last_node.swa_next",
            "last_node.swa_uuid",
        ],
    },
    "resource_pool": {
        "why": "Allocator / queue snapshot; inventory: controller-only",
        "features": [
            "resource.num_tokens",
            "resource.swa_num_tokens",
            "resource.size",
            "resource.page_size",
            "resource.available_size",
            "resource.evictable_size",
            "resource.protected_size",
            "resource.full_available_size",
            "resource.swa_available_size",
            "resource.full_evictable_size_",
            "resource.swa_evictable_size_",
            "resource.full_protected_size_",
            "resource.swa_protected_size_",
            "resource.sliding_window_size",
            "scheduler.waiting_queue",
            "scheduler.running_batch",
            "scheduler.cur_batch",
        ],
    },
}


def validate_groups(names: list[str]) -> None:
    flat = []
    for spec in GROUPS.values():
        flat.extend(spec["features"])
    missing = sorted(set(names) - set(flat))
    extra = sorted(set(flat) - set(names))
    dup = sorted({f for f in flat if flat.count(f) > 1})
    if missing or extra or dup:
        raise SystemExit(
            json.dumps({"missing": missing, "extra": extra, "dup": dup}, indent=2)
        )


def score(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "r2": float(r2_score(y, pred)),
    }


def perm_deltas(model, X, y, cols: np.ndarray, n_repeats: int, seed: int) -> np.ndarray:
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


def load_xy(run_dir: Path, dump_file: str):
    clients = load_client(run_dir / "client" / "small_2200.client.jsonl")
    dump = load_dump_map(run_dir / dump_file)
    names = [s[0] for s in SPECS]
    validate_groups(names)
    ids = sorted(
        rid for rid, rec in clients.items() if rid in dump and rec.get("small_split")
    )
    raw, splits, ys, ds = [], [], [], []
    for rid in ids:
        rec = clients[rid]
        raw.append(extract_row(rec, dump[rid]))
        splits.append(rec["small_split"])
        ys.append(float(rec["tau_s_small"]))
        ds.append(int(rec["delta_small"]))
    train_idx = [i for i, s in enumerate(splits) if s == "train"]
    factorize(raw, names, train_idx)
    X = np.array(
        [[np.nan if r[n] is None else float(r[n]) for n in names] for r in raw],
        dtype=np.float64,
    )
    y = np.array(ys, dtype=np.float64)
    d = np.array(ds, dtype=np.int32)
    split_m = {s: np.array([v == s for v in splits]) for s in ("train", "val", "test")}
    return names, X, y, d, split_m


def cols_of(names: list[str], feats: list[str]) -> np.ndarray:
    idx = {n: i for i, n in enumerate(names)}
    return np.array([idx[f] for f in feats], dtype=int)


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
    names, X, y, d, sm = load_xy(args.run_dir, args.dump_file)
    obs = d == 1
    tr, va, te = sm["train"], sm["val"], sm["test"]
    leaky_feats = GROUPS[LEAKY]["features"]
    leaky_cols = set(cols_of(names, leaky_feats).tolist())
    base_keep = np.array([j for j in range(len(names)) if j not in leaky_cols], dtype=int)
    all_keep = np.arange(len(names), dtype=int)

    def fit(keep: np.ndarray):
        return fit_lgbm(
            X[tr & obs][:, keep],
            y[tr & obs],
            X[va & obs][:, keep],
            y[va & obs],
        )

    base_model = fit(base_keep)
    leaky_model = fit(all_keep)
    evals_idx = {"val": va & obs, "test": te & obs}

    def metrics_on(model, keep, split):
        m = evals_idx[split]
        return score(y[m], model.predict(X[m][:, keep]))

    base_metrics = {s: metrics_on(base_model, base_keep, s) for s in evals_idx}
    leaky_metrics = {s: metrics_on(leaky_model, all_keep, s) for s in evals_idx}
    mean_tr = float(np.mean(y[tr & obs]))
    baseline = {
        s: score(y[evals_idx[s]], np.full(int(evals_idx[s].sum()), mean_tr))
        for s in evals_idx
    }

    results = []
    seed = args.seed
    for gname, spec in GROUPS.items():
        feats = spec["features"]
        is_leaky = gname == LEAKY
        model = leaky_model if is_leaky else base_model
        keep = all_keep if is_leaky else base_keep
        name_to_pos = {names[j]: k for k, j in enumerate(keep)}
        local_cols = np.array([name_to_pos[f] for f in feats if f in name_to_pos], dtype=int)
        row = {
            "group": gname,
            "why": spec["why"],
            "features": feats,
            "n_features": len(feats),
            "official_model": "with_leaky" if is_leaky else "no_leaky",
        }
        # permutation on the model that contains this group
        Xmap = {s: X[evals_idx[s]][:, keep] for s in evals_idx}
        ymap = {s: y[evals_idx[s]] for s in evals_idx}
        intact = {s: float(mean_absolute_error(ymap[s], model.predict(Xmap[s]))) for s in evals_idx}
        perm = {}
        for s in evals_idx:
            deltas = perm_deltas(
                model, Xmap[s], ymap[s], local_cols, args.n_repeats, seed
            )
            perm[s] = summarize(deltas, intact[s])
            seed += 1
        row["permutation"] = perm

        # ablation: retrain without the group
        if is_leaky:
            without_keep = base_keep
            without_model = base_model
        else:
            drop = set(cols_of(names, feats).tolist())
            without_keep = np.array([j for j in base_keep if j not in drop], dtype=int)
            without_model = fit(without_keep)
        without_metrics = {s: metrics_on(without_model, without_keep, s) for s in evals_idx}
        full_m = leaky_metrics if is_leaky else base_metrics
        row["ablation"] = {
            "n_kept": int(len(without_keep)),
            "metrics": without_metrics,
            "delta_mae": {
                s: float(without_metrics[s]["mae"] - full_m[s]["mae"]) for s in evals_idx
            },
            "delta_rmse": {
                s: float(without_metrics[s]["rmse"] - full_m[s]["rmse"]) for s in evals_idx
            },
            "delta_r2": {
                s: float(without_metrics[s]["r2"] - full_m[s]["r2"]) for s in evals_idx
            },
        }
        results.append(row)

    results.sort(key=lambda r: -r["ablation"]["delta_mae"]["val"])
    out = {
        "n_slots": len(names),
        "n_groups": len(GROUPS),
        "n_repeats": args.n_repeats,
        "n_observed": {s: int(evals_idx[s].sum()) for s in evals_idx},
        "full_no_leaky": {
            "n_features": int(len(base_keep)),
            "best_iteration": int(base_model.best_iteration_ or base_model.n_estimators),
            "metrics": base_metrics,
        },
        "full_with_leaky": {
            "n_features": int(len(all_keep)),
            "best_iteration": int(leaky_model.best_iteration_ or leaky_model.n_estimators),
            "metrics": leaky_metrics,
        },
        "mean_baseline": baseline,
        "groups": results,
        "note": (
            "Pipeline on all inventory slots: group → 40× grouped permutation "
            "→ leave-one-group-out retrain. Official full model excludes "
            "sampling.max_new_tokens. Sequences ranked as length. "
            "Nested small val/test; do not freeze."
        ),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "inventory_group_pipeline.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print("full no-leaky MAE", {k: v["mae"] for k, v in base_metrics.items()})
    print("full with-leaky MAE", {k: v["mae"] for k, v in leaky_metrics.items()})
    print(f"{'group':22s} {'perm val':>10} {'perm test':>10} {'abl val':>10} {'abl test':>10} n")
    for r in results:
        print(
            f"{r['group']:22s} "
            f"{r['permutation']['val']['delta_mae_mean']:+10.4f} "
            f"{r['permutation']['test']['delta_mae_mean']:+10.4f} "
            f"{r['ablation']['delta_mae']['val']:+10.4f} "
            f"{r['ablation']['delta_mae']['test']:+10.4f} "
            f"{r['n_features']:3d}"
        )
    print("wrote", path)


if __name__ == "__main__":
    main()
