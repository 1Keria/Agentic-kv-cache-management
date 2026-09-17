#!/usr/bin/env bash
# Replay one ratio-matched daily-training workload with the LRU server.
#
# Usage:
#   bash scripts/shell/replay_ratio_training.sh agent_000
#   bash scripts/shell/replay_ratio_training.sh agent_050
#   bash scripts/shell/replay_ratio_training.sh all
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv

EXPERIMENT_ROOT="${RATIO_TRAIN_EXPERIMENT_ROOT:-experiments/sglang_kv_cache/ratio_daily_models}"
WORKLOAD_ROOT="${RATIO_TRAIN_WORKLOAD_ROOT:-workloads/ratio_train_v4flash}"

normalize_ratio() {
  local value="$1"
  case "$value" in
    agent_000|agent_010|agent_020|agent_030|agent_040|agent_050|\
    agent_060|agent_070|agent_080|agent_090|agent_100)
      printf '%s\n' "$value"
      ;;
    0|00|000) printf 'agent_000\n' ;;
    10|010) printf 'agent_010\n' ;;
    20|020) printf 'agent_020\n' ;;
    30|030) printf 'agent_030\n' ;;
    40|040) printf 'agent_040\n' ;;
    50|050) printf 'agent_050\n' ;;
    60|060) printf 'agent_060\n' ;;
    70|070) printf 'agent_070\n' ;;
    80|080) printf 'agent_080\n' ;;
    90|090) printf 'agent_090\n' ;;
    100) printf 'agent_100\n' ;;
    *)
      echo "比例必须是 agent_000..agent_100，或 0,10,...,100；收到：$value" >&2
      return 2
      ;;
  esac
}

replay_one() {
  local ratio
  ratio="$(normalize_ratio "$1")"
  local workload_dir="$WORKLOAD_ROOT/$ratio"
  local run_root="$EXPERIMENT_ROOT/$ratio/replay"

  if [[ ! -f "$workload_dir/workload.jsonl" ]]; then
    echo "训练 workload 不存在：$workload_dir/workload.jsonl" >&2
    return 1
  fi

  echo "[ratio-train] ratio=$ratio workload=$workload_dir output=$run_root"
  MIX_REPLAY_RUN_ROOT="$run_root" \
  MIX_REPLAY_RUN_ID="train_lru" \
    bash scripts/shell/replay_mix_workload.sh \
      --workload-dir "$workload_dir" \
      --arrival frozen
}

if [[ $# -ne 1 ]]; then
  echo "用法：bash scripts/shell/replay_ratio_training.sh <agent_000|...|agent_100|all>" >&2
  exit 2
fi

if [[ "$1" == "all" ]]; then
  for ratio in 000 010 020 030 040 050 060 070 080 090 100; do
    replay_one "agent_$ratio"
  done
else
  replay_one "$1"
fi
