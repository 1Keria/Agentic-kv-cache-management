#!/usr/bin/env python3
"""Resume only the missing unified-barrier case in an existing large suite."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import signal

from analyze_calibration import summarize_run
from analyze_results import audit_run
from check_admission import validate_admission
from prepare_data import ROOT, save_json
from replay_agent import validate_workload
from run_large_unified_barrier import (
    verify_inputs,
    verify_patch_installation,
    wait_for_idle_gpus,
)
from run_suite import run_once
from shape_warmup import validate_shapes


CASE = {
    "strategy": "unified_exposure_barrier",
    "policy": "lru",
    "exposure_barrier": True,
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_completed_baselines(suite: Path, manifest: dict) -> dict:
    completed = {
        run["strategy"]: run
        for run in manifest.get("runs", [])
        if run.get("status") == "completed"
    }
    if set(completed) & {"unified_exposure_barrier"}:
        raise ValueError("Unified Exposure Barrier is already complete")
    if not {"lru", "slru"} <= set(completed):
        raise ValueError("Completed LRU and SLRU baselines are required")

    signatures = {}
    for strategy in ("lru", "slru"):
        run = suite / completed[strategy]["path"]
        audit = audit_run(run)
        if not (
            audit["protocol_integrity_passed"]
            and audit["post_flush_native_metrics_empty"]
            and audit["cached_tokens_all_known"]
        ):
            raise ValueError(f"Stored {strategy} baseline no longer passes integrity")
        signatures[strategy] = load_json(run / "effective_signature.json")
    if signatures["lru"] != signatures["slru"]:
        raise ValueError("Completed baseline effective signatures disagree")
    return signatures["slru"]


def next_retry_path(suite: Path, retry_number: int) -> Path:
    index = max(
        (
            int(path.name.split("_", 1)[0])
            for path in suite.iterdir()
            if path.is_dir() and path.name.split("_", 1)[0].isdigit()
        ),
        default=3,
    ) + 1
    return suite / f"{index:02d}_unified_exposure_barrier_retry{retry_number}"


def retryable_startup_failure(output: Path, error: BaseException) -> bool:
    if (output / "measurement").exists() or (output / "server_info_before.json").exists():
        return False
    text = repr(error)
    log_path = output / "server.log"
    if log_path.exists():
        text += "\n" + log_path.read_text(errors="replace")
    markers = (
        "Service exited before ready",
        "GPU compute processes already present",
        "The memory capacity is unbalanced",
        "Some GPUs may be occupied by other processes",
    )
    return any(marker in text for marker in markers)


async def execute(args) -> None:
    suite = args.suite.resolve()
    manifest_path = suite / "suite.json"
    manifest = load_json(manifest_path)
    if manifest.get("schema") != "agentkv_large_unified_barrier_suite_v1":
        raise ValueError("Not a large unified-barrier suite")
    if manifest.get("status") == "completed":
        return

    expected_signature = verify_completed_baselines(suite, manifest)
    prepared = ROOT / manifest["prepared"]
    config_path = args.config.resolve()
    if verify_inputs(prepared, config_path) != manifest["input_verification"]:
        raise ValueError("Frozen inputs/config differ from the original suite")
    if verify_patch_installation() != manifest["patch_verification"]:
        raise ValueError("Installed AgentKV patch differs from the original suite")

    config = load_json(config_path)
    workload = load_json(prepared / "evaluation.json")
    warmup = load_json(ROOT / "data/workloads/smoke_protocol_v1/manifest.json")
    shapes = load_json(prepared / "shape_warmup.json")
    admission = {
        "context_length": config["context_length"],
        "max_total_num_tokens": config["max_total_tokens"],
        "page_size": config["page_size"],
    }
    validate_admission(validate_workload(workload), workload, admission)
    validate_admission(validate_workload(warmup), warmup, admission)
    validate_shapes(shapes, admission)

    history = manifest.setdefault("recovery_history", [])
    manifest["status"] = "recovering"
    manifest["recovery_started_at_utc"] = utc_now()
    original_error = manifest.pop("error", None)
    if original_error is not None:
        manifest["original_error"] = original_error
    save_json(manifest_path, manifest)

    for retry_number in range(1, args.max_retries + 1):
        await wait_for_idle_gpus(
            args.gpu_wait_timeout,
            stable_seconds=args.gpu_idle_stability_seconds,
            poll_seconds=args.gpu_poll_seconds,
        )
        output = next_retry_path(suite, retry_number)
        attempt = {
            "retry": retry_number,
            "path": output.name,
            "status": "running",
            "started_at_utc": utc_now(),
            "gpu_idle_stability_seconds": args.gpu_idle_stability_seconds,
        }
        history.append(attempt)
        save_json(manifest_path, manifest)
        try:
            signature = await run_once(
                config,
                config_path,
                workload,
                warmup,
                CASE["policy"],
                output,
                expected_signature,
                args.ready_timeout,
                shapes,
                strategy=CASE["strategy"],
                exposure_barrier=CASE["exposure_barrier"],
            )
            if signature != expected_signature:
                raise ValueError("Recovered run effective signature drifted")
            audit = audit_run(output)
            save_json(output / "integrity.json", audit)
            descriptive = summarize_run(output)
            descriptive["purpose"] = "large_unified_barrier_single_pass"
            save_json(output / "descriptive_analysis.json", descriptive)
            if not (
                audit["protocol_integrity_passed"]
                and audit["post_flush_native_metrics_empty"]
                and audit["cached_tokens_all_known"]
            ):
                raise ValueError("Integrity failure for unified_exposure_barrier")

            manifest["runs"].append(
                {
                    **CASE,
                    "path": output.name,
                    "status": "completed",
                    "integrity_passed": True,
                    "recovered": True,
                }
            )
            attempt.update(status="completed", completed_at_utc=utc_now())
            manifest["status"] = "completed"
            manifest["completed_at_utc"] = utc_now()
            manifest.pop("recovery_error", None)
            save_json(manifest_path, manifest)
            return
        except BaseException as error:
            attempt.update(
                status="failed",
                completed_at_utc=utc_now(),
                error=repr(error),
                retryable_startup_failure=retryable_startup_failure(output, error),
            )
            manifest["recovery_error"] = repr(error)
            save_json(manifest_path, manifest)
            if not attempt["retryable_startup_failure"] or retry_number == args.max_retries:
                manifest["status"] = "failed"
                manifest["completed_at_utc"] = utc_now()
                save_json(manifest_path, manifest)
                raise
            await asyncio.sleep(args.retry_delay_seconds)

    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/large_unified_barrier_server.json",
    )
    parser.add_argument("--ready-timeout", type=float, default=3600)
    parser.add_argument("--gpu-wait-timeout", type=float, default=43200)
    parser.add_argument("--gpu-idle-stability-seconds", type=float, default=60)
    parser.add_argument("--gpu-poll-seconds", type=float, default=5)
    parser.add_argument("--retry-delay-seconds", type=float, default=30)
    parser.add_argument("--max-retries", type=int, default=20)
    args = parser.parse_args()
    os.umask(0o077)

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Received signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    with (ROOT / "runtime/suite.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(execute(args))


if __name__ == "__main__":
    main()
