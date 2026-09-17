#!/usr/bin/env bash
set -Eeuo pipefail

BASE=/share/dai-sys/zhoulongsheng/agentkv
EXP="$BASE/experiments/jyf/nn_exp/cold_predictor_exp"
PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/python
SGLANG=/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/sglang
RUN_TAG=${RUN_TAG:-$(date +%Y%m%d_%H%M%S)}
ARRIVAL_MODE=${COLD_ARRIVAL_MODE:-waves}
GAP_SCALE=${COLD_GAP_SCALE:-0.02}
RUN="$EXP/runs/$RUN_TAG"
TRACE="$RUN/frontier_trace"
WORK="$EXP/workloads/agent050_decode32"
SERVER_LOG="$RUN/server.log"
REPLAY_OUT="$RUN/replay"
PID=""

mkdir -p "$RUN" "$TRACE" "$REPLAY_OUT"
exec > >(tee "$RUN/orchestrator.log") 2>&1

if [[ ! -f "$WORK/workload.jsonl" ]]; then
  "$PYTHON" "$BASE/scripts/shell/jyf/prepare_cold_frontier_workload.py" \
    --source "$BASE/workloads/ratio_sweep_v4flash_unseen/agent_050" \
    --output "$WORK" --max-tokens 32
fi

cleanup() {
  local rc=$?
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" || true
    for _ in $(seq 1 90); do
      kill -0 "$PID" 2>/dev/null || break
      sleep 1
    done
  fi
  return "$rc"
}
trap cleanup EXIT

if ss -ltn | grep -q ':30000 '; then
  echo "port 30000 already in use" >&2
  exit 2
fi

MAX_GPU_USED=$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits 2>/dev/null | awk 'BEGIN{m=0} {if ($1>m)m=$1} END{print m}')
if [[ ${MAX_GPU_USED:-0} -gt 1024 ]]; then
  echo "GPU already in use (largest compute allocation ${MAX_GPU_USED} MiB)" >&2
  exit 2
fi

export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
RUNTIME_ROOT="/share/dai-sys/${USER:-jiaoyifan}/agentkv_runtime_cold_frontier"
export TVM_FFI_CACHE_DIR="$RUNTIME_ROOT/tvm_ffi_cache"
export XDG_CACHE_HOME="$RUNTIME_ROOT/xdg_cache"
export COLD_FRONTIER_TRACE_DIR="$TRACE"
export COLD_FRONTIER_SAMPLE_EVERY=1
export PYTHONPATH="$BASE/scripts/shell/jyf/cold_frontier_site"
mkdir -p "$RUNTIME_ROOT" "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME"

echo "[$(date '+%F %T')] starting instrumented LRU server"
"$SGLANG" serve \
  --trust-remote-code \
  --model-path /share/dai-sys/models/deepseek-v4-flash \
  --served-model-name deepseek-v4-flash \
  --tp 8 \
  --moe-runner-backend marlin \
  --reasoning-parser deepseek-v4 \
  --tool-call-parser deepseekv4 \
  --port 30000 --host 0.0.0.0 \
  --mem-fraction-static 0.45 \
  --watchdog-timeout 900 \
  --enable-metrics --enable-cache-report \
  --radix-eviction-policy lru >"$SERVER_LOG" 2>&1 &
PID=$!
echo "$PID" >"$RUN/server.pid"

for _ in $(seq 1 180); do
  kill -0 "$PID" 2>/dev/null || { tail -100 "$SERVER_LOG"; exit 3; }
  curl -fsS --max-time 5 http://127.0.0.1:30000/health >/dev/null && break
  sleep 10
done
curl -fsS --max-time 5 http://127.0.0.1:30000/health >/dev/null

echo "[$(date '+%F %T')] starting accelerated held-out replay"
if [[ "$ARRIVAL_MODE" == "frozen" ]]; then
  ARRIVAL_ARGS=(--arrival frozen --gap-scale "$GAP_SCALE")
else
  ARRIVAL_ARGS=(--arrival waves --arrival-horizon-s 300 --arrival-waves 9 --arrival-wave-width-s 20 --gap-scale "$GAP_SCALE")
fi
"$PYTHON" "$BASE/scripts/python/replay_mix_workload.py" \
  --base-url http://127.0.0.1:30000 \
  --workload-dir "$WORK" \
  --output-dir "$REPLAY_OUT" \
  "${ARRIVAL_ARGS[@]}" 2>&1 | tee "$RUN/replay.log"

echo "[$(date '+%F %T')] replay complete"
kill -TERM "$PID"
for _ in $(seq 1 90); do
  kill -0 "$PID" 2>/dev/null || break
  sleep 1
done
PID=""
ln -sfn "$RUN" "$EXP/latest_collection"
echo "DONE $RUN"
