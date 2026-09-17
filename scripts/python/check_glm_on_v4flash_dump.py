#!/usr/bin/env python3
"""Sanity-check a GLM-on-V4Flash dump: rid join, errors, continuation cache hits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_client(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("small_split") or rec.get("dry_run"):
                rows.append(rec)
    return rows


def load_request_end(dump_dir: Path) -> dict[str, dict]:
    out = {}
    for path in sorted(dump_dir.glob("native_pid*.jsonl")):
        with path.open(buffering=1024 * 1024) as f:
            for line in f:
                if '"event": "request_end"' not in line[:250]:
                    continue
                ev = json.loads(line)
                rid = str(ev.get("rid") or "")
                if rid:
                    out[rid] = ev
    return out


def cached_of(rec: dict) -> int:
    return int(rec.get("cached_tokens") or 0)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "experiments/session_return/replay_glm_on_v4flash/latest",
    )
    args = p.parse_args()
    client_dir = args.run_dir / "client"
    dumps = list(client_dir.glob("*.client.jsonl"))
    if not dumps:
        raise SystemExit(f"no client jsonl in {client_dir}")
    client_path = max(dumps, key=lambda x: x.stat().st_mtime)
    rows = load_client(client_path)
    ends = load_request_end(args.run_dir / "server_dump")
    n = len(rows)
    n_ok = sum(1 for r in rows if r.get("status") == "200")
    n_err = sum(1 for r in rows if r.get("status") != "200")
    joined = [r for r in rows if str(r.get("trace_id")) in ends]
    cont = [r for r in joined if int(r.get("delta_small") or 0) == 1]
    first = [r for r in joined if int(r.get("delta_small") or 0) == 0]
    # continuation vs first-in-window: use whether this user_hash appeared earlier in this replay
    seen = set()
    cont_replay = []
    new_replay = []
    for r in rows:
        h = r.get("user_hash")
        bucket = cont_replay if h in seen else new_replay
        if str(r.get("trace_id")) in ends and r.get("status") == "200":
            bucket.append(r)
        seen.add(h)

    def mean_cached(part: list[dict]) -> float | None:
        if not part:
            return None
        return sum(cached_of(r) for r in part) / len(part)

    report = {
        "run_dir": str(args.run_dir),
        "client": str(client_path),
        "n_sent": n,
        "n_ok": n_ok,
        "n_err": n_err,
        "error_rate": (n_err / n) if n else None,
        "n_dump_request_end": len(ends),
        "n_joined": len(joined),
        "join_rate": (len(joined) / n) if n else None,
        "mean_cached_all_ok": mean_cached([r for r in joined if r.get("status") == "200"]),
        "n_prefix_continuation_in_replay": len(cont_replay),
        "mean_cached_continuation": mean_cached(cont_replay),
        "n_first_in_replay": len(new_replay),
        "mean_cached_first": mean_cached(new_replay),
        "n_label_delta1_joined": len(cont),
        "mean_cached_label_delta1": mean_cached([r for r in cont if r.get("status") == "200"]),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        f"ok={n_ok}/{n} err={n_err} join={len(joined)}/{n}  "
        f"cont_cached={report['mean_cached_continuation']} "
        f"first_cached={report['mean_cached_first']}"
    )
    if n and n_err / n > 0.2:
        raise SystemExit("error rate > 20%; check Flash parser vs GLM tools/reasoning")
    if cont_replay and (report["mean_cached_continuation"] or 0) <= 0:
        raise SystemExit("continuation cached_tokens is 0; Flash prefix share likely broken")


if __name__ == "__main__":
    main()
