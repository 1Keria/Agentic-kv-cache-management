#!/usr/bin/env python3
"""Launch only the isolated engine, keeping all non-policy settings fixed."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys

import sglang

ROOT = Path(__file__).resolve().parents[1]


def build_command(config: dict, policy: str) -> list[str]:
    command = [sys.executable, "-m", "sglang.launch_server"]
    names = {"model_path": "model-path", "host": "host", "port": "port",
             "tensor_parallel_size": "tp-size", "mem_fraction_static": "mem-fraction-static",
             "max_total_tokens": "max-total-tokens", "max_running_requests": "max-running-requests",
             "context_length": "context-length", "chunked_prefill_size": "chunked-prefill-size",
             "page_size": "page-size", "kv_cache_dtype": "kv-cache-dtype",
             "swa_full_tokens_ratio": "swa-full-tokens-ratio", "moe_runner_backend": "moe-runner-backend",
             "cuda_graph_max_bs": "cuda-graph-max-bs", "random_seed": "random-seed"}
    for name, flag in names.items():
        command.extend(["--" + flag, str(config[name])])
    command.extend(["--radix-eviction-policy", policy, "--enable-metrics", "--stream-interval", "1"])
    if config["enable_piecewise_cuda_graph"]:
        command.extend(["--enable-piecewise-cuda-graph", "--piecewise-cuda-graph-max-tokens",
                        str(config["piecewise_cuda_graph_max_tokens"])])
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/smoke_server.json")
    parser.add_argument("--policy", choices=["lru", "lfu", "slru"], default="lru")
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()
    if not Path(sglang.__file__).resolve().is_relative_to(ROOT / "runtime/venv"):
        raise RuntimeError("Refusing non-isolated engine import")
    if importlib.metadata.version("sglang") != "0.5.13.post1":
        raise RuntimeError("Unexpected engine version")
    config = json.loads(args.config.read_text())
    command = build_command(config, args.policy)
    print(json.dumps({"command": command, "sglang_origin": sglang.__file__,
                      "purpose": config["purpose"]}, ensure_ascii=False), flush=True)
    if not args.print_only:
        os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
