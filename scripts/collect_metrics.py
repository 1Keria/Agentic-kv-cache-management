"""Prometheus 指标采集工具

独立使用：python scripts/collect_metrics.py [action]
  action:
    snapshot  - 采集当前指标快照
    watch     - 持续监控（每 5 秒采集一次）
    reset     - 提示如何重置（需重启 server）
"""

import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exp_utils import get_prometheus_metrics, EXPERIMENT_DIR


def snapshot():
    """采集当前指标快照"""
    metrics = get_prometheus_metrics()
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(EXPERIMENT_DIR, f"metrics_snapshot_{ts}.json")
    os.makedirs(EXPERIMENT_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"timestamp": ts, "metrics": metrics}, f, indent=2)
    print(f"Snapshot saved: {path}")
    for k, v in sorted(metrics.items()):
        print(f"  {k}: {v}")


def watch(interval=5):
    """持续监控"""
    print(f"Watching Prometheus metrics (interval={interval}s, Ctrl+C to stop)")
    try:
        while True:
            metrics = get_prometheus_metrics()
            hit_rate = 0
            if metrics.get("prefix_cache_queries_total", 0) > 0:
                hit_rate = metrics.get("prefix_cache_hits_total", 0) / metrics["prefix_cache_queries_total"] * 100
            usage = metrics.get("kv_cache_usage_perc", 0)
            print(f"[{time.strftime('%H:%M:%S')}] "
                  f"kv_usage={usage:.1f}% prefix_hit_rate={hit_rate:.1f}% "
                  f"hits={metrics.get('prefix_cache_hits_total', 0):.0f} "
                  f"queries={metrics.get('prefix_cache_queries_total', 0):.0f}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python collect_metrics.py [snapshot|watch|reset]")
        return

    action = sys.argv[1]
    if action == "snapshot":
        snapshot()
    elif action == "watch":
        watch()
    elif action == "reset":
        print("Prometheus metrics are cumulative. To reset:")
        print("  1. Stop vLLM server (Ctrl+C)")
        print("  2. Restart: bash scripts/run_vllm_server.sh")
    else:
        print(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
