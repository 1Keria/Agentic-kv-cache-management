#!/usr/bin/env python3
"""Compare prefix-hit on small-split test: LRU run vs τ̂ eviction run."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LRU = (
    REPO_ROOT / "experiments/session_return/replay_small/run_20260916_012751"
)


def load_client(run_dir: Path) -> list[dict]:
    path = run_dir / "client" / "small_2200.client.jsonl"
    if not path.is_file():
        matches = sorted((run_dir / "client").glob("*.client.jsonl"))
        if not matches:
            raise SystemExit(f"no client jsonl under {run_dir}")
        path = matches[-1]
    rows = []
    with path.open() as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("small_split"):
                rows.append(rec)
    return rows


def summarize(rows: list[dict]) -> dict:
    by = defaultdict(list)
    for rec in rows:
        by[rec.get("small_split") or "none"].append(rec)

    def block(part: list[dict]) -> dict:
        ok = [r for r in part if r.get("status") == "200"]
        prompt = [int(r.get("prompt_tokens") or 0) for r in ok]
        cached = [int(r.get("cached_tokens") or 0) for r in ok]
        psum = float(sum(prompt))
        csum = float(sum(cached))
        hit = [c / p if p else 0.0 for c, p in zip(cached, prompt)]
        return {
            "n": len(part),
            "n_ok": len(ok),
            "prompt_tokens": int(psum),
            "cached_tokens": int(csum),
            "hit_token_frac": (csum / psum) if psum else None,
            "mean_req_hit_frac": float(sum(hit) / len(hit)) if hit else None,
        }

    out = {name: block(part) for name, part in by.items()}
    out["all"] = block(rows)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--lru-run", type=Path, default=DEFAULT_LRU)
    p.add_argument("--tau-run", type=Path, required=True)
    args = p.parse_args()
    lru = summarize(load_client(args.lru_run))
    tau = summarize(load_client(args.tau_run))
    report = {
        "lru_run": str(args.lru_run),
        "tau_run": str(args.tau_run),
        "lru": lru,
        "tau": tau,
        "delta_test_hit_token_frac": None,
    }
    lt = lru.get("test", {}).get("hit_token_frac")
    tt = tau.get("test", {}).get("hit_token_frac")
    if lt is not None and tt is not None:
        report["delta_test_hit_token_frac"] = tt - lt
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for split in ("train", "val", "test", "all"):
        a = lru.get(split, {})
        b = tau.get(split, {})
        print(
            f"{split:5s}  LRU hit={a.get('hit_token_frac')}  "
            f"tau hit={b.get('hit_token_frac')}  "
            f"n_ok={b.get('n_ok')}/{a.get('n_ok')}"
        )


if __name__ == "__main__":
    main()
