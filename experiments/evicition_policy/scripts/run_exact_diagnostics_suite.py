#!/usr/bin/env python3
"""Run the exact-continuation control and LRU/SLRU pressure diagnostics."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

import aiohttp


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runtime/venv/bin/python"


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def port_free(host: str, port: int) -> bool:
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex((host, port)) != 0


def gpu_processes() -> list[str]:
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


async def wait_for_idle_gpus(timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while True:
        if not gpu_processes():
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("GPUs did not become idle before the configured deadline")
        await asyncio.sleep(15)


def process_group_members(group_id: int) -> list[int]:
    result = subprocess.run(["ps", "-eo", "pid=,pgid=,stat="], text=True, capture_output=True, check=True)
    output = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and int(parts[1]) == group_id and not parts[2].startswith("Z"):
            output.append(int(parts[0]))
    return output


def stop_service(process: subprocess.Popen) -> dict:
    members = process_group_members(process.pid)
    if members:
        os.killpg(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + 60
    while process_group_members(process.pid) and time.monotonic() < deadline:
        time.sleep(0.5)
    forced = bool(process_group_members(process.pid))
    if forced:
        os.killpg(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        pass
    owned = set(members)
    deadline = time.monotonic() + 90
    while any(int(row.split(",", 1)[0].strip()) in owned for row in gpu_processes()) and time.monotonic() < deadline:
        time.sleep(1)
    remaining = [row for row in gpu_processes() if int(row.split(",", 1)[0].strip()) in owned]
    if remaining:
        raise RuntimeError(f"GPU processes remain after owned service shutdown: {remaining}")
    return {"members_before": members, "forced": forced, "exit_code": process.returncode}


async def request_text(client: aiohttp.ClientSession, base_url: str, endpoint: str, method: str = "GET") -> str:
    async with client.request(method, base_url + endpoint, timeout=aiohttp.ClientTimeout(total=180)) as response:
        text = await response.text()
        if response.status != 200:
            raise RuntimeError(f"{endpoint}: HTTP {response.status}: {text[:500]}")
        return text


async def wait_ready(client: aiohttp.ClientSession, base_url: str, process: subprocess.Popen, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited before readiness: {process.returncode}")
        try:
            async with client.get(base_url + "/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    return
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        await asyncio.sleep(2)
    raise TimeoutError("Server readiness timeout")


async def run_case(case: dict, suite: Path, ready_timeout: int, frozen_trace: Path | None) -> dict:
    output = suite / case["name"]
    output.mkdir()
    config_path = ROOT / case["config"]
    config = json.loads(config_path.read_text())
    save(output / "case.json", case)
    save(output / "config.resolved.json", config)
    if not port_free(config["host"], config["port"]):
        raise RuntimeError("Configured port is occupied")
    await wait_for_idle_gpus(case["gpu_wait_timeout_seconds"])
    diagnostics = output / "runtime_events"
    env = os.environ.copy()
    if case["diagnostics"]:
        env["AGENTKV_DIAGNOSTICS_DIR"] = str(diagnostics)
        env["AGENTKV_DIAGNOSTICS_RANKS"] = "0"
    else:
        env.pop("AGENTKV_DIAGNOSTICS_DIR", None)
        env.pop("AGENTKV_DIAGNOSTICS_RANKS", None)
    if case.get("exposure_barrier", False):
        env["AGENTKV_EXPOSURE_BARRIER"] = "1"
    else:
        env.pop("AGENTKV_EXPOSURE_BARRIER", None)
    command = [
        "bash",
        str(ROOT / "scripts/run_server.sh"),
        "--config",
        str(config_path),
        "--policy",
        case["policy"],
    ]
    save(output / "command.json", {"command": command, "diagnostics": case["diagnostics"]})
    log_stream = (output / "server.log").open("x")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=log_stream,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    base_url = f"http://{config['host']}:{config['port']}"
    state = {
        "status": "starting",
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "server_pid": process.pid,
    }
    save(output / "state.json", state)
    try:
        async with aiohttp.ClientSession() as client:
            await wait_ready(client, base_url, process, ready_timeout)
            info = json.loads(await request_text(client, base_url, "/server_info"))
            save(output / "server_info.json", info)
            if info.get("version") != "0.5.13.post1":
                raise RuntimeError(f"Unexpected SGLang version: {info.get('version')}")
            if info.get("radix_eviction_policy") != case["policy"]:
                raise RuntimeError("Eviction policy mismatch")
            if info.get("max_total_num_tokens") != config["max_total_tokens"]:
                raise RuntimeError("Full capacity mismatch")
            if info.get("swa_full_tokens_ratio") != config["swa_full_tokens_ratio"]:
                raise RuntimeError("SWA capacity ratio mismatch")
            flush = await request_text(client, base_url, "/flush_cache?timeout=120", "POST")
            if "Cache flushed." not in flush:
                raise RuntimeError(f"Cache flush failed: {flush}")
            (output / "metrics.before.prom").write_text(await request_text(client, base_url, "/metrics"))
            state["status"] = "replaying"
            save(output / "state.json", state)
            client_output = output / "client"
            replay_command = [
                str(PYTHON),
                str(ROOT / "scripts/replay_exact_continuation.py"),
                "--base-url",
                base_url,
                "--output",
                str(client_output),
                "--run-label",
                case["name"],
            ]
            if frozen_trace is not None:
                replay_command.extend(["--frozen-trace", str(frozen_trace)])
            completed = await asyncio.to_thread(
                subprocess.run,
                replay_command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=config["measurement_timeout_seconds"],
            )
            (output / "client.stdout").write_text(completed.stdout)
            (output / "client.stderr").write_text(completed.stderr)
            if completed.returncode != 0:
                raise RuntimeError(f"Replay failed: {completed.stderr[-2000:]}")
            (output / "metrics.after.prom").write_text(await request_text(client, base_url, "/metrics"))
            state["status"] = "completed"
    except BaseException as error:
        state["status"] = "failed"
        state["error"] = repr(error)
        raise
    finally:
        cleanup = await asyncio.to_thread(stop_service, process)
        save(output / "cleanup.json", cleanup)
        log_stream.close()
        state["completed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save(output / "state.json", state)
    return {
        "name": case["name"],
        "strategy": case.get("strategy", case["policy"]),
        "policy": case["policy"],
        "exposure_barrier": case.get("exposure_barrier", False),
        "diagnostics": case["diagnostics"],
        "status": state["status"],
        "client_summary_sha256": sha256(output / "client/summary.json"),
    }


async def run_suite(args) -> Path:
    cases = [
        {"name": "01_control_lru_off", "config": "configs/diagnostic_control_server.json", "policy": "lru", "diagnostics": False, "gpu_wait_timeout_seconds": args.gpu_wait_timeout},
        {"name": "02_control_lru_on", "config": "configs/diagnostic_control_server.json", "policy": "lru", "diagnostics": True, "gpu_wait_timeout_seconds": args.gpu_wait_timeout},
        {"name": "03_pressure_lru", "config": "configs/diagnostic_pressure_server.json", "policy": "lru", "diagnostics": True, "gpu_wait_timeout_seconds": args.gpu_wait_timeout},
        {"name": "04_pressure_slru", "config": "configs/diagnostic_pressure_server.json", "policy": "slru", "diagnostics": True, "gpu_wait_timeout_seconds": args.gpu_wait_timeout},
    ]
    destination = ROOT / "results/pilot" / (
        "exact_diagnostics_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    destination.mkdir(parents=True)
    frozen_trace = None
    frozen_trace_sha256 = None
    if args.frozen_trace is not None:
        source = args.frozen_trace.resolve()
        rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        fields = ("request_seq", "session_id", "turn_index", "lifecycle_state", "branch_from_turn", "input_ids", "output_ids", "tool_ids")
        frozen_trace = destination / "frozen_trace.jsonl"
        with frozen_trace.open("x") as stream:
            for row in rows:
                stream.write(json.dumps({field: row.get(field) for field in fields}, ensure_ascii=False, separators=(",", ":")) + "\n")
        frozen_trace_sha256 = sha256(frozen_trace)
    manifest = {
        "schema": "agentkv_exact_diagnostics_suite_v1",
        "status": "running",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "cases": cases,
        "results": [],
        "diagnostics_patch_lock_sha256": sha256(ROOT / "configs/environment.diagnostics.lock.json"),
        "trace_mode": "captured_fixed" if frozen_trace is not None else "closed_loop",
        "frozen_trace_sha256": frozen_trace_sha256,
    }
    save(destination / "suite.json", manifest)
    try:
        for case in cases:
            result = await run_case(case, destination, args.ready_timeout, frozen_trace)
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
    parser.add_argument("--ready-timeout", type=int, default=1800)
    parser.add_argument("--gpu-wait-timeout", type=int, default=43200)
    parser.add_argument("--frozen-trace", type=Path)
    args = parser.parse_args()
    asyncio.run(run_suite(args))


if __name__ == "__main__":
    main()
