#!/usr/bin/env python3
"""Run fixed-trace LRU, SLRU, and Exposure Barrier isolation experiments."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from run_exact_diagnostics_suite import ROOT, run_case, save, sha256


REGIMES = {
    "full_only": "configs/exposure_full_only_server.json",
    "swa_only": "configs/exposure_swa_only_server.json",
    "joint": "configs/exposure_joint_server.json",
}


def build_cases(gpu_wait_timeout: int) -> list[dict]:
    cases = [
        {
            "name": "01_control_lru",
            "regime": "control",
            "config": "configs/exposure_control_server.json",
            "strategy": "lru",
            "policy": "lru",
            "exposure_barrier": False,
            "diagnostics": True,
            "gpu_wait_timeout_seconds": gpu_wait_timeout,
        }
    ]
    sequence = 2
    for regime, config in REGIMES.items():
        for strategy, policy, barrier in (
            ("lru", "lru", False),
            ("slru", "slru", False),
            ("exposure_barrier", "lru", True),
        ):
            cases.append(
                {
                    "name": f"{sequence:02d}_{regime}_{strategy}",
                    "regime": regime,
                    "config": config,
                    "strategy": strategy,
                    "policy": policy,
                    "exposure_barrier": barrier,
                    "diagnostics": True,
                    "gpu_wait_timeout_seconds": gpu_wait_timeout,
                }
            )
            sequence += 1
    return cases


def copy_frozen_trace(source: Path, destination: Path) -> str:
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    fields = (
        "request_seq",
        "session_id",
        "turn_index",
        "lifecycle_state",
        "branch_from_turn",
        "input_ids",
        "output_ids",
        "tool_ids",
    )
    with destination.open("x") as stream:
        for row in rows:
            stream.write(
                json.dumps(
                    {field: row.get(field) for field in fields},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
    return sha256(destination)


async def run_suite(args) -> Path:
    cases = build_cases(args.gpu_wait_timeout)
    destination = ROOT / "results/pilot" / (
        "exposure_barrier_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    destination.mkdir(parents=True)
    frozen_trace = destination / "frozen_trace.jsonl"
    frozen_trace_sha256 = copy_frozen_trace(args.frozen_trace.resolve(), frozen_trace)
    manifest = {
        "schema": "agentkv_exposure_barrier_suite_v1",
        "status": "running",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cases": cases,
        "results": [],
        "trace_mode": "captured_fixed",
        "frozen_trace_sha256": frozen_trace_sha256,
        "diagnostics_patch_lock_sha256": sha256(
            ROOT / "configs/environment.diagnostics.lock.json"
        ),
    }
    save(destination / "suite.json", manifest)
    try:
        for case in cases:
            result = await run_case(
                case, destination, args.ready_timeout, frozen_trace
            )
            manifest["results"].append(result)
            save(destination / "suite.json", manifest)
        manifest["status"] = "completed"
    except BaseException as error:
        manifest["status"] = "failed"
        manifest["error"] = repr(error)
        raise
    finally:
        manifest["completed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save(destination / "suite.json", manifest)
    print(destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-trace", type=Path, required=True)
    parser.add_argument("--ready-timeout", type=int, default=1800)
    parser.add_argument("--gpu-wait-timeout", type=int, default=43200)
    args = parser.parse_args()
    asyncio.run(run_suite(args))


if __name__ == "__main__":
    main()
