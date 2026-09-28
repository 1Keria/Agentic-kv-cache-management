#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EXPERIMENT_ROOT="$REPO_ROOT/experiments/固定分区试验对比"
RUN_ID="${FULL_EXPERIMENT_RUN_ID:-$(date -u +%Y%m%d_%H%M%S)_cuda_graph_warm_balanced_4pairs}"
RUN_DIR="${FULL_EXPERIMENT_RUN_DIR:-$EXPERIMENT_ROOT/results/full_runs/$RUN_ID}"
LAUNCHER_LOG="$EXPERIMENT_ROOT/results/launcher_logs/${RUN_ID}.log"
PID_FILE="$EXPERIMENT_ROOT/results/launcher_logs/${RUN_ID}.pid"
SESSION_FILE="$EXPERIMENT_ROOT/results/launcher_logs/${RUN_ID}.tmux_session"
RESUME="${FULL_EXPERIMENT_RESUME:-0}"
BACKGROUND_BACKEND="${FULL_EXPERIMENT_BACKGROUND_BACKEND:-auto}"

mkdir -p "$(dirname "$LAUNCHER_LOG")"
[[ "$RESUME" == "0" || "$RESUME" == "1" ]] \
  || { echo "FULL_EXPERIMENT_RESUME 只能为 0 或 1" >&2; exit 1; }
[[ "$BACKGROUND_BACKEND" == "auto" || "$BACKGROUND_BACKEND" == "tmux" || "$BACKGROUND_BACKEND" == "nohup" ]] \
  || { echo "FULL_EXPERIMENT_BACKGROUND_BACKEND 只能为 auto、tmux 或 nohup" >&2; exit 1; }
if [[ "$RESUME" == "1" ]]; then
  [[ -d "$RUN_DIR" ]] || { echo "恢复目录不存在：$RUN_DIR" >&2; exit 1; }
else
  [[ ! -e "$RUN_DIR" ]] || { echo "结果目录已存在：$RUN_DIR" >&2; exit 1; }
fi

if [[ "$RESUME" == "1" ]]; then
  printf '\n[background] resume requested at %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$LAUNCHER_LOG"
  LOG_REDIRECT=">>"
else
  LOG_REDIRECT=">"
fi

launch_command=(env
  FULL_EXPERIMENT_RUN_ID="$RUN_ID" \
  FULL_EXPERIMENT_RUN_DIR="$RUN_DIR" \
  FULL_EXPERIMENT_RESUME="$RESUME" \
  FULL_EXPERIMENT_ORDERS="${FULL_EXPERIMENT_ORDERS:-unified-first partitioned-first partitioned-first unified-first}" \
  WARM_CACHE_EXPERIMENT=1 \
  PRECOMPILE_DEEPGEMM="${PRECOMPILE_DEEPGEMM:-0}" \
  AGENTKV_RUNTIME_CACHE_ROOT="${AGENTKV_RUNTIME_CACHE_ROOT:-/tmp/agentkv_full_experiment_shared_cache}" \
  REPLAY_TIMEOUT_SECONDS="${REPLAY_TIMEOUT_SECONDS:-5400}" \
  CUDA_GRAPH_MAX_BS_DECODE="${CUDA_GRAPH_MAX_BS_DECODE:-96}" \
  ENABLE_JIT_WARMUP=1 \
  JIT_WARMUP_HORIZON_SECONDS="${JIT_WARMUP_HORIZON_SECONDS:-60}" \
  JIT_WARMUP_OUTPUT_TOKENS="${JIT_WARMUP_OUTPUT_TOKENS:-4}" \
  JIT_WARMUP_TIMEOUT_SECONDS="${JIT_WARMUP_TIMEOUT_SECONDS:-1800}" \
  bash "$SCRIPT_DIR/run_full_experiment.sh")

if [[ "$BACKGROUND_BACKEND" == "auto" ]]; then
  if command -v tmux >/dev/null 2>&1; then
    BACKGROUND_BACKEND=tmux
  else
    BACKGROUND_BACKEND=nohup
  fi
fi

if [[ "$BACKGROUND_BACKEND" == "tmux" ]]; then
  session_name="agentkv_${RUN_ID//[^[:alnum:]_]/_}"
  if tmux has-session -t "$session_name" 2>/dev/null; then
    echo "tmux 会话已存在：$session_name" >&2
    exit 1
  fi
  printf -v command_quoted '%q ' "${launch_command[@]}"
  printf -v log_quoted '%q' "$LAUNCHER_LOG"
  if [[ "$LOG_REDIRECT" == ">>" ]]; then
    tmux new-session -d -s "$session_name" "exec $command_quoted >>$log_quoted 2>&1"
  else
    tmux new-session -d -s "$session_name" "exec $command_quoted >$log_quoted 2>&1"
  fi
  pid="$(tmux list-panes -t "$session_name" -F '#{pane_pid}' | head -n 1)"
  echo "$session_name" >"$SESSION_FILE"
else
  if [[ "$LOG_REDIRECT" == ">>" ]]; then
    setsid nohup "${launch_command[@]}" >>"$LAUNCHER_LOG" 2>&1 < /dev/null &
  else
    setsid nohup "${launch_command[@]}" >"$LAUNCHER_LOG" 2>&1 < /dev/null &
  fi
  pid=$!
  rm -f "$SESSION_FILE"
fi

echo "$pid" >"$PID_FILE"
echo "$RUN_ID" >"$EXPERIMENT_ROOT/results/latest_full_run_id.txt"
cat <<EOF
[background] pid=$pid
[background] run_id=$RUN_ID
[background] run_dir=$RUN_DIR
[background] log=$LAUNCHER_LOG
[background] backend=$BACKGROUND_BACKEND
EOF
