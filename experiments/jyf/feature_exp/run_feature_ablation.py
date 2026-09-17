#!/usr/bin/env python3
"""Offline feature ablation for predicting the next logical-prefix reuse time.

Only information available to the inference server is used:
  * online reuse history maintained per logical prefix;
  * Radix-node shape/token information known after the current request inserts;
  * the request's ``tools`` field.

The target is request-start to the next request-start that contains the exact
same logical prefix. The final observation of each prefix is right-censored at
the end of the trace. Splits are by conversation anchor, so prefixes from one
conversation cannot occur in more than one split.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


EDGES = np.asarray(
    [1, 2, 3, 5, 8, 12, 20, 30, 45, 60, 90, 120, 180, 300, 600, 1200, 2400, 7200],
    dtype=np.float32,
)
HORIZONS = (5.0, 20.0, 60.0, 180.0)
TOOL_HASH_DIM = 32

RECENT_NAMES = [f"log_recent_gap_{i + 1}" for i in range(8)] + [
    f"recent_gap_mask_{i + 1}" for i in range(8)
]
HISTORY_NAMES = RECENT_NAMES + [
    "log_gap_mean",
    "log_gap_std",
    "log_gap_min",
    "log_gap_max",
    "log_gap_ewma",
    "log_reuse_count",
    "log_accesses_prev_5s",
    "log_accesses_prev_20s",
    "log_accesses_prev_60s",
    "log_accesses_prev_300s",
]
RADIX_NAMES = [
    "log_prefix_tokens",
    "log_node_tokens",
    "log_child_count",
    "is_leaf",
]
TOOLS_NAMES = ["log_tool_count", "log_tool_schema_bytes"] + [
    f"tool_name_hash_{i}" for i in range(TOOL_HASH_DIM)
]
FEATURE_NAMES = HISTORY_NAMES + RADIX_NAMES + TOOLS_NAMES

HISTORY_SUMMARY_NAMES = HISTORY_NAMES[len(RECENT_NAMES) :]
RADIX_TOKEN_NAMES = RADIX_NAMES[:2]
RADIX_SHAPE_NAMES = RADIX_NAMES[2:]
TOOLS_SIZE_NAMES = TOOLS_NAMES[:2]
TOOLS_IDENTITY_NAMES = TOOLS_NAMES[2:]

GROUPS = {
    "constant": [],
    "history_recent": RECENT_NAMES,
    "history_summary": HISTORY_SUMMARY_NAMES,
    "history": HISTORY_NAMES,
    "radix_tokens": RADIX_TOKEN_NAMES,
    "radix_shape": RADIX_SHAPE_NAMES,
    "radix": RADIX_NAMES,
    "tools_size": TOOLS_SIZE_NAMES,
    "tools_identity": TOOLS_IDENTITY_NAMES,
    "tools": TOOLS_NAMES,
    "history_recent+tools_size": RECENT_NAMES + TOOLS_SIZE_NAMES,
    "history_recent+tools_identity": RECENT_NAMES + TOOLS_IDENTITY_NAMES,
    "history_summary+tools_size": HISTORY_SUMMARY_NAMES + TOOLS_SIZE_NAMES,
    "history_summary+tools_identity": HISTORY_SUMMARY_NAMES + TOOLS_IDENTITY_NAMES,
    "history_summary+tools": HISTORY_SUMMARY_NAMES + TOOLS_NAMES,
    "history+radix": HISTORY_NAMES + RADIX_NAMES,
    "history+tools": HISTORY_NAMES + TOOLS_NAMES,
    "all": HISTORY_NAMES + RADIX_NAMES + TOOLS_NAMES,
}


def log1p(value: float) -> float:
    return math.log1p(max(0.0, float(value)))


def stable_hash(obj: object) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(raw.encode("utf-8", errors="replace"), digest_size=16).digest()


def chained_hash(previous: bytes, item: bytes) -> bytes:
    return hashlib.blake2b(previous + item, digest_size=16).digest()


def parse_timestamp(raw: str) -> float:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()


def split_for_anchor(anchor: bytes) -> int:
    value = int.from_bytes(hashlib.blake2b(anchor, digest_size=8).digest(), "big") % 100
    return 0 if value < 70 else (1 if value < 85 else 2)


def response_usage(response_body: object) -> dict:
    try:
        body = json.loads(response_body) if isinstance(response_body, str) else response_body
        usage = (body or {}).get("usage") or {}
        return usage if isinstance(usage, dict) else {}
    except Exception:
        return {}


def tool_features(tools: list) -> list[float]:
    raw = json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    vector = np.zeros(TOOL_HASH_DIM, dtype=np.float32)
    for tool in tools:
        function = tool.get("function", {}) if isinstance(tool, dict) else {}
        name = str(function.get("name") or tool.get("name") or "")
        digest = hashlib.blake2b(name.encode("utf-8", errors="replace"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        vector[value % TOOL_HASH_DIM] += 1.0 if ((value >> 8) & 1) else -1.0
    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector /= norm
    return [log1p(len(tools)), log1p(len(raw.encode("utf-8")))] + vector.tolist()


def read_requests(dataset: Path) -> tuple[list[dict], dict]:
    requests = []
    malformed = 0
    started = time.time()
    with dataset.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, 1):
            try:
                outer = json.loads(line)
                prompt = json.loads(outer["prompt_body"])
                messages = prompt.get("messages") or []
                first_user = next((i for i, m in enumerate(messages) if m.get("role") == "user"), None)
                if first_user is None:
                    continue
                tools = prompt.get("tools") or []
                scope = stable_hash({"model": prompt.get("model", ""), "tools": tools})
                usage = response_usage(outer.get("response_body"))
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                if prompt_tokens <= 0:
                    prompt_tokens = max(1, len(outer.get("prompt_body", "")) // 4)

                message_hashes = [stable_hash(m) for m in messages]
                message_sizes = [
                    max(1, len(json.dumps(m, ensure_ascii=False, separators=(",", ":"))))
                    for m in messages
                ]
                rolling = scope
                for i in range(first_user + 1):
                    rolling = chained_hash(rolling, message_hashes[i])
                anchor = rolling

                total_chars = sum(message_sizes)
                consumed_chars = 0
                rolling = scope
                occurrences = []
                for i, (message_hash, chars) in enumerate(zip(message_hashes, message_sizes)):
                    parent = rolling
                    rolling = chained_hash(rolling, message_hash)
                    consumed_chars += chars
                    if i < first_user:
                        continue
                    suffix_chars = max(0, total_chars - consumed_chars)
                    prefix_tokens = max(1, prompt_tokens - int(round(suffix_chars / 4.0)))
                    node_tokens = max(1, int(round(chars / 4.0)))
                    occurrences.append((rolling, parent, prefix_tokens, node_tokens))
                requests.append(
                    {
                        "t": parse_timestamp(outer["start_time"]),
                        "line": line_no,
                        "anchor": anchor,
                        "split": split_for_anchor(anchor),
                        "occurrences": occurrences,
                        "tool_features": tool_features(tools),
                    }
                )
            except Exception:
                malformed += 1
            if line_no % 2000 == 0:
                print(
                    f"[parse] lines={line_no} requests={len(requests)} malformed={malformed} "
                    f"elapsed={time.time() - started:.1f}s",
                    flush=True,
                )
    requests.sort(key=lambda row: (row["t"], row["line"]))
    return requests, {"requests": len(requests), "malformed": malformed}


def history_features(gaps: deque, hits: int, access_times: deque, now: float) -> list[float]:
    recent_chrono = list(gaps)[-8:]
    recent = recent_chrono[::-1]
    values = recent + [0.0] * (8 - len(recent))
    masks = [1.0] * len(recent) + [0.0] * (8 - len(recent))
    if recent_chrono:
        array = np.asarray(recent_chrono, dtype=np.float64)
        ewma = float(array[0])
        for value in array[1:]:
            ewma = 0.6 * float(value) + 0.4 * ewma
        stats = [float(array.mean()), float(array.std()), float(array.min()), float(array.max()), ewma]
    else:
        stats = [0.0] * 5
    prior = list(access_times)
    counts = [sum(timestamp >= now - window for timestamp in prior) for window in (5, 20, 60, 300)]
    return (
        [log1p(value) for value in values]
        + masks
        + [log1p(value) for value in stats]
        + [log1p(hits)]
        + [log1p(value) for value in counts]
    )


def build_dataset(dataset: Path, output: Path) -> dict:
    requests, meta = read_requests(dataset)
    if not requests:
        raise SystemExit("no valid requests")
    trace_end = max(row["t"] for row in requests)
    states: dict[bytes, dict] = {}
    xs, durations, events, splits, histories, sample_times = [], [], [], [], [], []

    def state(prefix_id: bytes) -> dict:
        return states.setdefault(
            prefix_id,
            {
                "last_t": None,
                "gaps": deque(maxlen=32),
                "hits": 0,
                "pending": None,
                "children": set(),
                "access_times": deque(maxlen=512),
            },
        )

    for request_i, request in enumerate(requests, 1):
        # At an eviction decision after this request, all its nodes and edges exist.
        for prefix_id, parent_id, _, _ in request["occurrences"]:
            state(prefix_id)
            if parent_id in states:
                states[parent_id]["children"].add(prefix_id)

        for prefix_id, _, prefix_tokens, node_tokens in request["occurrences"]:
            prefix_state = state(prefix_id)
            if prefix_state["last_t"] is not None:
                gap = max(request["t"] - prefix_state["last_t"], 1e-6)
                previous = prefix_state["pending"]
                durations[previous] = gap
                events[previous] = 1
                prefix_state["gaps"].append(gap)
                prefix_state["hits"] += 1

            history_count = len(prefix_state["gaps"])
            history = history_features(
                prefix_state["gaps"],
                prefix_state["hits"],
                prefix_state["access_times"],
                request["t"],
            )
            child_count = len(prefix_state["children"])
            radix = [
                log1p(prefix_tokens),
                log1p(node_tokens),
                log1p(child_count),
                float(child_count == 0),
            ]
            sample_index = len(xs)
            xs.append(history + radix + request["tool_features"])
            durations.append(0.0)
            events.append(0)
            splits.append(request["split"])
            histories.append(history_count)
            sample_times.append(request["t"])
            prefix_state["last_t"] = request["t"]
            prefix_state["pending"] = sample_index
            prefix_state["access_times"].append(request["t"])

        if request_i % 2000 == 0:
            print(
                f"[build] requests={request_i}/{len(requests)} samples={len(xs)} prefixes={len(states)}",
                flush=True,
            )

    for prefix_state in states.values():
        index = prefix_state["pending"]
        if index is not None and events[index] == 0:
            durations[index] = max(trace_end - prefix_state["last_t"], 1e-6)

    arrays = {
        "x": np.asarray(xs, dtype=np.float32),
        "duration": np.asarray(durations, dtype=np.float32),
        "event": np.asarray(events, dtype=np.uint8),
        "split": np.asarray(splits, dtype=np.uint8),
        "history": np.asarray(histories, dtype=np.uint8),
        "sample_time": np.asarray(sample_times, dtype=np.float64),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, **arrays)
    eligible = arrays["history"] >= 1
    observed = eligible & (arrays["event"] == 1)
    meta.update(
        {
            "samples": int(len(arrays["x"])),
            "unique_prefixes": int(len(states)),
            "warm_samples": int(eligible.sum()),
            "warm_observed": int(observed.sum()),
            "feature_names": FEATURE_NAMES,
            "feature_groups": GROUPS,
            "label": "request-start to next request-start for the same exact logical prefix",
            "dataset": str(dataset),
            "output": str(output),
        }
    )
    output.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


class HazardMLP(nn.Module):
    def __init__(self, inputs: int, outputs: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(inputs, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Linear(64, outputs),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class ConstantHazard(nn.Module):
    def __init__(self, outputs: int):
        super().__init__()
        self.logits = nn.Parameter(torch.zeros(outputs))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.logits.unsqueeze(0).expand(len(x), -1)


def hazard_nll(logits: torch.Tensor, duration: torch.Tensor, event: torch.Tensor, edges: torch.Tensor) -> torch.Tensor:
    index = torch.bucketize(duration, edges, right=False)
    position = torch.arange(logits.shape[1], device=logits.device).unsqueeze(0)
    log_survival = torch.nn.functional.logsigmoid(-logits)
    log_hazard = torch.nn.functional.logsigmoid(logits)
    before = position < index.unsqueeze(1)
    likelihood = (log_survival * before).sum(dim=1)
    rows = torch.arange(len(logits), device=logits.device)
    likelihood += torch.where(event > 0.5, log_hazard[rows, index], log_survival[rows, index])
    return -likelihood.mean()


def auc_score(labels: np.ndarray, scores: np.ndarray) -> float:
    labels = labels.astype(np.uint8)
    positives = int(labels.sum())
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.empty(len(scores), dtype=np.float64)
    start = 0
    while start < len(scores):
        end = start + 1
        while end < len(scores) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        ranks[order[start:end]] = 0.5 * (start + 1 + end)
        start = end
    rank_sum = float(ranks[labels == 1].sum())
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


@torch.no_grad()
def evaluate(model: nn.Module, x: torch.Tensor, duration: torch.Tensor, event: torch.Tensor, edges: torch.Tensor) -> dict:
    model.eval()
    logits_parts = []
    batch_size = 32768
    for start in range(0, len(x), batch_size):
        logits_parts.append(model(x[start : start + batch_size]))
    logits = torch.cat(logits_parts)
    nll = float(hazard_nll(logits, duration, event, edges).cpu())
    hazards = torch.sigmoid(logits).cpu().numpy()
    duration_np = duration.cpu().numpy()
    event_np = event.cpu().numpy().astype(bool)
    metrics = {"nll": nll}
    briers = []
    for horizon in HORIZONS:
        last_bin = int(np.searchsorted(EDGES, horizon, side="left"))
        probability = 1.0 - np.prod(1.0 - hazards[:, : last_bin + 1], axis=1)
        known = (duration_np > horizon) | (event_np & (duration_np <= horizon))
        labels = event_np & (duration_np <= horizon)
        brier = float(np.mean((probability[known] - labels[known].astype(np.float32)) ** 2))
        metrics[f"brier@{int(horizon)}s"] = brier
        metrics[f"auc@{int(horizon)}s"] = auc_score(labels[known], probability[known])
        metrics[f"known@{int(horizon)}s"] = int(known.sum())
        briers.append(brier)
    metrics["mean_brier"] = float(np.mean(briers))
    return metrics


def fit_one(data: dict, feature_indices: list[int], seed: int, args: argparse.Namespace) -> dict:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    device = torch.device(args.device)
    history = data["history"]
    duration = data["duration"].astype(np.float32)
    event = data["event"].astype(np.float32)
    eligible = (history >= args.min_history) & (duration > 1e-6)
    train_index = np.where(eligible & (data["split"] == 0))[0]
    val_index = np.where(eligible & (data["split"] == 1))[0]
    test_index = np.where(eligible & (data["split"] == 2))[0]

    if feature_indices:
        raw = data["x"][:, feature_indices].astype(np.float32)
        mean = raw[train_index].mean(axis=0)
        std = raw[train_index].std(axis=0)
        std[std < 1e-5] = 1.0
        raw = (raw - mean) / std
    else:
        raw = np.zeros((len(duration), 1), dtype=np.float32)

    train_x = torch.from_numpy(raw[train_index]).to(device)
    train_d = torch.from_numpy(duration[train_index]).to(device)
    train_e = torch.from_numpy(event[train_index]).to(device)
    val_x = torch.from_numpy(raw[val_index]).to(device)
    val_d = torch.from_numpy(duration[val_index]).to(device)
    val_e = torch.from_numpy(event[val_index]).to(device)
    test_x = torch.from_numpy(raw[test_index]).to(device)
    test_d = torch.from_numpy(duration[test_index]).to(device)
    test_e = torch.from_numpy(event[test_index]).to(device)
    edges = torch.from_numpy(EDGES).to(device)

    model: nn.Module
    if feature_indices:
        model = HazardMLP(len(feature_indices), len(EDGES) + 1).to(device)
    else:
        model = ConstantHazard(len(EDGES) + 1).to(device)
        # Closed-form MLE for a population discrete hazard. Training these
        # logits from zero with the MLP learning rate gives an unfairly weak
        # baseline because most bins have very small hazards.
        train_bins = np.searchsorted(EDGES, duration[train_index], side="left")
        train_events = event[train_index].astype(bool)
        hazards = []
        for bin_index in range(len(EDGES) + 1):
            at_risk = int((train_bins >= bin_index).sum())
            observed = int((train_events & (train_bins == bin_index)).sum())
            hazards.append((observed + 0.5) / (at_risk + 1.0))
        hazard_tensor = torch.tensor(hazards, dtype=torch.float32, device=device).clamp(1e-6, 1 - 1e-6)
        with torch.no_grad():
            model.logits.copy_(torch.logit(hazard_tensor))
        validation = evaluate(model, val_x, val_d, val_e, edges)["nll"]
        metrics = evaluate(model, test_x, test_d, test_e, edges)
        metrics.update(
            {
                "seed": seed,
                "epochs_run": 0,
                "best_val_nll": validation,
                "train_samples": int(len(train_index)),
                "val_samples": int(len(val_index)),
                "test_samples": int(len(test_index)),
                "test_observed": int(event[test_index].sum()),
            }
        )
        return metrics
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    best_state = None
    best_val = float("inf")
    stale = 0
    generator = torch.Generator(device=device)
    generator.manual_seed(seed)

    for epoch in range(args.epochs):
        model.train()
        permutation = torch.randperm(len(train_x), generator=generator, device=device)
        for start in range(0, len(train_x), args.batch_size):
            index = permutation[start : start + args.batch_size]
            optimizer.zero_grad(set_to_none=True)
            loss = hazard_nll(model(train_x[index]), train_d[index], train_e[index], edges)
            loss.backward()
            optimizer.step()
        validation = evaluate(model, val_x, val_d, val_e, edges)["nll"]
        if validation < best_val - 1e-4:
            best_val = validation
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= args.patience:
            break
    model.load_state_dict(best_state)
    metrics = evaluate(model, test_x, test_d, test_e, edges)
    metrics.update(
        {
            "seed": seed,
            "epochs_run": epoch + 1,
            "best_val_nll": best_val,
            "train_samples": int(len(train_index)),
            "val_samples": int(len(val_index)),
            "test_samples": int(len(test_index)),
            "test_observed": int(event[test_index].sum()),
        }
    )
    return metrics


def summarize(results: dict) -> dict:
    summary = {}
    for group, runs in results.items():
        keys = [key for key in runs[0] if key in {"nll", "mean_brier"} or key.startswith("auc@") or key.startswith("brier@")]
        summary[group] = {}
        for key in keys:
            values = np.asarray([run[key] for run in runs], dtype=np.float64)
            summary[group][key] = {"mean": float(np.nanmean(values)), "std": float(np.nanstd(values))}
    return summary


def write_report(path: Path, meta: dict, summary: dict, args: argparse.Namespace) -> None:
    baseline = summary["constant"]
    lines = [
        "# Server-visible feature ablation",
        "",
        f"Dataset: `{args.dataset}`",
        "",
        f"Warm-prefix test samples use `history >= {args.min_history}`. Conversation anchors are split 70/15/15, "
        "and final observations are right-censored at trace end.",
        "",
        "All learned rows use the same 2x64 ReLU discrete-hazard MLP. `constant` is a learned population hazard with no features.",
        "",
        "| features | NLL ↓ | mean Brier ↓ | AUC@5s ↑ | AUC@20s ↑ | AUC@60s ↑ | ΔNLL vs constant |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for group in GROUPS:
        row = summary[group]
        nll = row["nll"]["mean"]
        lines.append(
            f"| {group} | {nll:.4f} ± {row['nll']['std']:.4f} | "
            f"{row['mean_brier']['mean']:.4f} | {row['auc@5s']['mean']:.4f} | "
            f"{row['auc@20s']['mean']:.4f} | {row['auc@60s']['mean']:.4f} | "
            f"{nll - baseline['nll']['mean']:+.4f} |"
        )
    lines += [
        "",
        "## Feature groups",
        "",
        f"- `history_recent`: {', '.join(RECENT_NAMES)}",
        "- `history_summary`: gap statistics, reuse count, and prior-access counts in fixed windows.",
        "- `history`: `history_recent` plus `history_summary`.",
        f"- `radix_tokens`: {', '.join(RADIX_TOKEN_NAMES)}",
        f"- `radix_shape`: {', '.join(RADIX_SHAPE_NAMES)}",
        "- `radix`: `radix_tokens` plus `radix_shape`.",
        "- `tools_size`: tool count and serialized schema bytes.",
        f"- `tools_identity`: a {TOOL_HASH_DIM}-dimensional signed hash of tool names.",
        "- `tools`: `tools_size` plus `tools_identity`.",
        "",
        "The tree features are evaluated because they are server-visible, not because the experiment assumes they are useful. "
        "Incremental rows (`history+radix`, `history+tools`, `all`) determine whether they add signal after reuse history is known.",
        "",
        f"Parsed {meta['requests']} requests into {meta['samples']} prefix observations; "
        f"{meta['warm_samples']} have at least one previous reuse.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "runs" / "latest")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--seeds", type=int, nargs="+", default=[41, 42, 43])
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--min-history", type=int, default=1)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset_cache = args.output_dir / "feature_samples.npz"
    if args.rebuild or not dataset_cache.exists():
        meta = build_dataset(args.dataset, dataset_cache)
    else:
        meta = json.loads(dataset_cache.with_suffix(".meta.json").read_text())
    loaded = np.load(dataset_cache)
    data = {key: loaded[key] for key in loaded.files}
    name_to_index = {name: index for index, name in enumerate(FEATURE_NAMES)}

    results = {}
    for group, names in GROUPS.items():
        indices = [name_to_index[name] for name in names]
        results[group] = []
        for seed in args.seeds:
            print(f"[train] group={group} seed={seed}", flush=True)
            metrics = fit_one(data, indices, seed, args)
            results[group].append(metrics)
            print(json.dumps(metrics, sort_keys=True), flush=True)

    summary = summarize(results)
    payload = {
        "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "feature_names": FEATURE_NAMES,
        "groups": GROUPS,
        "runs": results,
        "summary": summary,
    }
    (args.output_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n")
    write_report(args.output_dir / "report.md", meta, summary, args)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
