#!/usr/bin/env python3
"""Copy the held-out 50/50 workload and cap decode length for frontier tracing."""

import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--max-tokens", type=int, default=32)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    counts = {"rows": 0, "openhands": 0, "request": 0}
    with (args.source / "workload.jsonl").open(encoding="utf-8") as src, \
            (args.output / "workload.jsonl").open("w", encoding="utf-8") as dst:
        for line in src:
            row = json.loads(line)
            row["max_tokens"] = min(int(row.get("max_tokens") or args.max_tokens), args.max_tokens)
            dst.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            counts["rows"] += 1
            counts[row["traffic_class"]] = counts.get(row["traffic_class"], 0) + 1
    source_spec = json.loads((args.source / "spec.json").read_text())
    spec = {
        "name": "cold_frontier_agent050_decode32",
        "source": str(args.source),
        "source_protocol": source_spec.get("protocol"),
        "decode_cap": args.max_tokens,
        "counts": counts,
        "note": "Prompt bodies/session ordering unchanged; only max_tokens is capped for collection speed.",
    }
    (args.output / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    print(json.dumps(spec, indent=2))


if __name__ == "__main__":
    main()
