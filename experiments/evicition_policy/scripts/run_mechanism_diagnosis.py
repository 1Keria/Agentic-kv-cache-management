#!/usr/bin/env python3
"""Observe complete frozen Agent-only runs; keep timing out of policy ranking."""

import argparse
import asyncio
import csv
import datetime
import fcntl
import json
import os
from pathlib import Path
import uuid

from analyze_results import audit_run
from prepare_data import ROOT, digest_file, save_json
from replay_agent import validate_workload
from run_suite import run_once


def read(path):
    return json.loads(path.read_text())


def select_cases(source):
    with (source / "paired_requests.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    cases = []
    fields = [name for name in rows[0] if name.startswith("previous_input_lcp_shortfall_proxy_tokens_")]
    common = sorted(rows, key=lambda row: min(int(row[name]) for name in fields), reverse=True)
    sessions = set()
    for row in common:
        minimum = min(int(row[name]) for name in fields)
        if minimum < 8192 or row["session_id"] in sessions:
            continue
        sessions.add(row["session_id"])
        cases.append({"kind": "large_common_shortfall", "session_id": row["session_id"],
                      "task_id": row["task_id"], "turn_index": int(row["turn_index"]),
                      "minimum_four_run_lcp_proxy_tokens": minimum})
        if len(sessions) == 4:
            break
    for sign, label in ((1, "stable_slru_more_cached"), (-1, "stable_slru_less_cached")):
        stable = [row for row in rows if sign * int(row["slru_minus_lru_batch1"]) >= 8192
                  and sign * int(row["slru_minus_lru_batch2"]) >= 8192]
        stable.sort(key=lambda row: min(sign * int(row["slru_minus_lru_batch1"]),
                                       sign * int(row["slru_minus_lru_batch2"])), reverse=True)
        for row in stable[:2]:
            cases.append({"kind": label, "session_id": row["session_id"], "task_id": row["task_id"],
                          "turn_index": int(row["turn_index"]),
                          "slru_minus_lru_batch1": int(row["slru_minus_lru_batch1"]),
                          "slru_minus_lru_batch2": int(row["slru_minus_lru_batch2"])})
    return {"selection_rule": "four largest common >=8K gaps from distinct sessions plus two stable >=8K positive/negative cases",
            "selected_before_diagnostic_run": True, "cases": cases,
            "source_csv_sha256": digest_file(source / "paired_requests.csv"),
            "note": "Case selection does not remove requests; all 20 complete sessions are replayed."}


async def execute(args, output):
    prior = read(args.source_batch / "batch.json")
    if prior["status"] != "completed":
        raise ValueError("Source repeat batch is incomplete")
    paths = {name: ROOT / prior[name] for name in ("config", "workload", "warmup", "shape_warmup")}
    for name, path in paths.items():
        if digest_file(path) != prior["input_sha256"][name]:
            raise ValueError(f"Frozen {name} changed")
    config, workload, warmup, shapes = (read(paths[name]) for name in ("config", "workload", "warmup", "shape_warmup"))
    validate_workload(workload)
    if workload["requests"] != 1206 or len(workload["sessions"]) != 20:
        raise ValueError("Unexpected workload extent")
    if not Path(config["model_path"]).is_dir():
        raise ValueError("Previously verified model snapshot unavailable")
    overlay = args.overlay.resolve()
    overlay_lock = read(overlay / "observation.lock.json")
    if overlay_lock["observer_sha256"] != digest_file(ROOT / "scripts/mechanism_observer.py"):
        raise ValueError("Observer overlay is stale")
    selection = select_cases(args.source_analysis)
    save_json(output / "selected_cases.json", selection)
    state = {"status": "running", "purpose": "read_only_reclamation_mechanism_diagnosis",
             "native_decisions_unchanged": True, "latency_ranking_allowed": False,
             "policies": args.policies, "source_batch": str(args.source_batch.relative_to(ROOT)),
             "input_sha256": prior["input_sha256"], "overlay": str(overlay.relative_to(ROOT)),
             "overlay_lock_sha256": digest_file(overlay / "observation.lock.json"), "runs": [],
             "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    save_json(output / "suite.json", state)
    expected = read(args.source_batch / "01_lru_slru/01_lru/effective_signature.json")
    try:
        for i, policy in enumerate(args.policies, 1):
            path = output / f"{i:02d}_{policy}"
            print(json.dumps({"starting": str(path), "policy": policy}), flush=True)
            await run_once(config, paths["config"], workload, warmup, policy, path, expected,
                           args.ready_timeout, shapes, observation_overlay=overlay)
            audit = audit_run(path)
            save_json(path / "integrity.json", audit)
            if not all(audit[name] for name in ("protocol_integrity_passed", "post_flush_native_metrics_empty",
                                                 "cached_tokens_all_known", "cleanup_confirmed")):
                raise ValueError(f"Run integrity failed: {audit['integrity_errors']}")
            state["runs"].append({"policy": policy, "path": path.name, "integrity_passed": True})
            save_json(output / "suite.json", state)
        state["status"] = "completed"
    except BaseException as error:
        state.update(status="failed", error=repr(error))
        raise
    finally:
        state["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_json(output / "suite.json", state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-batch", type=Path, default=ROOT / "results/order_balanced/20261008T035423Z_1593ea96")
    parser.add_argument("--source-analysis", type=Path, default=ROOT / "results/analysis/order_balanced_20261008")
    parser.add_argument("--overlay", type=Path, default=ROOT / "runtime/mechanism_overlay_20261008")
    parser.add_argument("--policies", nargs="+", choices=["lru", "slru"], default=["lru", "slru"])
    parser.add_argument("--ready-timeout", type=float, default=3600)
    args = parser.parse_args()
    os.umask(0o077)
    output = ROOT / "results/mechanism" / (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    print(json.dumps({"suite": str(output)}), flush=True)
    with (ROOT / "runtime/suite.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(execute(args, output))


if __name__ == "__main__":
    main()
