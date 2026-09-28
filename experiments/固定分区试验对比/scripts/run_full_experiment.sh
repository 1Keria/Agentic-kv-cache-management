#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EXPERIMENT_ROOT="$REPO_ROOT/experiments/固定分区试验对比"
MODEL_PATH="${MODEL_PATH:-/inspire/hdd/global_public/public_models/deepseek-ai/deepSeek-V4-Flash}"
VENV_ROOT="${AGENTKV_V4FLASH_VENV:-/inspire/hdd/project/inference-chip/czxs25240022/.venvs/agentkv-v4flash}"
PYTHON="${PARTITION_EXPERIMENT_PYTHON:-$VENV_ROOT/bin/python}"
FULL_RUN_ID="${FULL_EXPERIMENT_RUN_ID:-$(date -u +%Y%m%d_%H%M%S)_cuda_graph_balanced}"
FULL_RUN_DIR="${FULL_EXPERIMENT_RUN_DIR:-$EXPERIMENT_ROOT/results/full_runs/$FULL_RUN_ID}"
RUNTIME_CACHE_ROOT="${AGENTKV_RUNTIME_CACHE_ROOT:-/tmp/agentkv_full_experiment_$FULL_RUN_ID}"
read -r -a PAIR_ORDERS <<<"${FULL_EXPERIMENT_ORDERS:-unified-first partitioned-first partitioned-first unified-first}"
RESUME="${FULL_EXPERIMENT_RESUME:-0}"
STATUS=failed

read_config_value() {
  local key=$1
  sed -n "s/^${key}=//p" "$FULL_RUN_DIR/config.env" | tail -n 1
}

require_config_value() {
  local key=$1
  local expected=$2
  local actual
  actual="$(read_config_value "$key")"
  [[ "$actual" == "$expected" ]] || {
    echo "恢复配置不一致：$key 期望 '$expected'，已有 '$actual'" >&2
    exit 1
  }
}

write_status() {
  cat >"$FULL_RUN_DIR/run_status.env" <<EOF
FULL_RUN_ID=$FULL_RUN_ID
STATUS=$1
UPDATED_AT_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
}

on_exit() {
  local code=$?
  if [[ -d "$FULL_RUN_DIR" ]]; then
    write_status "$STATUS"
  fi
  exit "$code"
}
trap on_exit EXIT INT TERM

[[ "$RESUME" == "0" || "$RESUME" == "1" ]] \
  || { echo "FULL_EXPERIMENT_RESUME 只能为 0 或 1" >&2; exit 1; }
(( ${#PAIR_ORDERS[@]} >= 2 )) || { echo "完整实验至少需要两组配对顺序。" >&2; exit 1; }
for order in "${PAIR_ORDERS[@]}"; do
  [[ "$order" == "unified-first" || "$order" == "partitioned-first" ]] \
    || { echo "无效实验顺序：$order" >&2; exit 1; }
done

if [[ "$RESUME" == "1" ]]; then
  [[ -d "$FULL_RUN_DIR" && -f "$FULL_RUN_DIR/config.env" ]] \
    || { echo "恢复目录或配置不存在：$FULL_RUN_DIR" >&2; exit 1; }
  require_config_value FULL_RUN_ID "$FULL_RUN_ID"
  require_config_value MODEL_PATH "$MODEL_PATH"
  require_config_value PAIR_COUNT "${#PAIR_ORDERS[@]}"
  require_config_value PAIR_ORDERS "${PAIR_ORDERS[*]}"
  require_config_value MEM_FRACTION_STATIC "${MEM_FRACTION_STATIC:-0.45}"
  require_config_value DISABLE_CUDA_GRAPH 0
  require_config_value CUDA_GRAPH_MAX_BS_DECODE "${CUDA_GRAPH_MAX_BS_DECODE:-96}"
  require_config_value DISABLE_PREFILL_CUDA_GRAPH 1
  require_config_value SERVER_RANDOM_SEED "${SERVER_RANDOM_SEED:-42}"
  require_config_value AGENTKV_RUNTIME_CACHE_ROOT "$RUNTIME_CACHE_ROOT"
  echo "[full] resuming existing run: $FULL_RUN_DIR"
else
  [[ ! -e "$FULL_RUN_DIR" ]] || { echo "结果目录已存在：$FULL_RUN_DIR" >&2; exit 1; }
  mkdir -p "$FULL_RUN_DIR/pairs" "$FULL_RUN_DIR/logs" "$RUNTIME_CACHE_ROOT"
  cat >"$FULL_RUN_DIR/config.env" <<EOF
FULL_RUN_ID=$FULL_RUN_ID
MODEL_PATH=$MODEL_PATH
PAIR_COUNT=${#PAIR_ORDERS[@]}
PAIR_ORDERS=${PAIR_ORDERS[*]}
WARM_CACHE_EXPERIMENT=${WARM_CACHE_EXPERIMENT:-0}
ENABLE_JIT_WARMUP=${ENABLE_JIT_WARMUP:-1}
JIT_WARMUP_HORIZON_SECONDS=${JIT_WARMUP_HORIZON_SECONDS:-60}
JIT_WARMUP_OUTPUT_TOKENS=${JIT_WARMUP_OUTPUT_TOKENS:-4}
JIT_WARMUP_TIMEOUT_SECONDS=${JIT_WARMUP_TIMEOUT_SECONDS:-1800}
MEM_FRACTION_STATIC=${MEM_FRACTION_STATIC:-0.45}
DISABLE_CUDA_GRAPH=0
CUDA_GRAPH_MAX_BS_DECODE=${CUDA_GRAPH_MAX_BS_DECODE:-96}
DISABLE_PREFILL_CUDA_GRAPH=1
SERVER_RANDOM_SEED=${SERVER_RANDOM_SEED:-42}
REPLAY_TIMEOUT_SECONDS=${REPLAY_TIMEOUT_SECONDS:-5400}
AGENTKV_RUNTIME_CACHE_ROOT=$RUNTIME_CACHE_ROOT
EOF
fi
mkdir -p "$FULL_RUN_DIR/pairs" "$FULL_RUN_DIR/logs" "$FULL_RUN_DIR/aborted_attempts" "$RUNTIME_CACHE_ROOT"
write_status running

env \
  MODEL_PATH="$MODEL_PATH" \
  DISABLE_CUDA_GRAPH=0 \
  CUDA_GRAPH_MAX_BS_DECODE="${CUDA_GRAPH_MAX_BS_DECODE:-96}" \
  DISABLE_PREFILL_CUDA_GRAPH=1 \
  AGENTKV_RUNTIME_CACHE_ROOT="$RUNTIME_CACHE_ROOT" \
  bash "$SCRIPT_DIR/run_experiment.sh" --preflight-only \
  |& tee "$FULL_RUN_DIR/logs/preflight.log"

if [[ "${PRECOMPILE_DEEPGEMM:-1}" == "1" ]]; then
  echo "[full] precompiling DeepGEMM kernels into $RUNTIME_CACHE_ROOT"
  env \
    PYTHONPATH="$REPO_ROOT/Engine/sglang/python${PYTHONPATH:+:$PYTHONPATH}" \
    HOME="$RUNTIME_CACHE_ROOT/home" \
    XDG_CACHE_HOME="$RUNTIME_CACHE_ROOT/xdg_cache" \
    TVM_FFI_CACHE_DIR="$RUNTIME_CACHE_ROOT/tvm_ffi_cache" \
    DG_JIT_CACHE_DIR="$RUNTIME_CACHE_ROOT/home/.cache/deep_gemm" \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    "$PYTHON" -m sglang.compile_deep_gemm \
      --model-path "$MODEL_PATH" \
      --tp 8 \
      --moe-runner-backend marlin \
      --trust-remote-code \
      --mem-fraction-static "${MEM_FRACTION_STATIC:-0.45}" \
      --port "${PORT:-30000}" \
      --timeout "${DEEPGEMM_PRECOMPILE_TIMEOUT_SECONDS:-3600}" \
    |& tee "$FULL_RUN_DIR/logs/deepgemm_precompile.log"
fi

for index in "${!PAIR_ORDERS[@]}"; do
  pair_number=$((index + 1))
  order="${PAIR_ORDERS[$index]}"
  if [[ "$order" == "unified-first" ]]; then order_tag=ab; else order_tag=ba; fi
  pair_name="$(printf '%02d_%s' "$pair_number" "$order_tag")"
  pair_dir="$FULL_RUN_DIR/pairs/$pair_name"
  pair_log="$FULL_RUN_DIR/logs/$pair_name.log"
  pair_resume=0
  if [[ "$RESUME" == "1" && -d "$pair_dir" ]]; then
    pair_status="$(sed -n 's/^STATUS=//p' "$pair_dir/run_status.env" 2>/dev/null | tail -n 1)"
    if [[ "$pair_status" == "completed" && -f "$pair_dir/comparison.json" ]]; then
      echo "[full] skipping completed pair=$pair_name order=$order"
      continue
    fi
    if [[ -f "$pair_dir/config.env" ]]; then
      pair_resume=1
      echo "[full] resuming incomplete pair=$pair_name order=$order"
    else
      archive_name="${pair_name}_$(date -u +%Y%m%d_%H%M%S)_interrupted"
      archive_dir="$FULL_RUN_DIR/aborted_attempts/$archive_name"
      mkdir -p "$archive_dir"
      mv "$pair_dir" "$archive_dir/pair"
      if [[ -f "$pair_log" ]]; then
        mv "$pair_log" "$archive_dir/pair.log"
      fi
      echo "[full] archived unresumable pair=$pair_name to $archive_dir"
    fi
  fi
  echo "[full] starting pair=$pair_name order=$order"
  pair_command=(env
    MODEL_PATH="$MODEL_PATH"
    PARTITION_EXPERIMENT_RUN_ID="${FULL_RUN_ID}_$pair_name"
    PARTITION_EXPERIMENT_RUN_DIR="$pair_dir"
    PARTITION_EXPERIMENT_RESUME="$pair_resume"
    EXPERIMENT_ORDER="$order"
    MEM_FRACTION_STATIC="${MEM_FRACTION_STATIC:-0.45}"
    DISABLE_CUDA_GRAPH=0
    CUDA_GRAPH_MAX_BS_DECODE="${CUDA_GRAPH_MAX_BS_DECODE:-96}"
    DISABLE_PREFILL_CUDA_GRAPH=1
    SERVER_RANDOM_SEED="${SERVER_RANDOM_SEED:-42}"
    REPLAY_TIMEOUT_SECONDS="${REPLAY_TIMEOUT_SECONDS:-5400}"
    AGENTKV_RUNTIME_CACHE_ROOT="$RUNTIME_CACHE_ROOT"
    ENABLE_JIT_WARMUP="${ENABLE_JIT_WARMUP:-1}"
    JIT_WARMUP_HORIZON_SECONDS="${JIT_WARMUP_HORIZON_SECONDS:-60}"
    JIT_WARMUP_OUTPUT_TOKENS="${JIT_WARMUP_OUTPUT_TOKENS:-4}"
    JIT_WARMUP_TIMEOUT_SECONDS="${JIT_WARMUP_TIMEOUT_SECONDS:-1800}"
    bash "$SCRIPT_DIR/run_experiment.sh")
  if [[ "$pair_resume" == "1" ]]; then
    "${pair_command[@]}" |& tee -a "$pair_log"
  else
    "${pair_command[@]}" |& tee "$pair_log"
  fi
done

"$PYTHON" "$SCRIPT_DIR/summarize_full_experiment.py" --full-run-dir "$FULL_RUN_DIR"
STATUS=completed
write_status completed
echo "[full] completed: $FULL_RUN_DIR"
