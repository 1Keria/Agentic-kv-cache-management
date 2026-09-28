#!/usr/bin/env python3
"""Profile every encoded candidate, without selecting the formal workload."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import struct

from build_workload import POOL, read_rows
from prepare_data import ROOT, digest_file, save_json


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"count": 0}
    def percentile(fraction):
        position = (len(ordered) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return {"count": len(values), "sum": sum(values), "min": ordered[0], "p50": percentile(.5),
            "p95": percentile(.95), "p99": percentile(.99), "max": ordered[-1]}


def profile(output: Path):
    pool = json.loads(POOL.read_text())
    output.mkdir(parents=True, exist_ok=False)
    all_rows = []
    sessions = []
    prefix_references = {}
    page_size = 256
    for entry in pool["sessions"]:
        rows = read_rows(entry)
        session_prefixes = set()
        for row in rows:
            ids = row["input_ids"]
            prefix_hash = b""
            for offset in range(0, len(ids) - page_size + 1, page_size):
                page = struct.pack(f"<{page_size}I", *ids[offset:offset + page_size])
                prefix_hash = hashlib.sha256(prefix_hash + page).digest()
                session_prefixes.add(prefix_hash)
            all_rows.append({"session_id": entry["session_id"], "task_id": entry["task_id"],
                             "split": entry["split"], "turn_index": row["turn_index"],
                             "prompt_tokens": len(ids), "source_output_tokens": row["output_tokens"],
                             "recorded_gap_seconds": row["wait_after_previous_response_seconds"],
                             "previous_input_lcp_tokens": row["same_session_previous_input_lcp_tokens"],
                             "tokens_after_previous_input_lcp": len(ids) - row["same_session_previous_input_lcp_tokens"]})
        for prefix_hash in session_prefixes:
            prefix_references[prefix_hash] = prefix_references.get(prefix_hash, 0) + 1
        sessions.append({"session_id": entry["session_id"], "task_id": entry["task_id"], "split": entry["split"],
                         "requests": len(rows), "recorded_wait_sum_seconds": sum(
                             row["wait_after_previous_response_seconds"] for row in rows[1:]),
                         "max_prompt_plus_output_tokens": entry["max_prompt_plus_output_tokens"],
                         "unique_complete_prefix_pages": len(session_prefixes)})
    for filename, rows in [("requests.csv", all_rows), ("sessions.csv", sessions)]:
        with (output / filename).open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    summaries = {}
    for split in ["all", "calibration", "evaluation"]:
        rows = [row for row in all_rows if split == "all" or row["split"] == split]
        subset = [session for session in sessions if split == "all" or session["split"] == split]
        summaries[split] = {"sessions": len(subset), "tasks": len({session["task_id"] for session in subset}),
                            "requests": len(rows), "session_requests": distribution([session["requests"] for session in subset]),
                            "session_wait_sum_seconds": distribution([session["recorded_wait_sum_seconds"] for session in subset])}
        for field in ["prompt_tokens", "source_output_tokens", "recorded_gap_seconds", "previous_input_lcp_tokens", "tokens_after_previous_input_lcp"]:
            summaries[split][field] = distribution([row[field] for row in rows if row[field] is not None])
    summary = {"purpose": "all_candidate_content_profile_not_workload_selection", "summaries": summaries,
               "pool_manifest_sha256": digest_file(POOL), "page_size": page_size,
               "unique_complete_context_prefix_pages": len(prefix_references),
               "prefix_pages_shared_across_sessions": sum(count > 1 for count in prefix_references.values()),
               "prefix_page_session_reference_counts": distribution(list(prefix_references.values())),
               "limitations": ["Input-only complete-page content identities, not physical KV allocations or runtime hits",
                               "No event order inferred between independent sessions",
                               "Recorded output usage is a replay length target, not a measurement by this service",
                               "Historical provider encoding and exact collector version remain unverified",
                               "LCP gap is a content diagnostic, not avoidable eviction loss"],
               "formal_data_volume_selected": False}
    save_json(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if not args.output.resolve().is_relative_to(ROOT):
        raise ValueError("Output must remain inside this experiment")
    result = profile(args.output)
    print(json.dumps(result["summaries"]["all"], ensure_ascii=False))


if __name__ == "__main__":
    main()
