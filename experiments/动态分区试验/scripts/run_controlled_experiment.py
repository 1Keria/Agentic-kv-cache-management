#!/usr/bin/env python3
"""Run unified, fixed, and dynamic cache experiments with trajectory sampling."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = REPO_ROOT / "experiments/动态分区试验"
DEFAULT_MODEL = Path(
    "/mnt/public/dai-sys/.cache/hub/hub/"
    "models--deepseek-ai--DeepSeek-V4-Flash/"
    "snapshots/fd53f944496234770ba80e15004f9b6d269a71f5"
)
DEFAULT_VENV = REPO_ROOT / "experiments/evicition_policy/runtime/venv"
START_SCRIPTS = {
    "native": REPO_ROOT / "experiments/固定分区试验对比/scripts/start_unified_server.sh",
    "unified": REPO_ROOT / "experiments/固定分区试验对比/scripts/start_unified_server.sh",
    "fixed": REPO_ROOT / "experiments/固定分区试验对比/scripts/start_partitioned_server.sh",
    "dynamic": EXPERIMENT_ROOT / "scripts/start_dynamic_server.sh",
    "borrow": EXPERIMENT_ROOT / "scripts/start_borrow_server.sh",
    "borrow_dynamic": EXPERIMENT_ROOT / "scripts/start_borrow_dynamic_server.sh",
    "borrow_global": EXPERIMENT_ROOT / "scripts/start_borrow_global_server.sh",
    "borrow_reclass": EXPERIMENT_ROOT / "scripts/start_borrow_reclass_server.sh",
    "borrow_request_reclass": EXPERIMENT_ROOT / "scripts/start_borrow_request_reclass_server.sh",
    "borrow_lazy_reclass": EXPERIMENT_ROOT / "scripts/start_borrow_lazy_reclass_server.sh",
    "elastic": EXPERIMENT_ROOT / "scripts/start_elastic_server.sh",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read())


def save_metrics(base_url: str, path: Path) -> None:
    try:
        with urllib.request.urlopen(f"{base_url}/metrics", timeout=10) as response:
            path.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        path.with_suffix(".error.txt").write_text(f"{type(exc).__name__}: {exc}\n")


def port_is_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_server(base_url: str, process: subprocess.Popen[Any], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited during startup with code {process.returncode}")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=3) as response:
                if 200 <= response.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(1)
    raise TimeoutError(f"server did not become healthy within {timeout}s")


def stop_server(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    for sig, timeout in ((signal.SIGINT, 60), (signal.SIGTERM, 30), (signal.SIGKILL, 10)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            continue


def gpu_compute_processes(visible_devices: str | None = None) -> list[str]:
    """Return compute-process rows visible to nvidia-smi.

    The experiment owns all GPUs only while its server is running. A global
    "GPU list is empty" check would mistake another user's unrelated job for
    a leaked experiment process and could block teardown indefinitely.
    """
    selected = None
    if visible_devices:
        try:
            selected = {int(item.strip()) for item in visible_devices.split(",") if item.strip()}
        except ValueError:
            selected = None
    gpu_result = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    uuid_to_index = {}
    if gpu_result.returncode == 0:
        for line in gpu_result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",", 1)]
            if len(parts) == 2:
                try:
                    uuid_to_index[parts[1]] = int(parts[0])
                except ValueError:
                    pass
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    rows = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        gpu_uuid = line.split(",", 1)[0].strip()
        if selected is None or uuid_to_index.get(gpu_uuid) in selected:
            rows.append(line.strip())
    return rows


def wait_for_release(port: int, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # The port is the server-owned resource. Other jobs may legitimately
        # keep one or more GPUs busy after this experiment exits.
        if not port_is_open(port):
            return
        time.sleep(1)
    raise TimeoutError("GPU or serving port was not released")


def internal_state(info: dict[str, Any]) -> dict[str, Any]:
    states = info.get("internal_states") or []
    return states[0] if states else {}


def sample_trajectory(
    base_url: str,
    output_path: Path,
    stop_event: threading.Event,
    interval_s: float,
    start_monotonic: float,
) -> None:
    with output_path.open("a") as handle:
        while not stop_event.is_set():
            record: dict[str, Any] = {
                "timestamp_utc": utc_now(),
                "elapsed_s": round(time.monotonic() - start_monotonic, 3),
            }
            try:
                info = get_json(f"{base_url}/server_info")
                state = internal_state(info)
                record.update(
                    {
                        "controller": state.get("request_cache_region_controller"),
                        "regions": state.get("request_cache_regions"),
                    }
                )
            except Exception as exc:  # sampling must never abort the replay
                record["error"] = f"{type(exc).__name__}: {exc}"
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            stop_event.wait(interval_s)


def validate_summary(path: Path, expected_requests: int) -> None:
    summary = json.loads(path.read_text())
    integrity = summary.get("integrity") or {}
    if (
        integrity.get("n_issued") != expected_requests
        or integrity.get("n_ok") != expected_requests
        or integrity.get("n_err") != 0
    ):
        raise RuntimeError(f"replay integrity check failed: {integrity}")


def count_workload(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--workload-dir", type=Path, required=True)
    parser.add_argument("--modes", nargs="+", choices=tuple(START_SCRIPTS), required=True)
    parser.add_argument("--run-root", type=Path, default=EXPERIMENT_ROOT / "results/formal_20260929")
    parser.add_argument("--port", type=int, default=30000)
    parser.add_argument(
        "--replay-protocol",
        choices=("session", "phased", "open_loop"),
        default="session",
        help="open_loop uses a fixed request arrival schedule and ignores completion barriers.",
    )
    parser.add_argument("--replay-max-inflight", type=int, default=2)
    parser.add_argument("--open-loop-agent-start-s", type=float, default=20.0)
    parser.add_argument("--open-loop-return-start-s", type=float, default=100.0)
    parser.add_argument("--open-loop-session-stagger-s", type=float, default=2.0)
    parser.add_argument(
        "--allow-phase-requirement-failure",
        action="store_true",
        help="Record phase hit-rate requirements without aborting the replay.",
    )
    parser.add_argument("--unified-engine-root", type=Path, help="Optional pristine engine for the unified mode.")
    parser.add_argument(
        "--native-engine-root", type=Path,
        default=EXPERIMENT_ROOT / "runtime/native_wheel",
        help="Root containing a pristine official Engine/sglang/python package.",
    )
    parser.add_argument("--gap-scale", type=float, default=1.0)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument("--sample-interval-s", type=float, default=5.0)
    parser.add_argument("--chunked-prefill-size", type=int, default=None)
    parser.add_argument("--server-timeout-s", type=float, default=1800.0)
    parser.add_argument("--replay-timeout-s", type=float, default=5400.0)
    parser.add_argument("--agent-ratio", type=float, default=0.61)
    parser.add_argument(
        "--window-requests",
        type=int,
        default=0,
        help="Deprecated compatibility option; dynamic mode uses eviction feedback.",
    )
    parser.add_argument("--alpha", type=float, default=0.2)
    parser.add_argument(
        "--feedback-mode",
        choices=("eviction_share", "normalized_pressure"),
        default="normalized_pressure",
        help="Dynamic ratio feedback signal.",
    )
    parser.add_argument(
        "--max-ratio-step",
        type=float,
        default=0.05,
        help="Maximum normalized-pressure ratio movement per update.",
    )
    parser.add_argument(
        "--pressure-hysteresis",
        type=float,
        default=0.02,
        help="Minimum normalized pressure gap needed for an update.",
    )
    parser.add_argument(
        "--cooldown-evicted-tokens",
        type=int,
        default=4096,
        help="Evicted-token cooldown after a ratio update.",
    )
    parser.add_argument("--min-ratio", type=float, default=0.2)
    parser.add_argument("--max-ratio", type=float, default=0.8)
    parser.add_argument(
        "--elastic-reclaim-order",
        choices=("request_first", "pressure_first"),
        default="request_first",
        help="Borrowed-page order used by elastic shared-pool reclaim.",
    )
    parser.add_argument(
        "--elastic-preferred-reclaim",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use the elastic soft-line preferred reclaim tier.",
    )
    parser.add_argument(
        "--elastic-soft-step",
        type=float,
        default=0.1,
        help="Maximum elastic soft-split movement per pressure boundary.",
    )
    parser.add_argument(
        "--elastic-activity-window",
        type=int,
        default=32,
        help=(
            "Recent classified-request window required for tail-first reclaim; "
            "zero disables this gate (default: 32)."
        ),
    )
    parser.add_argument(
        "--elastic-ghost-capacity-tokens",
        type=int,
        default=int(os.environ.get("REQUEST_CACHE_ELASTIC_GHOST_CAPACITY_TOKENS", "0")),
        help="Bounded metadata capacity for eviction-then-revisit feedback; zero disables it.",
    )
    parser.add_argument(
        "--elastic-ghost-pressure-decay",
        type=float,
        default=float(os.environ.get("REQUEST_CACHE_ELASTIC_GHOST_PRESSURE_DECAY", "0.95")),
    )
    parser.add_argument(
        "--elastic-ghost-bias",
        type=float,
        default=float(os.environ.get("REQUEST_CACHE_ELASTIC_GHOST_BIAS", "0.5")),
    )
    parser.add_argument(
        "--elastic-ghost-reclaim",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("REQUEST_CACHE_ELASTIC_GHOST_RECLAIM", "1") == "1",
        help="Use ghost revisit pressure to choose borrowed-page reclaim order.",
    )
    parser.add_argument(
        "--elastic-ghost-protect",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("REQUEST_CACHE_ELASTIC_GHOST_PROTECT", "0") == "1",
        help=(
            "Protect borrowed radix nodes after the ghost observes that their "
            "eviction caused real recomputation."
        ),
    )
    parser.add_argument(
        "--elastic-ghost-protect-min-tokens",
        type=int,
        default=int(
            os.environ.get("REQUEST_CACHE_ELASTIC_GHOST_PROTECT_MIN_TOKENS", "0")
        ),
        help="Minimum decayed ghost score to protect a borrowed node; zero means one page.",
    )
    parser.add_argument(
        "--elastic-feedback",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Adapt elastic cold-start return reserves from actual borrowed-page "
            "eviction pressure."
        ),
    )
    parser.add_argument(
        "--feedback-min-evicted-tokens",
        type=int,
        default=0,
        help="Minimum accumulated evicted tokens before dynamic ratio feedback.",
    )
    parser.add_argument(
        "--borrow-high-watermark-tokens",
        type=int,
        default=0,
        help="Proactive reclaim threshold; zero reclaims only on global capacity pressure.",
    )
    parser.add_argument(
        "--borrow-low-watermark-tokens",
        type=int,
        default=0,
        help="Target pressure after proactive reclaim; used only when high watermark is set.",
    )
    parser.add_argument(
        "--borrowed-segment-tokens",
        type=int,
        default=0,
        help=(
            "Experimental page-aligned bound for newly inserted borrowed "
            "radix suffix segments; zero keeps whole-suffix nodes."
        ),
    )
    parser.add_argument("--disable-cuda-graph", choices=("0", "1"), default="1")
    parser.add_argument(
        "--mem-fraction-static",
        type=float,
        default=0.45,
        help="Fraction of GPU memory reserved for the KV cache; keep fixed across modes.",
    )
    parser.add_argument(
        "--swa-full-tokens-ratio",
        type=float,
        default=None,
        help="Optional SWA/full token capacity ratio, kept identical across modes.",
    )
    args = parser.parse_args()
    if args.borrow_low_watermark_tokens < 0 or (
        args.borrow_high_watermark_tokens < args.borrow_low_watermark_tokens
    ):
        raise SystemExit("borrow watermarks must satisfy 0 <= low <= high")
    if args.feedback_min_evicted_tokens < 0:
        raise SystemExit("feedback-min-evicted-tokens must be non-negative")
    if args.borrowed_segment_tokens < 0:
        raise SystemExit("borrowed-segment-tokens must be non-negative")
    if not 0.0 < args.mem_fraction_static < 1.0:
        raise SystemExit("mem-fraction-static must be in (0, 1)")
    if args.swa_full_tokens_ratio is not None and not 0.0 < args.swa_full_tokens_ratio <= 1.0:
        raise SystemExit("swa-full-tokens-ratio must be in (0, 1]")
    if not 0.0 < args.elastic_soft_step <= 1.0:
        raise SystemExit("elastic-soft-step must be in (0, 1]")
    if args.elastic_activity_window < 0:
        raise SystemExit("elastic-activity-window must be non-negative")
    if args.elastic_ghost_capacity_tokens < 0:
        raise SystemExit("elastic-ghost-capacity-tokens must be non-negative")
    if not 0.0 < args.elastic_ghost_pressure_decay <= 1.0:
        raise SystemExit("elastic-ghost-pressure-decay must be in (0, 1]")
    if args.elastic_ghost_bias < 0.0:
        raise SystemExit("elastic-ghost-bias must be non-negative")
    if args.elastic_ghost_protect_min_tokens < 0:
        raise SystemExit("elastic-ghost-protect-min-tokens must be non-negative")

    workload_dir = args.workload_dir.resolve()
    workload_path = workload_dir / "workload.jsonl"
    if not workload_path.is_file():
        raise SystemExit(f"missing workload: {workload_path}")
    if args.replay_protocol in {"phased", "open_loop"}:
        replay_plan_path = workload_dir / "replay_plan.json"
        if not replay_plan_path.is_file():
            raise SystemExit(
                "phased replay requires "
                f"{replay_plan_path}; use --replay-protocol session "
                "for workloads that only provide phase_assignment.json"
            )
    if port_is_open(args.port):
        raise SystemExit(f"port {args.port} is already in use")
    expected_requests = count_workload(workload_path)
    scenario_dir = args.run_root.resolve() / args.scenario
    scenario_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "created_at_utc": utc_now(),
        "scenario": args.scenario,
        "workload_dir": str(workload_dir),
        "expected_requests": expected_requests,
        "modes": args.modes,
        "gap_scale": args.gap_scale,
        "max_output_tokens": args.max_output_tokens,
        "agent_ratio": args.agent_ratio,
        "window_requests_legacy": args.window_requests,
        "alpha": args.alpha,
        "feedback_mode": args.feedback_mode,
        "max_ratio_step": args.max_ratio_step,
        "pressure_hysteresis": args.pressure_hysteresis,
        "cooldown_evicted_tokens": args.cooldown_evicted_tokens,
        "min_ratio": args.min_ratio,
        "max_ratio": args.max_ratio,
        "elastic_reclaim_order": args.elastic_reclaim_order,
        "elastic_preferred_reclaim": args.elastic_preferred_reclaim,
        "elastic_soft_step": args.elastic_soft_step,
        "elastic_activity_window": args.elastic_activity_window,
        "elastic_ghost_capacity_tokens": args.elastic_ghost_capacity_tokens,
        "elastic_ghost_pressure_decay": args.elastic_ghost_pressure_decay,
        "elastic_ghost_bias": args.elastic_ghost_bias,
        "elastic_ghost_reclaim": args.elastic_ghost_reclaim,
        "elastic_ghost_protect": args.elastic_ghost_protect,
        "elastic_ghost_protect_min_tokens": args.elastic_ghost_protect_min_tokens,
        "elastic_feedback": args.elastic_feedback,
        "elastic_activity_requires_hit": os.environ.get(
            "REQUEST_CACHE_ELASTIC_ACTIVITY_REQUIRES_HIT", "0"
        ),
        "feedback_min_evicted_tokens": args.feedback_min_evicted_tokens,
        "borrow_high_watermark_tokens": args.borrow_high_watermark_tokens,
        "borrow_low_watermark_tokens": args.borrow_low_watermark_tokens,
        "borrowed_segment_tokens": args.borrowed_segment_tokens,
        "disable_cuda_graph": args.disable_cuda_graph,
        "mem_fraction_static": args.mem_fraction_static,
        "swa_full_tokens_ratio": args.swa_full_tokens_ratio,
        "chunked_prefill_size": args.chunked_prefill_size,
        "random_seed": 42,
        "cuda_visible_devices": os.environ.get(
            "PARTITION_EXPERIMENT_CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7"
        ),
        "tp_size": os.environ.get("PARTITION_EXPERIMENT_TP_SIZE", "8"),
        "replay_protocol": args.replay_protocol,
        "replay_max_inflight": args.replay_max_inflight if args.replay_protocol == "phased" else None,
        "open_loop_agent_start_s": args.open_loop_agent_start_s if args.replay_protocol == "open_loop" else None,
        "open_loop_return_start_s": args.open_loop_return_start_s if args.replay_protocol == "open_loop" else None,
        "open_loop_session_stagger_s": args.open_loop_session_stagger_s if args.replay_protocol == "open_loop" else None,
        "allow_phase_requirement_failure": args.allow_phase_requirement_failure,
        "unified_engine_root": str(args.unified_engine_root.resolve()) if args.unified_engine_root else None,
        "native_engine_root": str(args.native_engine_root.resolve()) if "native" in args.modes else None,
    }
    (scenario_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    )

    python = Path(os.environ.get("PARTITION_EXPERIMENT_PYTHON", DEFAULT_VENV / "bin/python"))
    sglang = Path(os.environ.get("SGLANG_BIN", DEFAULT_VENV / "bin/sglang"))
    model = Path(os.environ.get("MODEL_PATH", DEFAULT_MODEL))
    classifier = Path(
        os.environ.get(
            "REQUEST_CLASSIFIER_CHECKPOINT",
            REPO_ROOT / "models/request_classifier/checkpoints/final_system_free/budget_4/request_classifier.pt",
        )
    )
    for path in (python, sglang, model, classifier):
        if not path.exists():
            raise SystemExit(f"required path does not exist: {path}")
    if "native" in args.modes:
        native_package = args.native_engine_root.resolve() / "Engine/sglang/python/sglang"
        if not (native_package / "__init__.py").is_file():
            raise SystemExit(f"missing pristine native engine package: {native_package}")
    if args.unified_engine_root and not (args.unified_engine_root / "Engine/sglang/python/sglang/__init__.py").is_file():
        raise SystemExit("unified engine package is missing")

    for mode in args.modes:
        mode_dir = scenario_dir / mode
        if mode_dir.exists():
            raise SystemExit(f"mode output already exists: {mode_dir}")
        occupied = gpu_compute_processes(
            os.environ.get(
                "PARTITION_EXPERIMENT_CUDA_VISIBLE_DEVICES",
                "0,1,2,3,4,5,6,7",
            )
        )
        if occupied:
            raise SystemExit(
                "实验需要独占 CUDA_VISIBLE_DEVICES 中的 GPU；启动前发现已有计算进程：\n"
                + "\n".join(occupied)
            )
        mode_dir.mkdir(parents=True)
        log_handle = (mode_dir / "server.log").open("w")
        env = os.environ.copy()
        env.update(
            {
                "MODEL_PATH": str(model),
                "SGLANG_BIN": str(sglang),
                "AGENTKV_V4FLASH_VENV": str(DEFAULT_VENV),
                "PARTITION_EXPERIMENT_PYTHON": str(python),
                "PORT": str(args.port),
                # Keep the historical eight-GPU default, but allow a caller to
                # reserve a subset when another job owns one device. The
                # selected set is part of the run configuration and must be
                # kept identical for every mode in a comparison.
                "CUDA_VISIBLE_DEVICES": os.environ.get(
                    "PARTITION_EXPERIMENT_CUDA_VISIBLE_DEVICES",
                    "0,1,2,3,4,5,6,7",
                ),
                "MEM_FRACTION_STATIC": str(args.mem_fraction_static),
                "DISABLE_CUDA_GRAPH": args.disable_cuda_graph,
                "DISABLE_PREFILL_CUDA_GRAPH": "1",
                "CUDA_GRAPH_MAX_BS_DECODE": "96",
                "SERVER_RANDOM_SEED": "42",
                "AGENTKV_RUNTIME_CACHE_ROOT": "/tmp/agentkv_dynamic_smoke",
                "REQUEST_CLASSIFIER_CHECKPOINT": str(classifier),
                "REQUEST_CLASSIFIER_THRESHOLD": "0.5",
                "AGENT_CACHE_CAPACITY_RATIO": str(args.agent_ratio),
                "REQUEST_AGENT_CACHE_RATIO": str(args.agent_ratio),
                "REQUEST_CACHE_RATIO_WINDOW_REQUESTS": str(args.window_requests),
                "REQUEST_CACHE_RATIO_ALPHA": str(args.alpha),
                "REQUEST_CACHE_RATIO_FEEDBACK_MODE": str(args.feedback_mode),
                "REQUEST_CACHE_RATIO_MAX_STEP": str(args.max_ratio_step),
                "REQUEST_CACHE_RATIO_PRESSURE_HYSTERESIS": str(
                    args.pressure_hysteresis
                ),
                "REQUEST_CACHE_RATIO_COOLDOWN_EVICTED_TOKENS": str(
                    args.cooldown_evicted_tokens
                ),
                "REQUEST_CACHE_AGENT_MIN_RATIO": str(args.min_ratio),
                "REQUEST_CACHE_AGENT_MAX_RATIO": str(args.max_ratio),
                "REQUEST_CACHE_ELASTIC_RECLAIM_ORDER": args.elastic_reclaim_order,
                "REQUEST_CACHE_ELASTIC_PREFERRED_RECLAIM": "1"
                if args.elastic_preferred_reclaim
                else "0",
                "REQUEST_CACHE_ELASTIC_SOFT_STEP": str(args.elastic_soft_step),
                "REQUEST_CACHE_ELASTIC_ACTIVITY_WINDOW": str(
                    args.elastic_activity_window
                ),
                "REQUEST_CACHE_ELASTIC_GHOST_CAPACITY_TOKENS": str(
                    args.elastic_ghost_capacity_tokens
                ),
                "REQUEST_CACHE_ELASTIC_GHOST_PRESSURE_DECAY": str(
                    args.elastic_ghost_pressure_decay
                ),
                "REQUEST_CACHE_ELASTIC_GHOST_BIAS": str(args.elastic_ghost_bias),
                "REQUEST_CACHE_ELASTIC_GHOST_RECLAIM": "1"
                if args.elastic_ghost_reclaim
                else "0",
                "REQUEST_CACHE_ELASTIC_GHOST_PROTECT": "1"
                if args.elastic_ghost_protect
                else "0",
                "REQUEST_CACHE_ELASTIC_GHOST_PROTECT_MIN_TOKENS": str(
                    args.elastic_ghost_protect_min_tokens
                ),
                "REQUEST_CACHE_ELASTIC_FEEDBACK": "1"
                if args.elastic_feedback
                else "0",
                "REQUEST_CACHE_FEEDBACK_MIN_EVICTED_TOKENS": str(
                    args.feedback_min_evicted_tokens
                ),
                "REQUEST_CACHE_BORROW_HIGH_WATERMARK_TOKENS": str(
                    args.borrow_high_watermark_tokens
                ),
                "REQUEST_CACHE_BORROW_LOW_WATERMARK_TOKENS": str(
                    args.borrow_low_watermark_tokens
                ),
                "REQUEST_CACHE_BORROWED_SEGMENT_TOKENS": str(
                    args.borrowed_segment_tokens
                ),
            }
        )
        if os.environ.get("PARTITION_EXPERIMENT_TP_SIZE"):
            env["TP_SIZE"] = os.environ["PARTITION_EXPERIMENT_TP_SIZE"]
        if args.swa_full_tokens_ratio is not None:
            env["SWA_FULL_TOKENS_RATIO"] = str(args.swa_full_tokens_ratio)
        if mode == "borrow":
            env["REQUEST_CACHE_REGION_POLICY"] = "borrow"
        elif mode == "borrow_dynamic":
            env["REQUEST_CACHE_REGION_POLICY"] = "borrow_dynamic"
        elif mode == "borrow_lazy_reclass":
            env["REQUEST_CACHE_REGION_POLICY"] = "borrow"
            env["REQUEST_CACHE_BORROW_LAZY_RECLASSIFY"] = "1"
        elif mode == "elastic":
            env["REQUEST_CACHE_REGION_POLICY"] = "elastic"
        elif mode == "fixed":
            env["REQUEST_CACHE_REGION_POLICY"] = "fixed"
        elif mode == "native":
            env["SGLANG_REPO_ROOT"] = str(args.native_engine_root.resolve())
        elif mode == "unified" and args.unified_engine_root:
            env["SGLANG_REPO_ROOT"] = str(args.unified_engine_root.resolve())
        server_cmd = ["bash", str(START_SCRIPTS[mode])]
        if args.chunked_prefill_size is not None:
            server_cmd.extend(["--chunked-prefill-size", str(args.chunked_prefill_size)])
        process = subprocess.Popen(
            server_cmd,
            cwd=REPO_ROOT,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            base_url = f"http://127.0.0.1:{args.port}"
            print(f"[{utc_now()}] starting mode={mode} pid={process.pid}", flush=True)
            wait_for_server(base_url, process, args.server_timeout_s)
            before = get_json(f"{base_url}/server_info")
            (mode_dir / "server_info_before.json").write_text(
                json.dumps(before, ensure_ascii=False, indent=2) + "\n"
            )
            save_metrics(base_url, mode_dir / "metrics_before.prom")

            replay_dir = mode_dir / "run_mix_replay"
            replay_cmd = [
                str(python),
                str(
                    EXPERIMENT_ROOT / "scripts/replay_partition_phases.py"
                    if args.replay_protocol == "phased"
                    else (
                        EXPERIMENT_ROOT / "scripts/replay_open_loop.py"
                        if args.replay_protocol == "open_loop"
                        else REPO_ROOT / "scripts/python/replay_mix_workload.py"
                    )
                ),
                "--base-url",
                base_url,
                "--workload-dir",
                str(workload_dir),
                "--output-dir",
                str(replay_dir),
                "--arrival",
                "frozen",
                "--fixed-output-tokens",
                "--gap-scale",
                str(args.gap_scale),
            ]
            if args.replay_protocol == "phased":
                replay_cmd.extend(["--max-inflight", str(args.replay_max_inflight)])
                # The unified/native baseline is expected to reveal whether the
                # ordinary prefix survives pressure; its miss is evidence, not
                # a replay integrity failure. Partitioned modes keep strict
                # phase requirements so a broken preservation control aborts.
                if mode in {"unified", "native"}:
                    replay_cmd.append("--allow-phase-requirement-failure")
                elif args.allow_phase_requirement_failure:
                    replay_cmd.append("--allow-phase-requirement-failure")
            elif args.replay_protocol == "open_loop":
                replay_cmd.extend(
                    [
                        "--agent-phase-start-s",
                        str(args.open_loop_agent_start_s),
                        "--return-phase-start-s",
                        str(args.open_loop_return_start_s),
                        "--session-stagger-s",
                        str(args.open_loop_session_stagger_s),
                    ]
                )
            if args.max_output_tokens is not None:
                replay_cmd.extend(["--max-output-tokens-override", str(args.max_output_tokens)])

            replay_start = time.monotonic()
            sampler_stop = threading.Event()
            sampler = threading.Thread(
                target=sample_trajectory,
                args=(
                    base_url,
                    mode_dir / "controller_trajectory.jsonl",
                    sampler_stop,
                    args.sample_interval_s,
                    replay_start,
                ),
                daemon=True,
            )
            sampler.start()
            with (mode_dir / "replay.log").open("w") as replay_log:
                replay = subprocess.run(
                    replay_cmd,
                    cwd=REPO_ROOT,
                    env=env,
                    stdout=replay_log,
                    stderr=subprocess.STDOUT,
                    timeout=args.replay_timeout_s,
                    check=False,
                )
            sampler_stop.set()
            sampler.join(timeout=args.sample_interval_s + 2)
            if replay.returncode != 0:
                raise RuntimeError(f"replay failed with code {replay.returncode}")
            validate_summary(replay_dir / "summary.json", expected_requests)

            after = get_json(f"{base_url}/server_info")
            (mode_dir / "server_info_after.json").write_text(
                json.dumps(after, ensure_ascii=False, indent=2) + "\n"
            )
            save_metrics(base_url, mode_dir / "metrics_after.prom")
            print(
                f"[{utc_now()}] completed mode={mode} elapsed={time.monotonic() - replay_start:.1f}s",
                flush=True,
            )
        except Exception:
            if process.poll() is not None:
                print((mode_dir / "server.log").read_text(errors="replace")[-20000:], file=sys.stderr)
            raise
        finally:
            stop_server(process)
            log_handle.close()
            wait_for_release(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
