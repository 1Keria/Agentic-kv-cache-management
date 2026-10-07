#!/usr/bin/env python3
"""Build a deterministic prefix subset for short cache-control experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--timeline-scale", type=float, default=0.1)
    args = parser.parse_args()
    if args.rows <= 0 or not 0 < args.timeline_scale <= 1:
        raise SystemExit("rows must be positive and timeline-scale must be in (0, 1]")
    source = args.source.resolve()
    rows = [
        json.loads(line)
        for line in source.read_text().splitlines()[: args.rows]
        if line.strip()
    ]
    if len(rows) != args.rows:
        raise SystemExit(f"source contains only {len(rows)} rows")
    for row in rows:
        row["session_start_s"] = round(
            float(row["session_start_s"]) * args.timeline_scale, 6
        )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    workload = output_dir / "workload.jsonl"
    workload.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows)
    )
    sessions = {str(row["session_id"]): str(row["traffic_class"]) for row in rows}
    manifest = {
        "name": f"prefix_subset_{args.rows}",
        "protocol": "dynamic-partition-controlled-v1",
        "source_workload": str(source),
        "source_workload_sha256": sha256_file(source),
        "workload_jsonl_sha256": sha256_file(workload),
        "n_turns": len(rows),
        "n_sessions": len(sessions),
        "n_sessions_by_class": {
            traffic_class: sum(value == traffic_class for value in sessions.values())
            for traffic_class in sorted(set(sessions.values()))
        },
        "transformation": {
            "type": "prefix_subset",
            "rows": args.rows,
            "timeline_scale": args.timeline_scale,
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
