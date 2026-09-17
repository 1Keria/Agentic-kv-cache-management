#!/usr/bin/env python3
"""Determine whether the reuse-gap hole originates in raw timestamps or dataset construction."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


BINS = np.asarray([0, 1, 2, 5, 10, 20, 60, 180, 600, 1800, 3600, 7200,
                   21600, 86400, np.inf], dtype=float)


def describe(values):
    x = np.asarray(values, dtype=float)
    if not len(x):
        return {"n": 0}
    counts, _ = np.histogram(x, bins=BINS)
    return {
        "n": int(len(x)),
        "min": float(x.min()),
        "quantiles": {str(q): float(np.quantile(x, q)) for q in
                      (0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)},
        "max": float(x.max()),
        "bins": {f"[{BINS[i]:g},{BINS[i+1]:g})": int(counts[i])
                 for i in range(len(counts))},
        "count_60_3551": int(np.sum((x > 60) & (x < 3551))),
        "smallest_above_60": float(x[x > 60].min()) if np.any(x > 60) else None,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--npz", type=Path, required=True)
    p.add_argument("--builder-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    sys.path.insert(0, str(a.builder_dir))
    from mlp_reuse_offline import read_requests

    requests, meta = read_requests(a.raw)
    times = np.asarray([r["t"] for r in requests], dtype=float)
    global_gaps = np.diff(times)

    last_anchor = {}
    anchor_gaps = []
    anchor_request_counts = Counter()
    for r in requests:
        anchor_request_counts[r["anchor"]] += 1
        if r["anchor"] in last_anchor:
            anchor_gaps.append(r["t"] - last_anchor[r["anchor"]])
        last_anchor[r["anchor"]] = r["t"]

    last_prefix = {}
    prefix_gaps = []
    for r in requests:
        for prefix_id, _, _ in r["occurrences"]:
            if prefix_id in last_prefix:
                prefix_gaps.append(r["t"] - last_prefix[prefix_id])
            last_prefix[prefix_id] = r["t"]

    z = np.load(a.npz, allow_pickle=False)
    eligible = z["history"] >= 1
    observed = z["event"] == 1
    test = z["split"] == 2
    constructed_all = z["duration"][eligible & observed]
    constructed_test = z["duration"][eligible & observed & test]
    censored_test = z["duration"][eligible & (~observed) & test]

    # Count raw requests by UTC-derived day string to expose collection windows.
    from datetime import datetime, timezone
    day_counts = Counter(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d") for t in times)
    result = {
        "raw_request_count": len(requests),
        "raw_time_start": float(times.min()),
        "raw_time_end": float(times.max()),
        "raw_span_s": float(times.max() - times.min()),
        "raw_requests_by_utc_day": dict(sorted(day_counts.items())),
        "global_adjacent_request_gaps": describe(global_gaps),
        "same_anchor_consecutive_request_gaps": describe(anchor_gaps),
        "exact_prefix_consecutive_occurrence_gaps_rebuilt_from_raw": describe(prefix_gaps),
        "constructed_npz_observed_history_ge_1_all": describe(constructed_all),
        "constructed_npz_observed_history_ge_1_test": describe(constructed_test),
        "constructed_npz_censored_history_ge_1_test": describe(censored_test),
        "anchors": len(anchor_request_counts),
        "anchors_with_multiple_requests": int(sum(v >= 2 for v in anchor_request_counts.values())),
        "anchor_request_count_quantiles": {
            str(q): float(np.quantile(list(anchor_request_counts.values()), q))
            for q in (0.5, 0.9, 0.95, 0.99)
        },
        "parse_meta": meta,
    }
    a.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
