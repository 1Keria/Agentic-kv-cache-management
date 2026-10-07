#!/usr/bin/env python3
"""Run the frozen 20-session workload for LRU, SLRU, and unified barrier."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import signal
import time
import uuid

from analyze_calibration import summarize_run
from analyze_results import audit_run
from check_admission import validate_admission
from prepare_data import ROOT, digest_file, save_json
from replay_agent import validate_workload
from run_suite import gpu_processes, run_once
from shape_warmup import validate_shapes


CASES = (
    {"strategy": "lru", "policy": "lru", "exposure_barrier": False},
    {"strategy": "slru", "policy": "slru", "exposure_barrier": False},
    {
        "strategy": "unified_exposure_barrier",
        "policy": "lru",
        "exposure_barrier": True,
    },
)


def verify_patch_installation() -> dict:
    lock_path = ROOT / "configs/environment.diagnostics.lock.json"
    lock = json.loads(lock_path.read_text())
    package = ROOT / "runtime/venv/lib/python3.12/site-packages/sglang/srt/mem_cache"
    checked = {}
    for relative, details in lock["files"].items():
        target = package / relative
        expected = details.get("patched_sha256", details.get("installed_sha256"))
        actual = digest_file(target)
        if actual != expected:
            raise ValueError(f"Installed AgentKV patch drift: {relative}")
        checked[relative] = actual
    return {
        "patch_lock_sha256": digest_file(lock_path),
        "features": lock.get("features", {}),
        "installed_files": checked,
    }


def verify_inputs(prepared: Path, config_path: Path) -> dict:
    metadata = json.loads((prepared / "prepared.json").read_text())
    for name in ("evaluation.json", "shape_warmup.json"):
        if digest_file(prepared / name) != metadata["artifact_sha256"][name]:
            raise ValueError(f"Frozen input drift: {name}")
    if metadata["evaluation_session_count"] != 20:
        raise ValueError("Expected the frozen 20-session evaluation workload")
    if metadata["inter_request_gap_scale"] != 0.3:
        raise ValueError("Expected the frozen accelerated timing transform")
    config = json.loads(config_path.read_text())
    if not Path(config["model_path"]).is_dir():
        raise ValueError("Configured model path is unavailable")
    if config["max_total_tokens"] != metadata["max_total_tokens"]:
        raise ValueError("Large-scale cache capacity drift")
    return {
        "prepared_sha256": digest_file(prepared / "prepared.json"),
        "evaluation_sha256": digest_file(prepared / "evaluation.json"),
        "shape_warmup_sha256": digest_file(prepared / "shape_warmup.json"),
        "config_sha256": digest_file(config_path),
        "sessions": metadata["evaluation_session_count"],
        "requests": json.loads((prepared / "evaluation.json").read_text())["requests"],
    }


async def wait_for_idle_gpus(
    timeout: float,
    *,
    stable_seconds: float = 0,
    poll_seconds: float = 15,
) -> None:
    deadline = time.monotonic() + timeout
    idle_since = None
    while True:
        occupied = gpu_processes()
        now = time.monotonic()
        if not occupied:
            if idle_since is None:
                idle_since = now
            if now - idle_since >= stable_seconds:
                return
        else:
            idle_since = None
        if now >= deadline:
            raise TimeoutError("GPUs did not become idle before the configured deadline")
        await asyncio.sleep(min(poll_seconds, max(0.1, deadline - now)))


async def execute(args, destination: Path) -> None:
    prepared = args.prepared.resolve()
    config_path = args.config.resolve()
    warmup_path = ROOT / "data/workloads/smoke_protocol_v1/manifest.json"
    workload_path = prepared / "evaluation.json"
    shapes_path = prepared / "shape_warmup.json"
    config = json.loads(config_path.read_text())
    workload = json.loads(workload_path.read_text())
    warmup = json.loads(warmup_path.read_text())
    shapes = json.loads(shapes_path.read_text())
    admission = {
        "context_length": config["context_length"],
        "max_total_num_tokens": config["max_total_tokens"],
        "page_size": config["page_size"],
    }
    validate_admission(validate_workload(workload), workload, admission)
    validate_admission(validate_workload(warmup), warmup, admission)
    validate_shapes(shapes, admission)
    if workload["purpose"] != "formal" or workload["requests"] != 1206:
        raise ValueError("Unexpected large-scale workload")

    manifest = {
        "schema": "agentkv_large_unified_barrier_suite_v1",
        "status": "running",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "prepared": str(prepared.relative_to(ROOT)),
        "cases": list(CASES),
        "runs": [],
        "input_verification": verify_inputs(prepared, config_path),
        "patch_verification": verify_patch_installation(),
    }
    save_json(destination / "suite.json", manifest)
    expected_signature = None
    try:
        for index, case in enumerate(CASES, start=1):
            await wait_for_idle_gpus(
                args.gpu_wait_timeout,
                stable_seconds=args.gpu_idle_stability_seconds,
            )
            output = destination / f"{index:02d}_{case['strategy']}"
            expected_signature = await run_once(
                config,
                config_path,
                workload,
                warmup,
                case["policy"],
                output,
                expected_signature,
                args.ready_timeout,
                shapes,
                strategy=case["strategy"],
                exposure_barrier=case["exposure_barrier"],
            )
            audit = audit_run(output)
            save_json(output / "integrity.json", audit)
            descriptive = summarize_run(output)
            descriptive["purpose"] = "large_unified_barrier_single_pass"
            save_json(output / "descriptive_analysis.json", descriptive)
            if (
                not audit["protocol_integrity_passed"]
                or not audit["post_flush_native_metrics_empty"]
                or not audit["cached_tokens_all_known"]
            ):
                raise ValueError(f"Integrity failure for {case['strategy']}")
            manifest["runs"].append(
                {
                    **case,
                    "path": output.name,
                    "status": "completed",
                    "integrity_passed": True,
                }
            )
            save_json(destination / "suite.json", manifest)
        manifest["status"] = "completed"
    except BaseException as error:
        manifest["status"] = (
            "interrupted"
            if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt))
            else "failed"
        )
        manifest["error"] = repr(error)
        raise
    finally:
        manifest["completed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_json(destination / "suite.json", manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepared",
        type=Path,
        default=ROOT / "data/workloads/exploration_1h_v4",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/large_unified_barrier_server.json",
    )
    parser.add_argument("--ready-timeout", type=float, default=3600)
    parser.add_argument("--gpu-wait-timeout", type=float, default=43200)
    parser.add_argument("--gpu-idle-stability-seconds", type=float, default=60)
    args = parser.parse_args()
    os.umask(0o077)
    destination = ROOT / "results/runs" / (
        "large_unified_barrier_"
        + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "_"
        + uuid.uuid4().hex[:8]
    )

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Received signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    with (ROOT / "runtime/suite.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        destination.mkdir(parents=True, exist_ok=False)
        print(json.dumps({"suite": str(destination)}, ensure_ascii=False), flush=True)
        asyncio.run(execute(args, destination))


if __name__ == "__main__":
    main()
