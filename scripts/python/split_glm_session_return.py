#!/usr/bin/env python3
"""Time-window train/val/test split for GLM session-return labels.

Full split: requests sorted by start_time, 70/15/15.
Small split: the same rule on the first --small-n requests (a timeline prefix).
Labels use original GLM arrival times. τ is seconds until the next strict
message-prefix continuation; if none occurs before the split window ends,
the row is right-censored at that cut.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = (
    REPO_ROOT / "third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl"
)
DEFAULT_OUT_DIR = REPO_ROOT / "experiments/session_return/splits"


def parse_ts(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        dt = value
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return float(dt.timestamp())
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        head, rest = text.split(".", 1)
        frac = ""
        tz = ""
        for i, ch in enumerate(rest):
            if ch.isdigit():
                frac += ch
            else:
                tz = rest[i:]
                break
        text = f"{head}.{(frac + '000000')[:6]}{tz}"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return float(dt.timestamp())


def glm_msg_hash(msg: dict[str, Any]) -> str:
    sig = {
        "role": msg.get("role"),
        "content": msg.get("content"),
        "tool_calls": msg.get("tool_calls"),
        "tool_call_id": msg.get("tool_call_id"),
        "name": msg.get("name"),
    }
    blob = json.dumps(sig, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def first_user_hash(messages: list[dict[str, Any]]) -> str | None:
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if content is None:
            continue
        if isinstance(content, str):
            text = content
        else:
            text = json.dumps(content, ensure_ascii=False, sort_keys=True)
        if not str(text).strip():
            continue
        return hashlib.sha256(str(text).encode("utf-8")).hexdigest()
    return None


def is_hash_prefix(prev: list[str], nxt: list[str]) -> bool:
    if len(prev) >= len(nxt):
        return False
    return prev == nxt[: len(prev)]


def index_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    bad = 0
    with path.open("rb") as f:
        line_no = 0
        while True:
            offset = f.tell()
            raw = f.readline()
            if not raw:
                break
            line_no += 1
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                pb = json.loads(obj["prompt_body"])
            except Exception:
                bad += 1
                continue
            messages = list(pb.get("messages") or [])
            user_h = first_user_hash(messages)
            if user_h is None:
                continue
            records.append(
                {
                    "line_no": line_no,
                    "offset": offset,
                    "trace_id": obj.get("trace_id"),
                    "start_time": obj.get("start_time"),
                    "start_s": parse_ts(obj.get("start_time")),
                    "user_hash": user_h,
                    "msg_hashes": [glm_msg_hash(m) for m in messages],
                }
            )
            if line_no % 4000 == 0:
                print(f"[glm] indexed {line_no} lines / {len(records)} records", flush=True)
    print(f"[glm] index done records={len(records)} bad_lines={bad}", flush=True)
    return records, bad


def count_cuts(n: int, train_frac: float, val_frac: float) -> tuple[int, int]:
    n_train = int(round(n * train_frac))
    n_val = int(round(n * val_frac))
    n_test = n - n_train - n_val
    if n_test < 0:
        n_val += n_test
        n_test = 0
    return n_train, n_train + n_val


def assign_by_index(i: int, n_train: int, n_train_val: int) -> str:
    if i < n_train:
        return "train"
    if i < n_train_val:
        return "val"
    return "test"


def attach_next_continuation(ordered: list[dict[str, Any]]) -> None:
    groups: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(ordered):
        groups[rec["user_hash"]].append(i)
    for idxs in groups.values():
        for pos, i in enumerate(idxs):
            prev = ordered[i]
            nxt_i = None
            for j in idxs[pos + 1 :]:
                cand = ordered[j]
                if is_hash_prefix(prev["msg_hashes"], cand["msg_hashes"]):
                    nxt_i = j
                    break
            prev["next_time_idx"] = nxt_i
            if nxt_i is None:
                prev["tau_s_global"] = None
                prev["delta_global"] = 0
                prev["next_trace_id"] = None
            else:
                nxt = ordered[nxt_i]
                prev["tau_s_global"] = float(nxt["start_s"] - prev["start_s"])
                prev["delta_global"] = 1
                prev["next_trace_id"] = nxt["trace_id"]


def window_end_s(ordered: list[dict[str, Any]], n_train: int, n_train_val: int) -> dict[str, float]:
    last = float(ordered[-1]["start_s"])
    ends = {"test": last}
    if n_train < len(ordered):
        ends["train"] = float(ordered[n_train]["start_s"])
    else:
        ends["train"] = last
    if n_train_val < len(ordered):
        ends["val"] = float(ordered[n_train_val]["start_s"])
    else:
        ends["val"] = last
    return ends


def apply_split_censor(
    rec: dict[str, Any],
    split: str,
    ends: dict[str, float],
) -> tuple[int, float, bool]:
    cut = ends[split]
    tau_g = rec.get("tau_s_global")
    if rec.get("delta_global") == 1 and tau_g is not None:
        next_s = float(rec["start_s"]) + float(tau_g)
        if next_s < cut - 1e-9:
            return 1, float(tau_g), False
        return 0, max(0.0, cut - float(rec["start_s"])), True
    return 0, max(0.0, cut - float(rec["start_s"])), False


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize(rows: list[dict[str, Any]], split_key: str, delta_key: str) -> dict[str, Any]:
    by = Counter(r[split_key] for r in rows if r.get(split_key))
    out: dict[str, Any] = {"n": len(rows), "by_split": dict(by)}
    for name in ("train", "val", "test"):
        part = [r for r in rows if r.get(split_key) == name]
        if not part:
            continue
        n_obs = sum(1 for r in part if r[delta_key] == 1)
        hashes = {r["user_hash"] for r in part}
        out[name] = {
            "n": len(part),
            "n_observed": n_obs,
            "n_censored": len(part) - n_obs,
            "n_hash": len(hashes),
            "start": part[0]["start_time"],
            "end": part[-1]["start_time"],
            "span_h": (part[-1]["start_s"] - part[0]["start_s"]) / 3600.0,
        }
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--train-frac", type=float, default=0.70)
    p.add_argument("--val-frac", type=float, default=0.15)
    p.add_argument("--small-n", type=int, default=2200)
    args = p.parse_args()

    records, bad = index_records(args.dataset)
    missing_t = sum(1 for r in records if r["start_s"] is None)
    if missing_t:
        raise SystemExit(f"{missing_t} records missing start_time")

    ordered = sorted(records, key=lambda r: (r["start_s"], r["line_no"]))
    n = len(ordered)
    n_train, n_train_val = count_cuts(n, args.train_frac, args.val_frac)
    small_n = min(args.small_n, n)
    s_train, s_train_val = count_cuts(small_n, args.train_frac, args.val_frac)

    for i, rec in enumerate(ordered):
        rec["time_idx"] = i
        rec["full_split"] = assign_by_index(i, n_train, n_train_val)
        rec["in_small"] = i < small_n
        rec["small_split"] = (
            assign_by_index(i, s_train, s_train_val) if i < small_n else None
        )

    attach_next_continuation(ordered)
    full_ends = window_end_s(ordered, n_train, n_train_val)
    small_ends = window_end_s(ordered[:small_n], s_train, s_train_val)

    crossing_hashes: set[str] = set()
    hash_splits: dict[str, set[str]] = defaultdict(set)
    hash_n: Counter[str] = Counter()
    for rec in ordered:
        hash_splits[rec["user_hash"]].add(rec["full_split"])
        hash_n[rec["user_hash"]] += 1
        delta, tau, crossed = apply_split_censor(rec, rec["full_split"], full_ends)
        rec["delta_full"] = delta
        rec["tau_s_full"] = tau
        rec["crosses_full_cut"] = crossed
        if rec["in_small"]:
            sd, st, _ = apply_split_censor(rec, rec["small_split"], small_ends)
            rec["delta_small"] = sd
            rec["tau_s_small"] = st
        else:
            rec["delta_small"] = None
            rec["tau_s_small"] = None
    for h, ss in hash_splits.items():
        if len(ss) > 1:
            crossing_hashes.add(h)

    drop_keys = {"msg_hashes"}
    rows = [{k: v for k, v in rec.items() if k not in drop_keys} for rec in ordered]

    out_dir = args.out_dir
    full_dir = out_dir / "full"
    small_dir = out_dir / "small"
    full_dir.mkdir(parents=True, exist_ok=True)
    small_dir.mkdir(parents=True, exist_ok=True)

    by_full = {"train": [], "val": [], "test": []}
    by_small = {"train": [], "val": [], "test": []}
    for row in rows:
        by_full[row["full_split"]].append(row)
        if row["in_small"]:
            by_small[row["small_split"]].append(row)

    for name, part in by_full.items():
        write_jsonl(full_dir / f"{name}.jsonl", part)
    for name, part in by_small.items():
        write_jsonl(small_dir / f"{name}.jsonl", part)

    for stale in (
        out_dir / "requests.jsonl",
        out_dir / "small_replay_order.jsonl",
        small_dir / "replay_order.jsonl",
    ):
        if stale.exists():
            stale.unlink()

    full_summary = summarize(rows, "full_split", "delta_full")
    small_rows = [r for r in rows if r["in_small"]]
    small_summary = summarize(small_rows, "small_split", "delta_small")
    n_cross_obs = sum(1 for r in rows if r["crosses_full_cut"])
    mega = hash_n.most_common(1)[0][0]
    mega_counts = Counter(r["full_split"] for r in rows if r["user_hash"] == mega)

    manifest = {
        "dataset": str(args.dataset.relative_to(REPO_ROOT)),
        "n_valid": n,
        "bad_lines": bad,
        "sort": "start_s, line_no",
        "train_frac": args.train_frac,
        "val_frac": args.val_frac,
        "label": {
            "tau_unit": "seconds",
            "tau_definition": (
                "next same-hash strict message-prefix arrival start_time "
                "minus this start_time; right-censored at the split window cut"
            ),
            "delta_full": "1 if next continuation occurs before this row's full split ends",
            "delta_small": "1 if next continuation occurs before this row's small split ends",
        },
        "full": {
            "n_train": n_train,
            "n_val": n_train_val - n_train,
            "n_test": n - n_train_val,
            "cut_time_idx": [n_train, n_train_val],
            "window_end_s": full_ends,
            "summary": full_summary,
            "n_crossing_hashes": len(crossing_hashes),
            "n_obs_censored_at_cut": n_cross_obs,
            "mega_hash": mega,
            "mega_by_split": dict(mega_counts),
        },
        "small": {
            "n": small_n,
            "n_train": s_train,
            "n_val": s_train_val - s_train,
            "n_test": small_n - s_train_val,
            "cut_time_idx": [s_train, s_train_val],
            "window_end_s": small_ends,
            "summary": small_summary,
            "note": (
                "Timeline prefix of the full train window. small val/test are "
                "not the official val/test."
            ),
            "replay_until": "all small split rows",
        },
        "files": {
            "full_dir": "full",
            "small_dir": "small",
            "full": {
                "train": "full/train.jsonl",
                "val": "full/val.jsonl",
                "test": "full/test.jsonl",
            },
            "small": {
                "train": "small/train.jsonl",
                "val": "small/val.jsonl",
                "test": "small/test.jsonl",
            },
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(
        {
            "out_dir": str(out_dir),
            "full": full_summary["by_split"],
            "small": small_summary["by_split"],
            "crossing_hashes": len(crossing_hashes),
            "obs_censored_at_full_cut": n_cross_obs,
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
