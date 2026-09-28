#!/usr/bin/env python3
"""Validate once, then run the user-approved three policies without extra prompts."""

import argparse
import asyncio
import datetime
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from types import SimpleNamespace
import uuid
import zipfile

import sglang

from analyze_calibration import summarize_run
from exploration_gate import validation_errors
from prepare_data import ROOT, digest_file, save_json
from run_suite import suite


def verify_environment() -> dict:
    lock = json.loads((ROOT / "configs/environment.lock.json").read_text())
    origin = Path(sglang.__file__).resolve().parent
    if str(origin) != lock["engine"]["origin"] or importlib.metadata.version("sglang") != lock["engine"]["version"]:
        raise ValueError("Engine origin or release drift")
    wheel = ROOT / lock["engine"]["wheel"]
    if digest_file(wheel) != lock["engine"]["wheel_sha256"]:
        raise ValueError("Official wheel drift")
    verified = 0
    with zipfile.ZipFile(wheel) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.startswith("sglang/"):
                continue
            installed = origin.parent / entry.filename
            if not installed.is_file() or digest_file(installed) != hashlib.sha256(archive.read(entry)).hexdigest():
                raise ValueError("Installed engine differs from locked wheel: " + entry.filename)
            verified += 1
    model = Path(lock["model"]["path"])
    for name, expected in lock["model"]["metadata_sha256"].items():
        if digest_file(model / name) != expected:
            raise ValueError("Model metadata changed: " + name)
    shards = list(model.glob("*.safetensors"))
    if len(shards) != lock["model"]["weight_shards"] or sum(path.stat().st_size for path in shards) != lock["model"]["weight_bytes"]:
        raise ValueError("Model shard inventory changed")
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze", "--all"], capture_output=True, text=True, check=True).stdout.splitlines()
    if sorted(freeze) != sorted(lock["dependency_freeze"]):
        raise ValueError("Dependency environment changed")
    checked = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True, check=True).stdout
    if shutil.disk_usage(ROOT).free < 30 * 1024 ** 3:
        raise ValueError("Need at least 30 GiB free for retained experiment logs")
    return {"engine_release": lock["engine"]["version"], "installed_wheel_files_verified": verified,
            "pip_check": checked.strip(), "dependency_freeze_matches": True,
            "model_metadata_and_inventory_verified": True, "full_weight_hashes_verified": False,
            "environment_lock_sha256": digest_file(ROOT / "configs/environment.lock.json")}


def check_prepared(folder: Path) -> dict:
    prepared = json.loads((folder / "prepared.json").read_text())
    if prepared.get("user_authorized_auto_start_after_validation") is not True:
        raise ValueError("Missing validation-to-experiment authorization")
    for name, expected in prepared["artifact_sha256"].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or digest_file(path) != expected:
            raise ValueError("Prepared input drift: " + name)
    if prepared.get("policies") != ["lru", "lfu", "slru"] or prepared.get("repeats_per_policy") != 1:
        raise ValueError("Unexpected experiment matrix")
    if (prepared.get("timing_transform") != "uniform_accelerated_replay_v1"
            or prepared.get("inter_request_gap_scale") != 0.30
            or prepared.get("start_spacing_seconds") != 27.0
            or prepared.get("validation_session_count") != 20
            or prepared.get("evaluation_session_count") != 20
            or prepared.get("max_total_tokens") != 524288
            or prepared.get("complete_session_selection") != "sha256_order_prefix_v1"
            or prepared.get("target_experiment_seconds") != 3600):
        raise ValueError("Expected the frozen one-hour accelerated full-coverage design")
    return prepared


def write_comparison(output: Path, suite_path: Path) -> None:
    suite_state = json.loads((suite_path / "suite.json").read_text())
    results = []
    for path in sorted(suite_path.glob("*/state.json")):
        result = summarize_run(path.parent)
        result["purpose"] = "single_pass_exploratory_comparison"
        result["limitations"] = [note for note in result["limitations"] if not note.startswith("Calibration only")]
        result["limitations"].append("One run per policy; no run-to-run variability, order balance, significance or stable superiority claims")
        save_json(path.parent / "descriptive_analysis.json", result)
        results.append(result)
    summary = {"suite": str(suite_path.relative_to(ROOT)), "suite_status": suite_state["status"],
               "stage": "single_pass_exploratory", "runs": results, "repeats_per_policy": 1,
               "note": "Descriptive differences only; native Full/SWA events are insufficient for exact eviction attribution."}
    save_json(output / "comparison.json", summary)
    lines = ["# 三策略单次探索性对照", "", f"状态：{suite_state['status']}。每种策略一次，不报告稳定领先或统计显著。", "",
             "| 策略 | 完成请求 | 测量分钟 | token 命中率 | TTFT p95 秒 | 撤回次数 | 完整性 |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for result in results:
        audit = result["integrity_audit"]
        hit = audit.get("token_weighted_cache_hit_fraction")
        hit_text = f"{hit * 100:.4f}%" if hit is not None else "未知"
        elapsed = result.get("measurement", {}).get("elapsed_seconds", 0) / 60
        lines.append(f"| {result['state']['policy'].upper()} | {result['completed_requests']} | {elapsed:.2f} | {hit_text} | "
                     f"{result['client_ttft_seconds'].get('p95', '未知')} | {result['native_num_retractions'].get('sum', '未知')} | "
                     f"{'通过' if audit.get('protocol_integrity_passed') else '未通过'} |")
    lines.extend(["", "所有原始请求、输出、运行参数、重启、预热、清缓存、GPU 采样及失败证据保留在对应 suite。",
                  "逐请求 queue_time 已知失真，使用按 rank 的 scheduler 直方图；回收计数不当作单池逻辑 token。",
                  "历史生成与本地生成不一致；未命中量不等于错误淘汰，单轮差异不能用于稳定策略排名。", ""])
    (output / "comparison.md").write_text("\n".join(lines))


async def execute(prepared_dir: Path, output: Path):
    prepared = check_prepared(prepared_dir)
    state = {"status": "checking_environment", "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "prepared": str(prepared_dir.relative_to(ROOT)), "policies": ["lru", "lfu", "slru"],
             "automatic_extra_repeats": False, "timing_transform": prepared["timing_transform"],
             "inter_request_gap_scale": prepared["inter_request_gap_scale"],
             "target_experiment_seconds": prepared["target_experiment_seconds"]}
    def update(status, **values):
        state.update(status=status, updated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), **values)
        save_json(output / "state.json", state)
        print(json.dumps({"status": status, **values}, ensure_ascii=False), flush=True)
    update("checking_environment")
    evaluation_suite = None
    try:
        save_json(output / "environment_verification.json", verify_environment())
        script_hashes = {path.name: digest_file(path) for path in sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "scripts").glob("*.sh"))}
        save_json(output / "script_fingerprints.json", script_hashes)
        warmup = ROOT / "data/workloads/smoke_protocol_v1/manifest.json"
        common = {"config": prepared_dir / "server.json", "warmup": warmup,
                  "shape_warmup": prepared_dir / "shape_warmup.json", "ready_timeout": 3600}
        update("validating_density_and_shapes")
        validation_suite = await suite(SimpleNamespace(**common, workload=prepared_dir / "validation.json", policies=["lru"], release=None,
                                      on_created=lambda path: update("validating_density_and_shapes", validation_suite=str(path.relative_to(ROOT)))))
        update("auditing_validation", validation_suite=str(validation_suite.relative_to(ROOT)))
        result = summarize_run(validation_suite / "01_lru")
        save_json(output / "validation_analysis.json", result)
        criteria = json.loads((prepared_dir / "criteria.json").read_text())
        errors = validation_errors(result, criteria)
        run_path = validation_suite / "01_lru"
        for pass_index in [1, 2]:
            shape_summary = json.loads((run_path / f"shape_pass_{pass_index}" / "summary.json").read_text())
            if shape_summary["status"] != "completed" or shape_summary["completed_requests"] != 12 or shape_summary["maximum_prompt_tokens"] < 172032:
                errors.append("long_shape_warmup_unverified")
        for name, expected in script_hashes.items():
            if digest_file(ROOT / "scripts" / name) != expected:
                errors.append("scripts_changed_during_validation")
        check_prepared(prepared_dir)
        evidence = [output / "validation_analysis.json", output / "environment_verification.json",
                    ROOT / "configs/environment.lock.json", run_path / "state.json", run_path / "cleanup.json",
                    run_path / "effective_signature.json", run_path / "protocol.json", run_path / "metrics_before.prom",
                    run_path / "measurement/summary.json", run_path / "measurement/requests.jsonl",
                    run_path / "shape_pass_1/summary.json", run_path / "shape_pass_2/summary.json", prepared_dir / "criteria.json"]
        release = {"status": "passed" if not errors else "failed", "validation_errors": sorted(set(errors)),
                   "policies": ["lru", "lfu", "slru"], "repeats_per_policy": 1,
                   "effective_signature": result["effective_signature"], "script_sha256": script_hashes,
                   "input_sha256": {"config": digest_file(common["config"]), "workload": digest_file(prepared_dir / "evaluation.json"),
                                    "protocol_warmup": digest_file(warmup), "shape_warmup": digest_file(common["shape_warmup"])},
                   "evidence_sha256": {str(path.relative_to(ROOT)): digest_file(path) for path in evidence},
                   "limitations": ["Calibration tasks validate the chosen density, not all evaluation traffic outcomes",
                                   "Long shape echo/length check is not complete kernel shape coverage",
                                   "No exact Full/SWA eviction attribution and no per-request queue time"]}
        save_json(output / "release.json", release)
        if errors:
            raise ValueError("Validation failed; no evaluation policy started: " + ", ".join(errors))
        update("validation_passed_starting_three_policy_comparison", release=str((output / "release.json").relative_to(ROOT)))
        evaluation_suite = await suite(SimpleNamespace(**common, workload=prepared_dir / "evaluation.json",
                                                      policies=["lru", "lfu", "slru"], release=output / "release.json",
                                                      on_created=lambda path: update("running_three_policy_comparison", evaluation_suite=str(path.relative_to(ROOT)))))
        update("analyzing_three_policy_results", evaluation_suite=str(evaluation_suite.relative_to(ROOT)))
        write_comparison(output, evaluation_suite)
        update("completed", completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    except BaseException as error:
        update("interrupted" if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)) else "failed", error=repr(error))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    args = parser.parse_args()
    prepared = args.prepared.resolve()
    if not prepared.is_relative_to(ROOT):
        raise ValueError("Prepared inputs must stay inside the experiment")
    os.umask(0o077)
    output = ROOT / "results/exploration" / (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Received signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    with (ROOT / "runtime/suite.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output.mkdir(parents=True, exist_ok=False)
        print(json.dumps({"exploration": str(output)}, ensure_ascii=False), flush=True)
        asyncio.run(execute(prepared, output))


if __name__ == "__main__":
    main()
