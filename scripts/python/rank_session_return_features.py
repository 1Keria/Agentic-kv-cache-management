#!/usr/bin/env python3
"""Univariate Harrell C-index ranking of native scalars vs remaining return time.

Diagnosis only: rank on small-train labels (right-censored). Do not freeze
features from this small nested split. Replay-clock ages are excluded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN = (
    REPO_ROOT
    / "experiments/session_return/replay_small/run_20260916_012751"
)

REQ_FIELDS = (
    "fill_len",
    "priority",
    "require_reasoning",
    "reasoning_tokens",
    "_is_reasoning_over",
    "host_hit_length",
    "swa_host_hit_length",
    "mamba_host_hit_length",
    "num_matched_prefix_tokens",
    "storage_hit_length",
    "cache_protected_len",
    "cached_tokens",
    "cached_tokens_device",
    "cached_tokens_host",
    "cached_tokens_storage",
    "kv_committed_len",
    "kv_allocated_len",
    "swa_evicted_seqlen",
    "extend_input_len",
    "stream",
    "finished_len",
)
NODE_FIELDS = ("hit_count", "lock_ref", "host_ref_counter", "priority")
SAMPLE_FIELDS = (
    "max_new_tokens",
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "frequency_penalty",
    "presence_penalty",
    "repetition_penalty",
    "n",
    "ignore_eos",
    "min_new_tokens",
)
RESOURCE_FIELDS = (
    "page_size",
    "size",
    "available_size",
    "evictable_size",
    "protected_size",
)
GROUPS = {
    "req": REQ_FIELDS,
    "last_node": NODE_FIELDS,
    "sampling": SAMPLE_FIELDS,
    "resource": RESOURCE_FIELDS,
}


def to_float(value: Any) -> float | None:
    if value is None or value is False:
        return 0.0 if value is False else None
    if value is True:
        return 1.0
    if isinstance(value, (int, float)) and np.isfinite(value):
        return float(value)
    return None


EFFORT = {"none": 0.0, "low": 1.0, "medium": 2.0, "high": 3.0, "max": 4.0}


def client_features(rec: dict[str, Any]) -> dict[str, float | None]:
    cr = rec.get("client_request") or {}
    effort = cr.get("reasoning_effort")
    return {
        "client.max_tokens": to_float(cr.get("max_tokens") or cr.get("max_completion_tokens")),
        "client.temperature": to_float(cr.get("temperature")),
        "client.top_p": to_float(cr.get("top_p")),
        "client.stream": to_float(cr.get("stream")),
        "client.reasoning_effort": EFFORT.get(str(effort).lower(), None)
        if effort is not None
        else None,
    }


def extract_row(event: dict[str, Any]) -> dict[str, float | None]:
    req = event.get("req") or {}
    node = req.get("last_node") or {}
    sampling = req.get("sampling_params") or {}
    resource = event.get("resource") or {}
    out: dict[str, float | None] = {}
    for name in REQ_FIELDS:
        out[f"req.{name}"] = to_float(req.get(name))
    for name in NODE_FIELDS:
        out[f"last_node.{name}"] = to_float(node.get(name))
    for name in SAMPLE_FIELDS:
        out[f"sampling.{name}"] = to_float(sampling.get(name))
    for name in RESOURCE_FIELDS:
        val = resource.get(name)
        if isinstance(val, (list, tuple)):
            out[f"resource.{name}"] = None
        else:
            out[f"resource.{name}"] = to_float(val)
    return out


def load_client(path: Path) -> dict[str, dict[str, Any]]:
    rows = {}
    with path.open() as f:
        for line in f:
            rec = json.loads(line)
            rows[str(rec["trace_id"])] = rec
    return rows


def load_request_end(path: Path) -> dict[str, dict[str, float | None]]:
    out = {}
    with path.open(buffering=1024 * 1024) as f:
        for line in f:
            if '"event": "request_end"' not in line[:250]:
                continue
            event = json.loads(line)
            rid = str(event.get("rid") or "")
            if rid:
                out[rid] = extract_row(event)
    return out


def harrell_c(times: np.ndarray, events: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    """C-index treating score as predicted remaining time (higher => later return)."""
    n = len(times)
    conc = disc = tied = 0.0
    comparable = 0.0
    for i in range(n):
        if events[i] != 1:
            continue
        ti = times[i]
        si = scores[i]
        for j in range(n):
            if i == j:
                continue
            if times[j] < ti:
                continue
            if times[j] == ti and events[j] != 1:
                continue
            if times[j] == ti and j < i:
                continue
            if times[j] == ti:
                comparable += 1
                tied += 1
                continue
            comparable += 1
            if si < scores[j]:
                conc += 1
            elif si > scores[j]:
                disc += 1
            else:
                tied += 1
    if comparable == 0:
        return {"c_index": float("nan"), "n_pairs": 0, "tied_frac": float("nan")}
    c = (conc + 0.5 * tied) / comparable
    return {
        "c_index": float(c),
        "n_pairs": int(comparable),
        "tied_frac": float(tied / comparable),
    }


def summarize_feature(xs: np.ndarray) -> dict[str, Any]:
    finite = xs[np.isfinite(xs)]
    if finite.size == 0:
        return {"n": 0, "n_unique": 0, "std": None, "min": None, "max": None}
    return {
        "n": int(finite.size),
        "n_unique": int(len(np.unique(finite))),
        "std": float(np.std(finite)),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
    }


def rank_split(
    features: dict[str, dict[str, float | None]],
    clients: dict[str, dict[str, Any]],
    split: str,
) -> list[dict[str, Any]]:
    ids = [
        rid
        for rid, rec in clients.items()
        if rec.get("small_split") == split and rid in features
    ]
    times = np.array([float(clients[i]["tau_s_small"]) for i in ids], dtype=np.float64)
    events = np.array([int(clients[i]["delta_small"]) for i in ids], dtype=np.int32)
    merged = {rid: {**features[rid], **client_features(clients[rid])} for rid in ids}
    names = sorted(next(iter(merged.values())).keys()) if merged else []
    rows = []
    for name in names:
        xs = np.array(
            [
                np.nan if merged[i][name] is None else float(merged[i][name])
                for i in ids
            ],
            dtype=np.float64,
        )
        stats = summarize_feature(xs)
        group = name.split(".", 1)[0]
        if stats["n_unique"] < 2 or not stats["std"]:
            rows.append(
                {
                    "feature": name,
                    "group": group,
                    "c_index": None,
                    "abs_c": None,
                    "direction": "constant",
                    **stats,
                    "n_pairs": 0,
                    "tied_frac": None,
                    "n_obs": int(events.sum()),
                    "n_rows": len(ids),
                }
            )
            continue
        mask = np.isfinite(xs)
        c = harrell_c(times[mask], events[mask], xs[mask])
        cval = c["c_index"]
        direction = "higher_longer_tau" if cval >= 0.5 else "higher_shorter_tau"
        rows.append(
            {
                "feature": name,
                "group": group,
                "c_index": cval,
                "abs_c": abs(cval - 0.5),
                "direction": direction,
                **stats,
                "n_pairs": c["n_pairs"],
                "tied_frac": c["tied_frac"],
                "n_obs": int(events[mask].sum()),
                "n_rows": int(mask.sum()),
            }
        )
    rows.sort(key=lambda r: (r["abs_c"] is None, -(r["abs_c"] or 0.0), r["feature"]))
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    p.add_argument("--dump-file", type=str, default="server_dump/native_pid1681410.jsonl")
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args()
    run_dir: Path = args.run_dir
    clients = load_client(run_dir / "client" / "small_2200.client.jsonl")
    feats = load_request_end(run_dir / args.dump_file)
    dummy = set(feats) - set(clients)
    print(json.dumps({"n_client": len(clients), "n_dump": len(feats), "dummy": list(dummy)}, indent=2))
    out_dir = args.out_dir or (REPO_ROOT / "experiments/session_return/feature_rank")
    out_dir.mkdir(parents=True, exist_ok=True)
    ranking = {}
    for split in ("train", "val", "test"):
        ranking[split] = rank_split(feats, clients, split)
        n = sum(1 for r in clients.values() if r.get("small_split") == split)
        n_obs = sum(
            1
            for r in clients.values()
            if r.get("small_split") == split and r.get("delta_small") == 1
        )
        print(split, "n", n, "obs", n_obs, "top", ranking[split][0]["feature"] if ranking[split] else None)
    payload = {
        "run_dir": str(run_dir),
        "dump_file": args.dump_file,
        "label": "tau_s_small / delta_small",
        "metric": "Harrell C-index; score = feature value; C>0.5 means higher feature, later return",
        "note": (
            "Small nested split inside official train. Univariate C-index is "
            "diagnosis, not official feature freeze."
        ),
        "excluded": [
            "replay-clock ages (last_access_time, creation_time, created_time)",
            "derived counts (n_children, prompt_tokens, TTFT, E2E)",
            "token sequences and messages",
            "identity fields (rid, node id)",
        ],
        "ranking": ranking,
    }
    (out_dir / "univariate_cindex.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    # compact train table
    lines = ["feature\tgroup\tc_index\tabs_c\tdirection\tn_unique\tstd"]
    for row in ranking["train"]:
        lines.append(
            "\t".join(
                [
                    row["feature"],
                    row["group"],
                    "" if row["c_index"] is None else f"{row['c_index']:.4f}",
                    "" if row["abs_c"] is None else f"{row['abs_c']:.4f}",
                    row["direction"],
                    str(row["n_unique"]),
                    "" if row["std"] is None else f"{row['std']:.4g}",
                ]
            )
        )
    (out_dir / "univariate_cindex_train.tsv").write_text("\n".join(lines) + "\n")
    print("wrote", out_dir)


if __name__ == "__main__":
    main()
