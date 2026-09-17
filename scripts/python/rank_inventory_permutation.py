#!/usr/bin/env python3
"""Permutation-rank every native inventory field (docs/模型输入特征统计.md §1–7).

Sequences become length. Objects become present/absent. Strings are factorized.
This is the only way LightGBM permutation can see the 150 inventory slots.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import mean_absolute_error

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
from rank_session_return_features import DEFAULT_RUN, load_client  # noqa: E402
from train_session_return_lgbm import fit_lgbm  # noqa: E402

EFFORT = {"none": 0.0, "low": 1.0, "medium": 2.0, "high": 3.0, "max": 4.0}


def get(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if cur is None or not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def as_num(value: Any) -> float | None:
    if value is None:
        return None
    if value is False:
        return 0.0
    if value is True:
        return 1.0
    if isinstance(value, (int, float)) and np.isfinite(value):
        return float(value)
    return None


def as_len(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, dict, str)):
        return float(len(value))
    return None


def as_present(value: Any) -> float:
    return 0.0 if value is None else 1.0


def as_cat(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return type(value).__name__
    return str(value)


# (name, dump_root, path, kind)  kind: num|len|cat|present|bool|effort
# dump_root: client | event
SPECS: list[tuple[str, str, str, str]] = [
    # §1 client
    ("client.messages", "client", "messages", "len"),
    ("client.input_ids", "client", "input_ids", "len"),
    ("client.model", "client", "model", "cat"),
    ("client.tools", "client", "tools", "len"),
    ("client.tool_choice", "client", "tool_choice", "cat"),
    ("client.parallel_tool_calls", "client", "parallel_tool_calls", "bool"),
    ("client.response_format", "client", "response_format", "present"),
    ("client.reasoning_effort", "client", "reasoning_effort", "effort"),
    ("client.task", "client", "task", "cat"),
    ("client.user", "client", "user", "cat"),
    ("client.max_tokens", "client", "max_tokens", "num"),
    ("client.max_completion_tokens", "client", "max_completion_tokens", "num"),
    ("client.min_tokens", "client", "min_tokens", "num"),
    ("client.n", "client", "n", "num"),
    ("client.stop", "client", "stop", "len"),
    ("client.stop_token_ids", "client", "stop_token_ids", "len"),
    ("client.stop_regex", "client", "stop_regex", "len"),
    ("client.temperature", "client", "temperature", "num"),
    ("client.top_p", "client", "top_p", "num"),
    ("client.top_k", "client", "top_k", "num"),
    ("client.min_p", "client", "min_p", "num"),
    ("client.frequency_penalty", "client", "frequency_penalty", "num"),
    ("client.presence_penalty", "client", "presence_penalty", "num"),
    ("client.repetition_penalty", "client", "repetition_penalty", "num"),
    ("client.seed", "client", "seed", "num"),
    ("client.ignore_eos", "client", "ignore_eos", "bool"),
    ("client.no_stop_trim", "client", "no_stop_trim", "bool"),
    ("client.continue_final_message", "client", "continue_final_message", "bool"),
    ("client.stream", "client", "stream", "bool"),
    ("client.extra_key", "client", "extra_key", "cat"),
    ("client.cache_salt", "client", "cache_salt", "cat"),
    ("client.lora_path", "client", "lora_path", "cat"),
    ("client.priority", "client", "priority", "num"),
    ("client.session_params", "client", "session_params", "present"),
    ("client.rid", "client", "rid", "cat"),
    ("client.image_content", "client", "image", "present"),
    ("client.audio_content", "client", "audio", "present"),
    ("client.video_content", "client", "video", "present"),
    ("client.max_dynamic_patch", "client", "max_dynamic_patch", "num"),
    ("client.min_dynamic_patch", "client", "min_dynamic_patch", "num"),
    ("client.use_audio_in_video", "client", "use_audio_in_video", "bool"),
    # §2 tokenized
    ("tokenized.input_text", "event", "tokenized.input_text", "len"),
    ("tokenized.input_ids", "event", "tokenized.input_ids", "len"),
    ("tokenized.mm_inputs", "event", "tokenized.mm_inputs", "present"),
    ("tokenized.sampling_params", "event", "tokenized.sampling_params", "present"),
    ("tokenized.session_params", "event", "tokenized.session_params", "present"),
    ("tokenized.extra_key", "event", "tokenized.extra_key", "cat"),
    ("tokenized.routing_key", "event", "tokenized.routing_key", "cat"),
    ("tokenized.priority", "event", "tokenized.priority", "num"),
    ("tokenized.stream", "event", "tokenized.stream", "bool"),
    ("tokenized.time_stats", "event", "tokenized.time_stats", "present"),
    # §3 req
    ("req.rid", "event", "req.rid", "cat"),
    ("req.origin_input_ids", "event", "req.origin_input_ids", "len"),
    ("req.origin_input_ids_unpadded", "event", "req.origin_input_ids_unpadded", "len"),
    ("req.output_ids", "event", "req.output_ids", "len"),
    ("req.full_untruncated_fill_ids", "event", "req.full_untruncated_fill_ids", "len"),
    ("req.fill_len", "event", "req.fill_len", "num"),
    ("req.input_embeds", "event", "req.input_embeds", "present"),
    ("req.multimodal_inputs", "event", "req.multimodal_inputs", "present"),
    ("req.sampling_params", "event", "req.sampling_params", "present"),
    ("req.session", "event", "req.session", "present"),
    ("req.extra_key", "event", "req.extra_key", "cat"),
    ("req.lora_id", "event", "req.lora_id", "cat"),
    ("req.routing_key", "event", "req.routing_key", "cat"),
    ("req.priority", "event", "req.priority", "num"),
    ("req.require_reasoning", "event", "req.require_reasoning", "bool"),
    ("req._is_reasoning_over", "event", "req._is_reasoning_over", "bool"),
    ("req.reasoning_tokens", "event", "req.reasoning_tokens", "num"),
    ("req.finished_reason", "event", "req.finished_reason.type", "cat"),
    ("req.finished_len", "event", "req.finished_len", "num"),
    ("req.to_finish", "event", "req.to_finish", "present"),
    ("req.prefix_indices", "event", "req.prefix_indices", "len"),
    ("req.last_node", "event", "req.last_node", "present"),
    ("req.last_host_node", "event", "req.last_host_node", "present"),
    ("req.best_match_node", "event", "req.best_match_node", "present"),
    ("req.host_hit_length", "event", "req.host_hit_length", "num"),
    ("req.swa_host_hit_length", "event", "req.swa_host_hit_length", "num"),
    ("req.mamba_host_hit_length", "event", "req.mamba_host_hit_length", "num"),
    ("req.num_matched_prefix_tokens", "event", "req.num_matched_prefix_tokens", "num"),
    ("req.storage_hit_length", "event", "req.storage_hit_length", "num"),
    ("req.cache_protected_len", "event", "req.cache_protected_len", "num"),
    ("req.cached_tokens", "event", "req.cached_tokens", "num"),
    ("req.cached_tokens_device", "event", "req.cached_tokens_device", "num"),
    ("req.cached_tokens_host", "event", "req.cached_tokens_host", "num"),
    ("req.cached_tokens_storage", "event", "req.cached_tokens_storage", "num"),
    ("req.kv_committed_len", "event", "req.kv_committed_len", "num"),
    ("req.kv_allocated_len", "event", "req.kv_allocated_len", "num"),
    ("req.swa_evicted_seqlen", "event", "req.swa_evicted_seqlen", "num"),
    ("req.extend_input_len", "event", "req.extend_input_len", "num"),
    ("req.stream", "event", "req.stream", "bool"),
    # sampling inner (listed under client gen params, read from req)
    ("sampling.max_new_tokens", "event", "req.sampling_params.max_new_tokens", "num"),
    ("sampling.temperature", "event", "req.sampling_params.temperature", "num"),
    ("sampling.top_p", "event", "req.sampling_params.top_p", "num"),
    ("sampling.top_k", "event", "req.sampling_params.top_k", "num"),
    ("sampling.min_p", "event", "req.sampling_params.min_p", "num"),
    ("sampling.frequency_penalty", "event", "req.sampling_params.frequency_penalty", "num"),
    ("sampling.presence_penalty", "event", "req.sampling_params.presence_penalty", "num"),
    ("sampling.repetition_penalty", "event", "req.sampling_params.repetition_penalty", "num"),
    ("sampling.n", "event", "req.sampling_params.n", "num"),
    ("sampling.ignore_eos", "event", "req.sampling_params.ignore_eos", "bool"),
    ("sampling.no_stop_trim", "event", "req.sampling_params.no_stop_trim", "bool"),
    ("sampling.min_new_tokens", "event", "req.sampling_params.min_new_tokens", "num"),
    ("sampling.seed", "event", "req.sampling_params.sampling_seed", "num"),
    ("sampling.stop_strs", "event", "req.sampling_params.stop_strs", "len"),
    ("sampling.stop_token_ids", "event", "req.sampling_params.stop_token_ids", "len"),
    ("sampling.stop_regex_strs", "event", "req.sampling_params.stop_regex_strs", "len"),
    # §4 timestamps
    ("time.created_time", "event", "req.time_stats.created_time", "num"),
    ("time.tokenize_finish_time", "event", "req.time_stats.tokenize_finish_time", "num"),
    ("time.api_server_dispatch_time", "event", "req.time_stats.api_server_dispatch_time", "num"),
    ("time.api_server_dispatch_finish_time", "event", "req.time_stats.api_server_dispatch_finish_time", "num"),
    ("time.first_token_time", "event", "req.time_stats.first_token_time", "num"),
    ("time.last_time", "event", "req.time_stats.last_time", "num"),
    ("time.finished_time", "event", "req.time_stats.finished_time", "num"),
    ("time.response_sent_to_client_time", "event", "req.time_stats.response_sent_to_client_time", "num"),
    ("time.scheduler_recv_time", "event", "req.time_stats.scheduler_recv_time", "num"),
    ("time.wait_queue_entry_time", "event", "req.time_stats.wait_queue_entry_time", "num"),
    ("time.forward_entry_time", "event", "req.time_stats.forward_entry_time", "num"),
    ("time.prefill_finished_time", "event", "req.time_stats.prefill_finished_time", "num"),
    ("time.completion_time", "event", "req.time_stats.completion_time", "num"),
    # §5 session
    ("session.session_id", "event", "req.session.session_id", "cat"),
    ("session.capacity_of_str_len", "event", "req.session.capacity_of_str_len", "num"),
    ("session.streaming", "event", "req.session.streaming", "bool"),
    ("session.timeout", "event", "req.session.timeout", "num"),
    ("session.last_active_time", "event", "req.session.last_active_time", "num"),
    ("session.req_nodes", "event", "req.session.req_nodes", "len"),
    ("session.close_on_finish", "event", "req.session.close_on_finish", "bool"),
    ("session._inflight", "event", "req.session._inflight", "bool"),
    # §6 last_node
    ("last_node.children", "event", "req.last_node.children", "len"),
    ("last_node.parent", "event", "req.last_node.parent_id", "num"),
    ("last_node.key", "event", "req.last_node.key", "present"),
    ("last_node.key.token_ids", "event", "req.last_node.key.token_ids", "len"),
    ("last_node.key.extra_key", "event", "req.last_node.key.extra_key", "cat"),
    ("last_node.key.is_bigram", "event", "req.last_node.key.is_bigram", "bool"),
    ("last_node.value", "event", "req.last_node.value", "len"),
    ("last_node.last_access_time", "event", "req.last_node.last_access_time", "num"),
    ("last_node.hit_count", "event", "req.last_node.hit_count", "num"),
    ("last_node.host_value", "event", "req.last_node.host_value", "len"),
    ("last_node.hash_value", "event", "req.last_node.hash_value", "len"),
    ("last_node.id", "event", "req.last_node.id", "num"),
    ("last_node.lock_ref", "event", "req.last_node.lock_ref", "num"),
    ("last_node.creation_time", "event", "req.last_node.creation_time", "num"),
    ("last_node.host_ref_counter", "event", "req.last_node.host_ref_counter", "num"),
    ("last_node.write_through_pending_id", "event", "req.last_node.write_through_pending_id", "cat"),
    ("last_node.priority", "event", "req.last_node.priority", "num"),
    ("last_node.swa_tombstone", "event", "req.last_node.swa_tombstone", "bool"),
    ("last_node.full_lock_ref", "event", "req.last_node.full_lock_ref", "num"),
    ("last_node.swa_lock_ref", "event", "req.last_node.swa_lock_ref", "num"),
    ("last_node.prev", "event", "req.last_node.prev_id", "num"),
    ("last_node.next", "event", "req.last_node.next_id", "num"),
    ("last_node.swa_prev", "event", "req.last_node.swa_prev_id", "num"),
    ("last_node.swa_next", "event", "req.last_node.swa_next_id", "num"),
    ("last_node.swa_uuid", "event", "req.last_node.swa_uuid", "cat"),
    # §7 resource / queues
    ("resource.num_tokens", "event", "resource.num_tokens", "num"),
    ("resource.swa_num_tokens", "event", "resource.swa_num_tokens", "num"),
    ("resource.size", "event", "resource.size", "num"),
    ("resource.page_size", "event", "resource.page_size", "num"),
    ("resource.available_size", "event", "resource.available_size", "num"),
    ("resource.evictable_size", "event", "resource.evictable_size", "num"),
    ("resource.protected_size", "event", "resource.protected_size", "num"),
    ("resource.full_available_size", "event", "resource.full_available_size", "num"),
    ("resource.swa_available_size", "event", "resource.swa_available_size", "num"),
    ("resource.full_evictable_size_", "event", "resource.full_evictable_size_", "num"),
    ("resource.swa_evictable_size_", "event", "resource.swa_evictable_size_", "num"),
    ("resource.full_protected_size_", "event", "resource.full_protected_size_", "num"),
    ("resource.swa_protected_size_", "event", "resource.swa_protected_size_", "num"),
    ("resource.sliding_window_size", "event", "resource.sliding_window_size", "num"),
    ("scheduler.waiting_queue", "event", "scheduler.waiting_queue", "len"),
    ("scheduler.running_batch", "event", "scheduler.running_batch", "len"),
    ("scheduler.cur_batch", "event", "scheduler.cur_batch", "len"),
]


def coerce(value: Any, kind: str) -> float | str | None:
    if kind == "len":
        return as_len(value)
    if kind == "present":
        return as_present(value)
    if kind == "bool":
        return as_num(value)
    if kind == "num":
        return as_num(value)
    if kind == "effort":
        if value is None:
            return None
        return EFFORT.get(str(value).lower(), None)
    if kind == "cat":
        return as_cat(value)
    raise ValueError(kind)


def extract_row(client_rec: dict, event: dict) -> dict[str, float | str | None]:
    cr = client_rec.get("client_request") or {}
    cr = {**cr, "rid": client_rec.get("trace_id")}
    row = {}
    for name, root, path, kind in SPECS:
        src = cr if root == "client" else event
        row[name] = coerce(get(src, path), kind)
    return row


def load_dump_map(path: Path) -> dict[str, dict]:
    out = {}
    with path.open(buffering=1024 * 1024) as f:
        for line in f:
            if '"event": "request_end"' not in line[:300]:
                continue
            ev = json.loads(line)
            rid = str(ev.get("rid") or "")
            if rid:
                out[rid] = ev
    return out


def factorize(rows: list[dict], names: list[str], train_ids: list[int]) -> None:
    for name in names:
        vals = [rows[i][name] for i in range(len(rows))]
        if not any(isinstance(v, str) for v in vals):
            continue
        mapping = {}
        next_id = 0
        for i in train_ids:
            v = rows[i][name]
            if isinstance(v, str) and v not in mapping:
                mapping[v] = float(next_id)
                next_id += 1
        for i, v in enumerate(vals):
            if v is None:
                rows[i][name] = None
            elif isinstance(v, str):
                rows[i][name] = mapping.get(v, -1.0)
            else:
                rows[i][name] = float(v) if isinstance(v, (int, float)) else None


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
    dump = load_dump_map(args.run_dir / args.dump_file)
    names = [s[0] for s in SPECS]
    ids = sorted(
        rid for rid, rec in clients.items() if rid in dump and rec.get("small_split")
    )
    raw_rows = []
    splits, ys, ds = [], [], []
    for rid in ids:
        rec = clients[rid]
        raw_rows.append(extract_row(rec, dump[rid]))
        splits.append(rec["small_split"])
        ys.append(float(rec["tau_s_small"]))
        ds.append(int(rec["delta_small"]))
    y = np.array(ys, dtype=np.float64)
    d = np.array(ds, dtype=np.int32)
    train_idx = [i for i, s in enumerate(splits) if s == "train"]
    factorize(raw_rows, names, train_idx)
    X = np.array(
        [[np.nan if r[n] is None else float(r[n]) for n in names] for r in raw_rows],
        dtype=np.float64,
    )

    def mask(split: str) -> np.ndarray:
        return np.array([s == split for s in splits])

    tr, va, te = mask("train"), mask("val"), mask("test")
    obs_tr, obs_va, obs_te = d == 1, d == 1, d == 1
    model = fit_lgbm(X[tr & obs_tr], y[tr & obs_tr], X[va & obs_va], y[va & obs_va])
    gain = model.booster_.feature_importance(importance_type="gain")
    intact = {
        "val": float(mean_absolute_error(y[va & obs_va], model.predict(X[va & obs_va]))),
        "test": float(mean_absolute_error(y[te & obs_te], model.predict(X[te & obs_te]))),
    }
    evals = {
        "val": (X[va & obs_va], y[va & obs_va]),
        "test": (X[te & obs_te], y[te & obs_te]),
    }

    ranking = []
    Xtr = X[tr]
    for j, name in enumerate(names):
        finite = Xtr[:, j][np.isfinite(Xtr[:, j])]
        nuniq = int(len(np.unique(np.round(finite, 12)))) if finite.size else 0
        n_miss = int(np.isnan(Xtr[:, j]).sum())
        spec = SPECS[j]
        row = {
            "rank": 0,
            "feature": name,
            "kind": spec[3],
            "path": spec[2],
            "gain": float(gain[j]),
            "n_unique_train": nuniq,
            "n_missing_train": n_miss,
            "flags": [],
        }
        if nuniq < 2:
            row["flags"].append("constant_or_empty")
        if spec[3] == "len":
            row["flags"].append("sequence_as_length")
        if spec[2].startswith("req.time_stats") or name.startswith("time."):
            row["flags"].append("replay_timestamp")
        if "max_new_tokens" in name:
            row["flags"].append("leaky_replay_cap")
        rng = np.random.default_rng(args.seed + j)
        for split, (Xs, ys_) in evals.items():
            deltas = np.empty(args.n_repeats, dtype=np.float64)
            n = len(Xs)
            for i in range(args.n_repeats):
                perm = rng.permutation(n)
                Xp = Xs.copy()
                Xp[:, j] = Xs[perm, j]
                deltas[i] = float(mean_absolute_error(ys_, model.predict(Xp))) - intact[split]
            row[split] = {
                "delta_mae_mean": float(np.mean(deltas)),
                "delta_mae_std": float(np.std(deltas, ddof=1)),
                "frac_positive": float(np.mean(deltas > 0)),
            }
        ranking.append(row)
    ranking.sort(key=lambda r: (-r["val"]["delta_mae_mean"], -r["gain"], r["feature"]))
    for i, r in enumerate(ranking, 1):
        r["rank"] = i

    out = {
        "n_inventory": len(names),
        "n_repeats": args.n_repeats,
        "intact_mae": intact,
        "n_observed": {
            "train": int((tr & obs_tr).sum()),
            "val": int((va & obs_va).sum()),
            "test": int((te & obs_te).sum()),
        },
        "best_iteration": int(model.best_iteration_ or model.n_estimators),
        "ranking": ranking,
        "note": (
            "All inventory §1–7 slots. Sequences ranked via length, objects via "
            "present/absent, strings factorized. Nested last_node stands for §6. "
            "Do not freeze from nested small val."
        ),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "permutation_inventory.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print("n_specs", len(names), "intact", intact)
    for r in ranking[:30]:
        print(
            f"{r['rank']:3d} {r['feature']:42s} "
            f"val {r['val']['delta_mae_mean']:+.4f}  test {r['test']['delta_mae_mean']:+.4f}  "
            f"uniq {r['n_unique_train']:5d}  {','.join(r['flags']) or '-'}"
        )
    print("wrote", path)


if __name__ == "__main__":
    main()
