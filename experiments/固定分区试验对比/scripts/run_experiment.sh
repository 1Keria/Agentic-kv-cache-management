#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EXPERIMENT_ROOT="$REPO_ROOT/experiments/固定分区试验对比"
WORKLOAD_DIR="$EXPERIMENT_ROOT/data/token_balanced_openhands_wildchat"
MODEL_PATH="${MODEL_PATH:-/inspire/hdd/global_public/public_models/deepseek-ai/deepSeek-V4-Flash}"
SGLANG_BIN="${SGLANG_BIN:-$SCRIPT_DIR/sglang_venv.sh}"
VENV_ROOT="${AGENTKV_V4FLASH_VENV:-/inspire/hdd/project/inference-chip/czxs25240022/.venvs/agentkv-v4flash}"
PYTHON="${PARTITION_EXPERIMENT_PYTHON:-$VENV_ROOT/bin/python}"
PORT="${PORT:-30000}"
BASE_URL="http://127.0.0.1:$PORT"
RUN_ID="${PARTITION_EXPERIMENT_RUN_ID:-$(date -u +%Y%m%d_%H%M%S)}"
RUN_DIR="${PARTITION_EXPERIMENT_RUN_DIR:-$EXPERIMENT_ROOT/results/runs/$RUN_ID}"
SELECTED_RATIO_ENV="$EXPERIMENT_ROOT/results/selected_ratio.env"
CLASSIFIER_CHECKPOINT="${REQUEST_CLASSIFIER_CHECKPOINT:-$REPO_ROOT/models/request_classifier/checkpoints/final_system_free/budget_4/request_classifier.pt}"
MEM_FRACTION_STATIC="${MEM_FRACTION_STATIC:-0.45}"
DISABLE_CUDA_GRAPH="${DISABLE_CUDA_GRAPH:-1}"
CUDA_GRAPH_MAX_BS_DECODE="${CUDA_GRAPH_MAX_BS_DECODE:-96}"
DISABLE_PREFILL_CUDA_GRAPH="${DISABLE_PREFILL_CUDA_GRAPH:-1}"
SERVER_RANDOM_SEED="${SERVER_RANDOM_SEED:-42}"
REPLAY_TIMEOUT_SECONDS="${REPLAY_TIMEOUT_SECONDS:-3600}"
EXPERIMENT_ORDER="${EXPERIMENT_ORDER:-unified-first}"
RUNTIME_CACHE_ROOT="${AGENTKV_RUNTIME_CACHE_ROOT:-/tmp/agentkv_v4flash_runtime}"
ENABLE_JIT_WARMUP="${ENABLE_JIT_WARMUP:-0}"
JIT_WARMUP_HORIZON_SECONDS="${JIT_WARMUP_HORIZON_SECONDS:-60}"
JIT_WARMUP_OUTPUT_TOKENS="${JIT_WARMUP_OUTPUT_TOKENS:-4}"
JIT_WARMUP_TIMEOUT_SECONDS="${JIT_WARMUP_TIMEOUT_SECONDS:-1800}"
RESUME="${PARTITION_EXPERIMENT_RESUME:-0}"
SERVER_PID=""
SERVER_GROUP=""
PREFLIGHT_ONLY=0
RUN_STAGE="preflight"

die() {
  echo "[error] $*" >&2
  exit 1
}

read_config_value() {
  local key=$1
  sed -n "s/^${key}=//p" "$RUN_DIR/config.env" 2>/dev/null | tail -n 1
}

require_config_value() {
  local key=$1
  local expected=$2
  local actual
  actual="$(read_config_value "$key")"
  [[ "$actual" == "$expected" ]] \
    || die "恢复配置不一致：$key 期望 '$expected'，已有 '$actual'"
}

mode_is_complete() {
  local mode=$1
  local mode_dir="$RUN_DIR/$mode"
  [[ -f "$mode_dir/run_mix_replay/summary.json" ]] \
    && [[ -f "$mode_dir/server_info_before.json" ]] \
    && [[ -f "$mode_dir/server_info_after.json" ]] \
    || return 1
  "$PYTHON" - "$mode_dir/run_mix_replay/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text())
integrity = summary.get("integrity") or {}
if integrity.get("n_issued") != 1261 or integrity.get("n_ok") != 1261 or integrity.get("n_err") != 0:
    raise SystemExit(1)
PY
}

archive_incomplete_mode() {
  local mode=$1
  local mode_dir="$RUN_DIR/$mode"
  [[ -d "$mode_dir" ]] || return 0
  local archive_dir="$RUN_DIR/aborted_attempts/${mode}_$(date -u +%Y%m%d_%H%M%S)_interrupted"
  mkdir -p "$RUN_DIR/aborted_attempts"
  mv "$mode_dir" "$archive_dir"
  cat >"$archive_dir/INVALID.md" <<EOF
# 中断策略运行，不纳入统计

- 策略：$mode
- 归档时间：$(date -u +%Y-%m-%dT%H:%M:%SZ)
- 原因：策略回放未完整结束；恢复时仅重新运行该策略。
EOF
  echo "[resume] archived incomplete mode=$mode to $archive_dir"
}

if [[ "${1:-}" == "--preflight-only" ]]; then
  PREFLIGHT_ONLY=1
  shift
fi
if [[ $# -ne 0 ]]; then
  die "未知参数：$*"
fi

cleanup_server() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "[server] stopping pid=$SERVER_PID"
    kill -TERM -- "-$SERVER_GROUP" 2>/dev/null || kill -TERM "$SERVER_PID" 2>/dev/null || true
    for _ in $(seq 1 120); do
      if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        break
      fi
      sleep 1
    done
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      kill -KILL -- "-$SERVER_GROUP" 2>/dev/null || kill -KILL "$SERVER_PID" 2>/dev/null || true
    fi
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  SERVER_PID=""
  SERVER_GROUP=""
}

write_run_status() {
  local status=$1
  [[ -d "$RUN_DIR" ]] || return 0
  cat >"$RUN_DIR/run_status.env" <<EOF
RUN_ID=$RUN_ID
STATUS=$status
STAGE=$RUN_STAGE
UPDATED_AT_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
}

on_exit() {
  local status=$?
  cleanup_server
  if [[ "$status" -eq 0 && "$RUN_STAGE" == "completed" ]]; then
    write_run_status completed
  elif [[ -d "$RUN_DIR" ]]; then
    write_run_status failed
  fi
  trap - EXIT INT TERM
  exit "$status"
}
trap on_exit EXIT INT TERM

verify_inputs() {
  [[ -d "$MODEL_PATH" ]] || die "模型目录不存在：$MODEL_PATH"
  [[ -x "$SGLANG_BIN" ]] || die "sglang 不可执行：$SGLANG_BIN"
  [[ -x "$PYTHON" ]] || die "实验 Python 不可执行：$PYTHON"
  [[ -f "$CLASSIFIER_CHECKPOINT" ]] || die "分类器不存在：$CLASSIFIER_CHECKPOINT"
  [[ -f "$WORKLOAD_DIR/workload.jsonl" ]] || die "workload 不存在"
  [[ -f "$WORKLOAD_DIR/manifest.json" ]] || die "manifest 不存在"
  command -v curl >/dev/null || die "缺少 curl"
  command -v nvidia-smi >/dev/null || die "缺少 nvidia-smi"
  command -v timeout >/dev/null || die "缺少 timeout"
  [[ "$REPLAY_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] \
    && (( REPLAY_TIMEOUT_SECONDS >= 3600 )) \
    || die "REPLAY_TIMEOUT_SECONDS 必须是至少 3600 秒的整数"
  [[ "$DISABLE_CUDA_GRAPH" == "0" || "$DISABLE_CUDA_GRAPH" == "1" ]] \
    || die "DISABLE_CUDA_GRAPH 只能为 0 或 1"
  [[ "$DISABLE_PREFILL_CUDA_GRAPH" == "0" || "$DISABLE_PREFILL_CUDA_GRAPH" == "1" ]] \
    || die "DISABLE_PREFILL_CUDA_GRAPH 只能为 0 或 1"
  [[ "$CUDA_GRAPH_MAX_BS_DECODE" =~ ^[0-9]+$ ]] \
    && (( CUDA_GRAPH_MAX_BS_DECODE >= 1 )) \
    || die "CUDA_GRAPH_MAX_BS_DECODE 必须是正整数"
  [[ "$EXPERIMENT_ORDER" == "unified-first" || "$EXPERIMENT_ORDER" == "partitioned-first" ]] \
    || die "EXPERIMENT_ORDER 只能为 unified-first 或 partitioned-first"
  [[ "$ENABLE_JIT_WARMUP" == "0" || "$ENABLE_JIT_WARMUP" == "1" ]] \
    || die "ENABLE_JIT_WARMUP 只能为 0 或 1"
  [[ "$JIT_WARMUP_OUTPUT_TOKENS" =~ ^[0-9]+$ ]] \
    && (( JIT_WARMUP_OUTPUT_TOKENS >= 1 )) \
    || die "JIT_WARMUP_OUTPUT_TOKENS 必须是正整数"
  [[ "$SERVER_RANDOM_SEED" =~ ^[0-9]+$ ]] \
    || die "SERVER_RANDOM_SEED 必须是非负整数"
  [[ "$RESUME" == "0" || "$RESUME" == "1" ]] \
    || die "PARTITION_EXPERIMENT_RESUME 只能为 0 或 1"
  if curl -fsS --max-time 2 "$BASE_URL/health" >/dev/null 2>&1; then
    die "$PORT 端口已有健康服务，拒绝覆盖"
  fi
  if ss -ltn "sport = :$PORT" 2>/dev/null | tail -n +2 | grep -q .; then
    die "$PORT 端口已被占用"
  fi
  mapfile -t gpu_indices < <(nvidia-smi --query-gpu=index --format=csv,noheader,nounits)
  [[ ${#gpu_indices[@]} -ge 8 ]] || die "需要至少 8 张 GPU，当前只有 ${#gpu_indices[@]} 张"
  mapfile -t compute_pids < <(
    nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits 2>/dev/null \
      | sed '/^[[:space:]]*$/d' | sort -u
  )
  if [[ ${#compute_pids[@]} -ne 0 ]]; then
    die "GPU 上已有计算进程：${compute_pids[*]}"
  fi
  if [[ "$RESUME" == "0" && -e "$RUN_DIR" ]]; then
    die "结果目录已存在：$RUN_DIR"
  fi
  if [[ "$RESUME" == "1" && ! -f "$RUN_DIR/config.env" ]]; then
    die "恢复配置不存在：$RUN_DIR/config.env"
  fi
  PYTHONPATH="$REPO_ROOT/Engine/sglang/python${PYTHONPATH:+:$PYTHONPATH}" \
    "$SGLANG_BIN" version >/dev/null
  PYTHONPATH="$REPO_ROOT/Engine/sglang/python${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON" - <<'PY'
import requests
from openai import AsyncOpenAI
from sglang.srt.entrypoints.http_server import app
from transformers import AutoTokenizer

print("client dependencies ok")
PY
}

wait_for_server() {
  local log_path=$1
  for _ in $(seq 1 1800); do
    if curl -fsS --max-time 5 "$BASE_URL/health" >/dev/null 2>&1; then
      echo "[server] ready"
      return 0
    fi
    if [[ -n "$SERVER_PID" ]] && ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "[server] exited during startup" >&2
      tail -n 200 "$log_path" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "[server] startup timeout" >&2
  tail -n 200 "$log_path" >&2 || true
  return 1
}

start_server() {
  local mode=$1
  local log_path=$2
  shift 2
  echo "[server] starting mode=$mode log=$log_path"
  setsid env \
    MODEL_PATH="$MODEL_PATH" \
    SGLANG_BIN="$SGLANG_BIN" \
    PORT="$PORT" \
    CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}" \
    MEM_FRACTION_STATIC="$MEM_FRACTION_STATIC" \
    DISABLE_CUDA_GRAPH="$DISABLE_CUDA_GRAPH" \
    CUDA_GRAPH_MAX_BS_DECODE="$CUDA_GRAPH_MAX_BS_DECODE" \
    DISABLE_PREFILL_CUDA_GRAPH="$DISABLE_PREFILL_CUDA_GRAPH" \
    SERVER_RANDOM_SEED="$SERVER_RANDOM_SEED" \
    AGENTKV_RUNTIME_CACHE_ROOT="$RUNTIME_CACHE_ROOT" \
    REQUEST_CLASSIFIER_CHECKPOINT="$CLASSIFIER_CHECKPOINT" \
    REQUEST_CLASSIFIER_THRESHOLD="${REQUEST_CLASSIFIER_THRESHOLD:-0.5}" \
    "$@" \
    bash "$SCRIPT_DIR/start_${mode}_server.sh" \
    >"$log_path" 2>&1 &
  SERVER_PID=$!
  SERVER_GROUP=$SERVER_PID
  wait_for_server "$log_path"
}

save_server_info() {
  local output=$1
  curl -fsS "$BASE_URL/server_info" | "$PYTHON" -m json.tool >"$output"
}

extract_capacities() {
  local server_log=$1
  local server_info=$2
  "$PYTHON" - "$server_log" "$server_info" <<'PY'
import json
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
info_path = Path(sys.argv[2])
text = log_path.read_text(errors="replace")
matches = re.findall(r"DSV4 pool sizes: full=(\d+), swa=(\d+)", text)
if matches:
    full, swa = map(int, matches[0])
else:
    info = json.loads(info_path.read_text())
    full = int(info.get("max_total_num_tokens") or info["internal_states"][0]["memory_usage"]["token_capacity"])
    page_size = int(info.get("page_size") or 256)
    ratio = float(info.get("swa_full_tokens_ratio") or 0.1)
    swa = int(full * ratio) // page_size * page_size
print(full, swa)
PY
}

run_replay() {
  local mode=$1
  local mode_dir="$RUN_DIR/$mode"
  echo "[replay] mode=$mode"
  MIX_REPLAY_RUN_ROOT="$mode_dir" \
  MIX_REPLAY_RUN_ID="replay" \
  MIX_REPLAY_PYTHON="$PYTHON" \
    timeout --foreground --signal=TERM --kill-after=60s \
      "$REPLAY_TIMEOUT_SECONDS" \
      bash "$SCRIPT_DIR/replay_workload.sh" --base-url "$BASE_URL"
}

run_jit_warmup() {
  local mode=$1
  local mode_dir="$RUN_DIR/$mode"
  local warmup_log="$mode_dir/jit_warmup.log"
  echo "[warmup] mode=$mode full workload, horizon=${JIT_WARMUP_HORIZON_SECONDS}s, output_tokens=$JIT_WARMUP_OUTPUT_TOKENS"
  MIX_REPLAY_RUN_ROOT="$mode_dir" \
  MIX_REPLAY_RUN_ID="jit_warmup" \
  MIX_REPLAY_PYTHON="$PYTHON" \
    timeout --foreground --signal=TERM --kill-after=60s \
      "$JIT_WARMUP_TIMEOUT_SECONDS" \
      bash "$SCRIPT_DIR/replay_workload.sh" \
        --base-url "$BASE_URL" \
        --arrival uniform \
        --arrival-horizon-s "$JIT_WARMUP_HORIZON_SECONDS" \
        --gap-scale 0 \
        --request-gap-cap-s 0 \
        --max-output-tokens-override "$JIT_WARMUP_OUTPUT_TOKENS" \
        --no-flush-cache \
      >"$warmup_log" 2>&1
  "$PYTHON" - "$mode_dir/run_mix_jit_warmup/summary.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
summary = json.loads(path.read_text())
integrity = summary["integrity"]
if integrity.get("n_ok") != 1261 or integrity.get("n_err") != 0:
    raise SystemExit(f"JIT warmup failed integrity check: {integrity}")
print(
    f"[warmup] completed ok={integrity['n_ok']} "
    f"wall={integrity['wall_clock_s']}s"
)
PY
}

flush_and_verify_cache() {
  local mode=$1
  local mode_dir="$RUN_DIR/$mode"
  curl -fsS -X POST "$BASE_URL/flush_cache?timeout=120" \
    >"$mode_dir/flush_cache_response.txt"
  save_server_info "$mode_dir/server_info_after_flush.json"
  "$PYTHON" - "$mode" "$mode_dir/server_info_after_flush.json" <<'PY'
import json
import sys
from pathlib import Path

mode = sys.argv[1]
info = json.loads(Path(sys.argv[2]).read_text())
states = info.get("internal_states") or []
if mode == "partitioned":
    regions = (states[0] if states else {}).get("request_cache_regions") or {}
    for name in ("agent", "request"):
        block = regions.get(name) or {}
        for field in (
            "full_used_tokens",
            "swa_used_tokens",
            "full_evicted_tokens",
            "swa_evicted_tokens",
            "eviction_count",
        ):
            if int(block.get(field) or 0) != 0:
                raise SystemExit(
                    f"cache flush verification failed: {name}.{field}={block.get(field)}"
                )
print(f"[warmup] cache and metrics reset verified for mode={mode}")
PY
}

wait_for_server_release() {
  for _ in $(seq 1 120); do
    local gpu_pids
    gpu_pids="$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits 2>/dev/null | sed '/^[[:space:]]*$/d')"
    if [[ -z "$gpu_pids" ]] \
      && ! ss -ltn "sport = :$PORT" 2>/dev/null | tail -n +2 | grep -q .; then
      return 0
    fi
    sleep 1
  done
  die "前一服务停止后 GPU 或端口未在 120 秒内释放，拒绝启动下一服务"
}

verify_inputs
if [[ "$PREFLIGHT_ONLY" == "1" ]]; then
  echo "[preflight] 模型、分类器、workload、端口、8 张 GPU 和运行依赖均已通过检查"
  echo "[preflight] 当前离线比例：$(grep '^AGENT_CACHE_CAPACITY_RATIO=' "$SELECTED_RATIO_ENV" 2>/dev/null || echo '尚未生成')"
  exit 0
fi
if [[ "$RESUME" == "1" ]]; then
  require_config_value RUN_ID "$RUN_ID"
  require_config_value MODEL_PATH "$MODEL_PATH"
  require_config_value MEM_FRACTION_STATIC "$MEM_FRACTION_STATIC"
  require_config_value DISABLE_CUDA_GRAPH "$DISABLE_CUDA_GRAPH"
  require_config_value CUDA_GRAPH_MAX_BS_DECODE "$CUDA_GRAPH_MAX_BS_DECODE"
  require_config_value DISABLE_PREFILL_CUDA_GRAPH "$DISABLE_PREFILL_CUDA_GRAPH"
  require_config_value SERVER_RANDOM_SEED "$SERVER_RANDOM_SEED"
  require_config_value EXPERIMENT_ORDER "$EXPERIMENT_ORDER"
  require_config_value AGENTKV_RUNTIME_CACHE_ROOT "$RUNTIME_CACHE_ROOT"
  require_config_value ENABLE_JIT_WARMUP "$ENABLE_JIT_WARMUP"
  echo "[resume] resuming paired experiment: $RUN_DIR"
else
  mkdir -p "$RUN_DIR/unified" "$RUN_DIR/partitioned"
  cat >"$RUN_DIR/config.env" <<EOF
RUN_ID=$RUN_ID
MODEL_PATH=$MODEL_PATH
SGLANG_BIN=$SGLANG_BIN
VENV_ROOT=$VENV_ROOT
PYTHON=$PYTHON
PORT=$PORT
CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}
MEM_FRACTION_STATIC=$MEM_FRACTION_STATIC
DISABLE_CUDA_GRAPH=$DISABLE_CUDA_GRAPH
CUDA_GRAPH_MAX_BS_DECODE=$CUDA_GRAPH_MAX_BS_DECODE
DISABLE_PREFILL_CUDA_GRAPH=$DISABLE_PREFILL_CUDA_GRAPH
SERVER_RANDOM_SEED=$SERVER_RANDOM_SEED
REPLAY_TIMEOUT_SECONDS=$REPLAY_TIMEOUT_SECONDS
EXPERIMENT_ORDER=$EXPERIMENT_ORDER
AGENTKV_RUNTIME_CACHE_ROOT=$RUNTIME_CACHE_ROOT
ENABLE_JIT_WARMUP=$ENABLE_JIT_WARMUP
JIT_WARMUP_HORIZON_SECONDS=$JIT_WARMUP_HORIZON_SECONDS
JIT_WARMUP_OUTPUT_TOKENS=$JIT_WARMUP_OUTPUT_TOKENS
JIT_WARMUP_TIMEOUT_SECONDS=$JIT_WARMUP_TIMEOUT_SECONDS
REQUEST_CLASSIFIER_CHECKPOINT=$CLASSIFIER_CHECKPOINT
REQUEST_CLASSIFIER_THRESHOLD=${REQUEST_CLASSIFIER_THRESHOLD:-0.5}
EOF
  cp "$WORKLOAD_DIR/manifest.json" "$RUN_DIR/workload_manifest.json"
  nvidia-smi --query-gpu=index,name,uuid,memory.total,driver_version \
    --format=csv,noheader >"$RUN_DIR/gpu_inventory.csv"
fi
RUN_STAGE="initialized"
write_run_status running

if [[ "$EXPERIMENT_ORDER" == "unified-first" ]]; then
  MODES=(unified partitioned)
else
  MODES=(partitioned unified)
  [[ -f "$SELECTED_RATIO_ENV" ]] || die "固定分区先运行时需要已有的 selected_ratio.env"
  # shellcheck disable=SC1090
  source "$SELECTED_RATIO_ENV"
  [[ -n "${AGENT_CACHE_CAPACITY_RATIO:-}" ]] || die "selected_ratio.env 中没有有效比例"
fi

if [[ "$RESUME" == "1" ]]; then
  FULL_CACHE_CAPACITY_TOKENS="$(read_config_value ACTUAL_FULL_CACHE_CAPACITY_TOKENS)"
  SWA_CACHE_CAPACITY_TOKENS="$(read_config_value ACTUAL_SWA_CACHE_CAPACITY_TOKENS)"
  if [[ ! -f "$RUN_DIR/selected_ratio.env" && -f "$SELECTED_RATIO_ENV" ]]; then
    cp "$SELECTED_RATIO_ENV" "$RUN_DIR/selected_ratio.env"
  fi
  [[ -f "$RUN_DIR/selected_ratio.env" ]] || die "恢复目录缺少 selected_ratio.env"
  # shellcheck disable=SC1090
  source "$RUN_DIR/selected_ratio.env"
else
  FULL_CACHE_CAPACITY_TOKENS=""
  SWA_CACHE_CAPACITY_TOKENS=""
fi
for mode_index in 0 1; do
  mode="${MODES[$mode_index]}"
  if [[ "$RESUME" == "1" ]] && mode_is_complete "$mode"; then
    echo "[resume] skipping completed mode=$mode"
    continue
  fi
  if [[ "$RESUME" == "1" ]]; then
    archive_incomplete_mode "$mode"
    mkdir -p "$RUN_DIR/$mode"
  fi
  RUN_STAGE="${mode}_startup"
  write_run_status running
  if [[ "$mode" == "partitioned" ]]; then
    start_server partitioned "$RUN_DIR/partitioned/server.log" \
      AGENT_CACHE_CAPACITY_RATIO="$AGENT_CACHE_CAPACITY_RATIO"
  else
    start_server unified "$RUN_DIR/unified/server.log"
  fi
  if [[ "$ENABLE_JIT_WARMUP" == "1" ]]; then
    run_jit_warmup "$mode"
    save_server_info "$RUN_DIR/$mode/server_info_after_warmup.json"
    flush_and_verify_cache "$mode"
  fi
  save_server_info "$RUN_DIR/$mode/server_info_before.json"
  read -r mode_full_capacity mode_swa_capacity < <(
    extract_capacities \
      "$RUN_DIR/$mode/server.log" \
      "$RUN_DIR/$mode/server_info_before.json"
  )
  echo "[capacity] mode=$mode full=$mode_full_capacity swa=$mode_swa_capacity"

  if [[ -z "$FULL_CACHE_CAPACITY_TOKENS" ]]; then
    FULL_CACHE_CAPACITY_TOKENS="$mode_full_capacity"
    SWA_CACHE_CAPACITY_TOKENS="$mode_swa_capacity"
    cat >>"$RUN_DIR/config.env" <<EOF
ACTUAL_FULL_CACHE_CAPACITY_TOKENS=$FULL_CACHE_CAPACITY_TOKENS
ACTUAL_SWA_CACHE_CAPACITY_TOKENS=$SWA_CACHE_CAPACITY_TOKENS
EOF
    ratio_used_before_selection="${AGENT_CACHE_CAPACITY_RATIO:-}"
    PARTITION_EXPERIMENT_PYTHON="$PYTHON" \
      bash "$SCRIPT_DIR/select_agent_cache_capacity_ratio.sh" \
      --model-path "$MODEL_PATH" \
      --full-cache-capacity-tokens "$FULL_CACHE_CAPACITY_TOKENS" \
      --swa-cache-capacity-tokens "$SWA_CACHE_CAPACITY_TOKENS"
    cp "$SELECTED_RATIO_ENV" "$RUN_DIR/selected_ratio.env"
    # shellcheck disable=SC1090
    source "$SELECTED_RATIO_ENV"
    [[ -n "${AGENT_CACHE_CAPACITY_RATIO:-}" ]] || die "离线比例选择未产生比例"
    if [[ "$mode" == "partitioned" && "$ratio_used_before_selection" != "$AGENT_CACHE_CAPACITY_RATIO" ]]; then
      die "固定分区已使用比例 $ratio_used_before_selection 启动，但实际容量重新选择出的比例为 $AGENT_CACHE_CAPACITY_RATIO"
    fi
  elif [[ "$mode_full_capacity" != "$FULL_CACHE_CAPACITY_TOKENS" ]] \
    || [[ "$mode_swa_capacity" != "$SWA_CACHE_CAPACITY_TOKENS" ]]; then
    die "控制变量失效：首轮容量 full=$FULL_CACHE_CAPACITY_TOKENS swa=$SWA_CACHE_CAPACITY_TOKENS；$mode 容量 full=$mode_full_capacity swa=$mode_swa_capacity"
  else
    echo "[control] capacities matched: full=$FULL_CACHE_CAPACITY_TOKENS swa=$SWA_CACHE_CAPACITY_TOKENS"
  fi

  RUN_STAGE="${mode}_replay"
  write_run_status running
  run_replay "$mode"
  save_server_info "$RUN_DIR/$mode/server_info_after.json"
  cleanup_server
  RUN_STAGE="between_services"
  write_run_status running
  wait_for_server_release
done

RUN_STAGE="comparison"
write_run_status running
"$PYTHON" "$SCRIPT_DIR/compare_experiment.py" --run-dir "$RUN_DIR"
RUN_STAGE="completed"
write_run_status completed
echo "[done] paired experiment prepared and completed: $RUN_DIR"
