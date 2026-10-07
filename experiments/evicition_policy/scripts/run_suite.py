#!/usr/bin/env python3
"""Restart an owned official service for each run; retain every failure."""

import argparse
import asyncio
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
import uuid

import aiohttp

from check_admission import validate_admission
from exploration_gate import verify_release
from prepare_data import ROOT, canonical_digest, digest_file, save_json
from replay_agent import append_record, replay, validate_workload
from server_command import build_command
from shape_warmup import run_shapes, validate_shapes
from verify_protocol import verify


def pool_capacities(log_text: str, tensor_parallel_size: int) -> dict:
    pattern = r"TP(\d+)\] DSV4 pool sizes: full=(\d+), swa=(\d+), c4=(\d+), c128=(\d+), c4_state=(\d+), c128_state=(\d+)"
    ranks = {}
    for match in re.finditer(pattern, log_text):
        ranks[int(match[1])] = tuple(int(value) for value in match.groups()[1:])
    if set(ranks) != set(range(tensor_parallel_size)) or len(set(ranks.values())) != 1:
        raise ValueError("Missing or inconsistent final pool capacities across TP ranks")
    return dict(zip(["full_tokens", "swa_tokens", "c4_slots", "c128_slots", "c4_state_slots", "c128_state_slots"], ranks[0]))


def effective_signature(info: dict, log_text: str, config: dict, policy: str) -> dict:
    if info.get("version") != "0.5.13.post1" or info.get("radix_eviction_policy") != policy:
        raise ValueError("Running version/policy mismatch")
    if "impl=UnifiedRadixCache" not in log_text:
        raise ValueError("Unified cache backend not confirmed")
    capacity = pool_capacities(log_text, config["tensor_parallel_size"])
    if capacity["full_tokens"] != info.get("max_total_num_tokens"):
        raise ValueError("Pool logs and server capacity disagree")
    if capacity["full_tokens"] != config["max_total_tokens"]:
        raise ValueError("Actual Full capacity differs from frozen requested capacity")
    expected = config["expected_effective_graphs"]
    graphs = {"decode": not info["disable_cuda_graph"], "prefill": not info["disable_piecewise_cuda_graph"]}
    if graphs != expected:
        raise ValueError(f"Effective CUDA Graph settings differ: {graphs}")
    if info.get("incremental_streaming_output") or info.get("stream_interval") != 1:
        raise ValueError("Replay requires cumulative token IDs and stream interval one")
    names = ["model_path", "version", "attention_backend", "kv_cache_dtype", "page_size", "tp_size",
             "max_running_requests", "context_length", "chunked_prefill_size", "schedule_policy",
             "moe_runner_backend", "random_seed", "cuda_graph_bs", "swa_full_tokens_ratio"]
    return {"server": {name: info[name] for name in names}, "graphs": graphs,
            "cache_backend": "UnifiedRadixCache", "capacities": capacity}


def port_free(host: str, port: int) -> bool:
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex((host, port)) != 0


def gpu_processes() -> str:
    result = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
                            text=True, capture_output=True, timeout=15, check=True)
    return result.stdout.strip()


def wait_gpu_release(owned_pids: list[int], timeout: float = 60) -> list[dict]:
    deadline = time.monotonic() + timeout
    samples = []
    while True:
        listing = gpu_processes()
        rows = listing.splitlines() if listing else []
        remaining = [line for line in rows if int(line.split(",", 1)[0].strip()) in owned_pids]
        samples.append({"monotonic_seconds": time.monotonic(), "owned_gpu_rows": remaining})
        if not remaining:
            return samples
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Owned GPU allocations did not disappear: {remaining}")
        time.sleep(0.5)


def group_members(group_id: int) -> list[int]:
    result = subprocess.run(["ps", "-eo", "pid=,pgid=,stat="], text=True, capture_output=True, check=True)
    return [int(parts[0]) for line in result.stdout.splitlines() if len(parts := line.split()) == 3
            and int(parts[1]) == group_id and not parts[2].startswith("Z")]


def stop_owned(process: subprocess.Popen) -> dict:
    group_id = process.pid
    if group_id == os.getpgrp():
        raise RuntimeError("Refusing to signal the controller process group")
    members_before = group_members(group_id)
    if process.poll() is None:
        process.terminate()
    elif members_before:
        os.killpg(group_id, signal.SIGTERM)
    deadline = time.monotonic() + 45
    while group_members(group_id) and time.monotonic() < deadline:
        time.sleep(0.25)
        process.poll()
    forced = bool(group_members(group_id))
    if forced:
        os.killpg(group_id, signal.SIGKILL)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass
    remaining = group_members(group_id)
    if remaining:
        raise RuntimeError(f"Owned service group did not stop: {remaining}")
    release_samples = wait_gpu_release(members_before)
    return {"pid": process.pid, "group_members_before": members_before, "forced_kill": forced,
            "remaining_group_members": remaining, "exit_code": process.returncode,
            "gpu_release_samples": release_samples, "owned_gpu_allocations_released": True}


async def request_text(client, base_url, endpoint, method="GET"):
    async with client.request(method, base_url + endpoint, timeout=aiohttp.ClientTimeout(total=180)) as response:
        result = await response.text()
        if response.status != 200:
            raise RuntimeError(f"{endpoint}: HTTP {response.status}: {result[:500]}")
        return result


def cache_is_empty(metrics: str) -> bool:
    names = {"sglang:num_running_reqs", "sglang:num_queue_reqs", "sglang:kv_evictable_tokens",
             "sglang:kv_used_tokens", "sglang:swa_evictable_tokens"}
    observed = {name: [] for name in names}
    for line in metrics.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name = line.split("{", 1)[0].split()[0]
        if name in names:
            observed[name].append(float(line.rsplit(" ", 1)[1]))
    return all(values and all(value == 0 for value in values) for values in observed.values())


async def verify_empty_cache(client, base_url):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        metrics = await request_text(client, base_url, "/metrics")
        if cache_is_empty(metrics):
            return metrics
        await asyncio.sleep(1)
    raise ValueError("Native metrics did not confirm idle/empty cache after flush")


async def wait_ready(client, base_url, process, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited before ready: {process.returncode}")
        try:
            async with client.get(base_url + "/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    return
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        await asyncio.sleep(2)
    raise TimeoutError("Service readiness deadline exceeded; no fallback configuration applied")


async def monitor(client, base_url, output, stopped):
    with (output / "monitor.jsonl").open("x") as stream:
        while not stopped.is_set():
            sample = {"timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
            try:
                sample["metrics"] = await request_text(client, base_url, "/metrics")
                result = await asyncio.to_thread(subprocess.run, ["nvidia-smi", "--query-gpu=index,uuid,memory.used,utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader"],
                                                 text=True, capture_output=True, timeout=10)
                sample["gpu_csv"] = result.stdout
                sample["gpu_exit_code"] = result.returncode
            except Exception as error:
                sample["error"] = repr(error)
            append_record(stream, sample)
            try:
                await asyncio.wait_for(stopped.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass


async def run_once(
    config,
    config_path,
    workload,
    warmup,
    policy,
    output,
    expected_signature,
    ready_timeout,
    shapes=None,
    *,
    strategy=None,
    exposure_barrier=False,
):
    strategy = strategy or policy
    output.mkdir(parents=True, exist_ok=False)
    state = {"status": "starting", "policy": policy, "strategy": strategy,
             "exposure_barrier": bool(exposure_barrier), "purpose": workload["purpose"],
             "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    save_json(output / "state.json", state)
    save_json(output / "config.resolved.json", config)
    save_json(output / "workload.json", workload)
    if shapes is not None:
        save_json(output / "shape_warmup_plan.json", shapes)
    base_url = f"http://{config['host']}:{config['port']}"
    if not port_free(config["host"], config["port"]):
        state.update(status="failed", error="Port already occupied")
        save_json(output / "state.json", state)
        raise RuntimeError("Port already occupied; refusing to adopt or kill existing service")
    occupied = gpu_processes()
    if occupied:
        state.update(status="failed", error="GPU compute processes already present")
        save_json(output / "state.json", state)
        raise RuntimeError(f"GPUs already have compute processes; refusing interference: {occupied}")
    command = ["bash", str(ROOT / "scripts/run_server.sh"), "--config", str(config_path), "--policy", policy]
    patch_lock = ROOT / "configs/environment.diagnostics.lock.json"
    save_json(output / "command.json", {"wrapper": command, "resolved": build_command(config, policy),
                                        "strategy": strategy, "exposure_barrier": bool(exposure_barrier),
                                        "environment_lock_sha256": digest_file(ROOT / "configs/environment.lock.json"),
                                        "diagnostics_patch_lock_sha256": digest_file(patch_lock) if patch_lock.exists() else None,
                                        "workload_sha256": canonical_digest(workload)})
    scripts = sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "scripts").glob("*.sh"))
    save_json(output / "script_fingerprints.json", {path.name: digest_file(path) for path in scripts})
    log_file = (output / "server.log").open("x")
    env = os.environ.copy()
    if exposure_barrier:
        env["AGENTKV_EXPOSURE_BARRIER"] = "1"
    else:
        env.pop("AGENTKV_EXPOSURE_BARRIER", None)
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log_file,
                               stderr=subprocess.STDOUT, start_new_session=True)
    save_json(output / "process.json", {"pid": process.pid, "pgid": process.pid,
                                       "proc_start_ticks": Path(f"/proc/{process.pid}/stat").read_text().split(")", 1)[1].split()[19]})
    signature = None
    stopped = asyncio.Event()
    monitor_task = None
    try:
        async with aiohttp.ClientSession() as client:
            await wait_ready(client, base_url, process, ready_timeout)
            info = json.loads(await request_text(client, base_url, "/server_info"))
            save_json(output / "server_info_before.json", info)
            signature = effective_signature(info, (output / "server.log").read_text(), config, policy)
            save_json(output / "effective_signature.json", signature)
            if expected_signature is not None and signature != expected_signature:
                raise ValueError("Actual capacities/backend/graphs differ from previous run")
            if shapes is not None:
                validate_shapes(shapes, info)
            save_json(output / "admission.json", {
                "measurement": validate_admission(validate_workload(workload), workload, info),
                "warmup": validate_admission(validate_workload(warmup), warmup, info)})
            state["status"] = "verifying_protocol"
            save_json(output / "state.json", state)
            protocol = await asyncio.to_thread(verify, base_url, warmup)
            save_json(output / "protocol.json", protocol)
            if protocol["status"] != "passed":
                raise ValueError("Online encoding/generation protocol verification failed")
            await replay(base_url, warmup, output / "warmup", context={"run_id": output.name, "policy": strategy, "phase": "warmup"})
            if shapes is not None:
                state["status"] = "shape_warmup"
                save_json(output / "state.json", state)
                for pass_index in range(shapes["passes"]):
                    shape_flush = await request_text(client, base_url, "/flush_cache?timeout=120", "POST")
                    if "Cache flushed." not in shape_flush:
                        raise ValueError("Shape warmup cache flush failed")
                    (output / f"shape_pass_{pass_index + 1}_empty.prom").write_text(await verify_empty_cache(client, base_url))
                    await run_shapes(client, base_url, shapes, output / f"shape_pass_{pass_index + 1}")
            flush = await request_text(client, base_url, "/flush_cache?timeout=120", "POST")
            save_json(output / "flush.json", {"success": "Cache flushed." in flush, "response": flush})
            if "Cache flushed." not in flush:
                raise ValueError("Cache flush not acknowledged")
            info_after_flush = json.loads(await request_text(client, base_url, "/server_info"))
            save_json(output / "server_info_after_flush.json", info_after_flush)
            (output / "metrics_before.prom").write_text(await verify_empty_cache(client, base_url))
            state["status"] = "replaying"
            save_json(output / "state.json", state)
            monitor_task = asyncio.create_task(monitor(client, base_url, output, stopped))
            summary = await asyncio.wait_for(
                replay(base_url, workload, output / "measurement", context={"run_id": output.name, "policy": strategy, "phase": "measurement"}),
                timeout=config.get("measurement_timeout_seconds"))
            if summary["completed_requests"] != workload["requests"]:
                raise ValueError("Incomplete workload")
            save_json(output / "server_info_after.json", json.loads(await request_text(client, base_url, "/server_info")))
            (output / "metrics_after.prom").write_text(await request_text(client, base_url, "/metrics"))
            state["status"] = "completed"
            stopped.set()
            await monitor_task
    except BaseException as error:
        state["status"] = "interrupted" if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)) else "failed"
        state["error"] = repr(error)
        raise
    finally:
        stopped.set()
        if monitor_task is not None and not monitor_task.done():
            monitor_task.cancel()
            await asyncio.gather(monitor_task, return_exceptions=True)
        try:
            cleanup = await asyncio.to_thread(stop_owned, process)
            save_json(output / "cleanup.json", cleanup)
            deadline = time.monotonic() + 30
            while not port_free(config["host"], config["port"]) and time.monotonic() < deadline:
                await asyncio.sleep(0.5)
            if not port_free(config["host"], config["port"]):
                raise RuntimeError("Port is still occupied after owned service stop")
        except BaseException as error:
            state["status"] = "cleanup_failed"
            state["cleanup_error"] = repr(error)
            raise
        finally:
            log_file.close()
            state["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            save_json(output / "state.json", state)
    return signature


async def suite(args):
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text())
    workload = json.loads(args.workload.read_text())
    warmup = json.loads(args.warmup.read_text())
    shapes_path = getattr(args, "shape_warmup", None)
    shapes = json.loads(shapes_path.read_text()) if shapes_path is not None else None
    configured_admission = {"context_length": config["context_length"],
                            "max_total_num_tokens": config["max_total_tokens"], "page_size": config["page_size"]}
    validate_admission(validate_workload(workload), workload, configured_admission)
    validate_admission(validate_workload(warmup), warmup, configured_admission)
    if shapes is not None:
        validate_shapes(shapes, configured_admission)
    if warmup["purpose"] != "smoke":
        raise ValueError("Use the fixed smoke workload as engineering warmup")
    release = None
    if workload["purpose"] == "formal":
        release_path = getattr(args, "release", None)
        if release_path is None:
            raise ValueError("Formal run gate requires passed density and shape validation")
        release = verify_release(release_path, config_path, args.workload, args.warmup, shapes_path, args.policies)
    if not (ROOT / "configs/environment.lock.json").is_file():
        raise ValueError("Environment lock missing")
    results_category = "runs" if workload["purpose"] == "formal" else "pilot"
    destination = ROOT / "results" / results_category / (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True)
    resolved = {"status": "running", "purpose": workload["purpose"], "policies": args.policies,
                "config_sha256": digest_file(config_path), "workload_sha256": digest_file(args.workload),
                "warmup_sha256": digest_file(args.warmup), "runs": []}
    save_json(destination / "suite.json", resolved)
    on_created = getattr(args, "on_created", None)
    if on_created is not None:
        on_created(destination)
    if release is not None:
        save_json(destination / "validation_release.json", release)
    print(json.dumps({"suite": str(destination)}, ensure_ascii=False), flush=True)
    expected = release["effective_signature"] if release is not None else None
    try:
        for index, policy in enumerate(args.policies):
            if release is not None:
                verify_release(args.release, config_path, args.workload, args.warmup, shapes_path, args.policies)
            output = destination / f"{index + 1:02d}_{policy}"
            expected = await run_once(config, config_path, workload, warmup, policy, output, expected, args.ready_timeout, shapes)
            if workload["purpose"] == "formal":
                from analyze_results import audit_run
                audit = audit_run(output)
                save_json(output / "integrity.json", audit)
                if (not audit["protocol_integrity_passed"] or not audit["post_flush_native_metrics_empty"]
                        or not audit["cached_tokens_all_known"]):
                    raise ValueError("Completed run failed integrity checks; next policy not started")
            resolved["runs"].append({"policy": policy, "path": output.name, "status": "completed"})
            save_json(destination / "suite.json", resolved)
        resolved["status"] = "completed"
    except BaseException as error:
        resolved["status"] = "interrupted" if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)) else "failed"
        resolved["error"] = repr(error)
        raise
    finally:
        resolved["observed_run_states"] = [
            {"path": str(path.parent.relative_to(destination)), **json.loads(path.read_text())}
            for path in sorted(destination.glob("*/state.json"))]
        save_json(destination / "suite.json", resolved)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/smoke_server.json")
    parser.add_argument("--workload", type=Path, default=ROOT / "data/workloads/smoke_protocol_v1/manifest.json")
    parser.add_argument("--warmup", type=Path, default=ROOT / "data/workloads/smoke_protocol_v1/manifest.json")
    parser.add_argument("--policies", nargs="+", choices=["lru", "lfu", "slru"], default=["lru", "lfu", "slru"])
    parser.add_argument("--ready-timeout", type=float, default=3600)
    parser.add_argument("--shape-warmup", type=Path)
    parser.add_argument("--release", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Received signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    with (ROOT / "runtime/suite.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(suite(args))


if __name__ == "__main__":
    main()
