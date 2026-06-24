#!/usr/bin/env python3
"""自动化实验运行器 - 直接在进程内运行所有实验

按照 runbook 执行所有实验，自动管理 server 生命周期。
每个实验完成后自动重启 server 清除 KV cache。

用法:
  cd /share/dai-sys/zhoulongsheng/agentkv
  python scripts/auto_run_experiments.py [--start-from 1]
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp_utils import wait_for_server, save_config, EXPERIMENT_DIR

SERVER_LOG = os.path.join(EXPERIMENT_DIR, "server.log")
CONDA_PYTHON = "/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python"
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPTS_DIR)


def kill_server():
    """杀掉 vLLM server"""
    result = subprocess.run("lsof -ti :8000 2>/dev/null", shell=True, capture_output=True, text=True)
    for pid in result.stdout.strip().split():
        if pid:
            try:
                os.kill(int(pid), 9)
            except ProcessLookupError:
                pass
    time.sleep(3)


def start_server(kv_offload_gib=8, vllm_log_level="INFO", gpu_util=0.3):
    """启动 vLLM server"""
    kill_server()

    env = os.environ.copy()
    env["KV_OFFLOAD_GIB"] = str(kv_offload_gib)
    env["VLLM_LOG_LEVEL"] = vllm_log_level
    env["UVICORN_LOG_LEVEL"] = vllm_log_level.lower()
    # 选择空闲 GPU（避开已被占用的 GPU 0）
    env["CUDA_VISIBLE_DEVICES"] = "2"

    cmd = ["bash", os.path.join(SCRIPTS_DIR, "run_vllm_server.sh"), str(gpu_util), "8000"]

    print(f"  Starting server: offload={kv_offload_gib}GiB, log={vllm_log_level}")
    with open(SERVER_LOG, "w") as log_f:
        proc = subprocess.Popen(
            cmd, env=env, stdout=log_f, stderr=subprocess.STDOUT,
            cwd=PROJECT_DIR, start_new_session=True,
        )
    print(f"  Server PID: {proc.pid}")
    return proc


async def wait_server_ready(timeout=300):
    """等待 server 就绪"""
    print(f"  Waiting for server (timeout={timeout}s)...")
    result = await wait_for_server(timeout=timeout)
    if result:
        print(f"  ✅ Server ready!")
    else:
        print(f"  ❌ Server not ready after {timeout}s")
        if os.path.exists(SERVER_LOG):
            with open(SERVER_LOG) as f:
                lines = f.readlines()
            print("  Last 10 lines of server log:")
            for line in lines[-10:]:
                print(f"    {line.rstrip()}")
    return result


def run_subprocess(script_name, args=None, timeout=600):
    """运行实验脚本作为子进程"""
    cmd = [CONDA_PYTHON, os.path.join(SCRIPTS_DIR, script_name)]
    if args:
        cmd.extend(args)

    print(f"  Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_DIR, timeout=timeout)
        # 打印输出
        if result.stdout:
            for line in result.stdout.split('\n'):
                print(f"  | {line}")
        if result.stderr and result.returncode != 0:
            print(f"  STDERR: {result.stderr[:500]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"  ⚠️  Timeout after {timeout}s!")
        return False


# 实验定义
EXPERIMENTS = [
    # Phase 1: Offloading ON (8 GiB)
    {"name": "exp1", "script": "run_exp1.py", "args": ["--num-runs", "1"], "offload": 8, "log": "INFO"},
    {"name": "exp2", "script": "run_exp2.py", "args": ["--num-runs", "1"], "offload": 8, "log": "INFO"},
    {"name": "exp3_on", "script": "run_exp3.py", "args": ["--config", "on", "--num-runs", "1"], "offload": 8, "log": "INFO"},
    {"name": "exp4.1", "script": "run_exp4.py", "args": ["--subexp", "4.1", "--num-runs", "1"], "offload": 8, "log": "INFO"},
    {"name": "exp4.2", "script": "run_exp4.py", "args": ["--subexp", "4.2", "--num-runs", "1"], "offload": 8, "log": "INFO"},
    {"name": "exp4.3", "script": "run_exp4.py", "args": ["--subexp", "4.3", "--num-runs", "1"], "offload": 8, "log": "INFO"},
    {"name": "exp4.4", "script": "run_exp4.py", "args": ["--subexp", "4.4", "--num-runs", "1"], "offload": 8, "log": "INFO"},
    {"name": "exp4.5_on", "script": "run_exp4.py", "args": ["--subexp", "4.5", "--config", "on", "--num-runs", "1"], "offload": 8, "log": "DEBUG"},
    {"name": "exp4.6_on", "script": "run_exp4.py", "args": ["--subexp", "4.6", "--config", "on", "--num-runs", "1"], "offload": 8, "log": "DEBUG"},
    {"name": "exp5_lru", "script": "run_exp5.py", "args": ["--run", "lru", "--num-runs", "1"], "offload": 8, "log": "DEBUG"},
    {"name": "exp5_aware", "script": "run_exp5.py", "args": ["--run", "aware", "--num-runs", "1"], "offload": 8, "log": "DEBUG"},
    # Phase 2: Offloading OFF
    {"name": "exp3_off", "script": "run_exp3.py", "args": ["--config", "off", "--num-runs", "1"], "offload": 0, "log": "INFO"},
    {"name": "exp4.5_off", "script": "run_exp4.py", "args": ["--subexp", "4.5", "--config", "off", "--num-runs", "1"], "offload": 0, "log": "DEBUG"},
    {"name": "exp4.6_off", "script": "run_exp4.py", "args": ["--subexp", "4.6", "--config", "off", "--num-runs", "1"], "offload": 0, "log": "DEBUG"},
    # Phase 3: Preemption strategies
    {"name": "exp6_swap", "script": "run_exp6.py", "args": ["--config", "swap", "--num-runs", "1"], "offload": 8, "log": "DEBUG"},
    {"name": "exp6_recompute", "script": "run_exp6.py", "args": ["--config", "recompute", "--num-runs", "1"], "offload": 0, "log": "DEBUG"},
    {"name": "exp6_default", "script": "run_exp6.py", "args": ["--config", "default", "--num-runs", "1"], "offload": 0, "log": "DEBUG"},
]


async def run_all(start_from=1):
    """运行所有实验"""
    save_config()
    results = {}

    print(f"\n{'='*60}")
    print(f"  AgentKV vLLM KV Cache 实验自动化运行器")
    print(f"  总实验数: {len(EXPERIMENTS)}")
    print(f"  从第 {start_from} 个开始")
    print(f"{'='*60}\n")

    for i, exp in enumerate(EXPERIMENTS, 1):
        if i < start_from:
            print(f"  ⏭️  Skipping {i}: {exp['name']}")
            continue

        print(f"\n{'='*60}")
        print(f"  [{i}/{len(EXPERIMENTS)}] {exp['name']}")
        print(f"{'='*60}")

        # 启动 server
        start_server(kv_offload_gib=exp['offload'], vllm_log_level=exp['log'])
        ready = await wait_server_ready(timeout=300)

        if not ready:
            # 重试一次
            print("  Retrying server start...")
            start_server(kv_offload_gib=exp['offload'], vllm_log_level=exp['log'])
            ready = await wait_server_ready(timeout=300)
            if not ready:
                results[exp['name']] = "FAILED: server not ready"
                continue

        # 运行实验
        success = run_subprocess(exp['script'], exp['args'], timeout=600)
        results[exp['name']] = "OK" if success else "FAILED"

        # 保存 DEBUG 日志
        if exp['log'] == 'DEBUG' and os.path.exists(SERVER_LOG):
            log_copy = os.path.join(EXPERIMENT_DIR, f"server_log_{exp['name']}.log")
            subprocess.run(["cp", SERVER_LOG, log_copy], capture_output=True)

    # 清理
    kill_server()

    # 汇总
    print(f"\n{'='*60}")
    print(f"  实验结果汇总")
    print(f"{'='*60}")
    ok_count = 0
    for name, status in results.items():
        icon = "✅" if status == "OK" else "❌"
        print(f"  {icon} {name}: {status}")
        if status == "OK":
            ok_count += 1

    print(f"\n  成功: {ok_count}/{len(results)}")

    results_path = os.path.join(EXPERIMENT_DIR, "auto_run_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Results saved: {results_path}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-from", type=int, default=1)
    args = parser.parse_args()
    asyncio.run(run_all(start_from=args.start_from))
