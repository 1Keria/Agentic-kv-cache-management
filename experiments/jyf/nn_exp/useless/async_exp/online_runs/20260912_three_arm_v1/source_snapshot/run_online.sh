#!/usr/bin/env bash
set -Eeuo pipefail
BASE=/share/dai-sys/zhoulongsheng/agentkv
EXP="$BASE/experiments/nn_exp/async_exp"
PY=/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/python
SGLANG=/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/sglang
RUN="$EXP/online_runs/${1:-$(date +%Y%m%d_%H%M%S)}"
WORK="$BASE/experiments/nn_exp/cold_predictor_exp/workloads/agent050_decode32"
PID=""
[[ ! -e "$RUN" ]] || { echo "Run exists: $RUN" >&2; exit 2; }
mkdir -p "$RUN"
exec > >(tee "$RUN/orchestrator.log") 2>&1
cleanup() {
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID"
    for _ in $(seq 1 90); do
      kill -0 "$PID" 2>/dev/null || break
      sleep 1
    done
  fi
}
trap cleanup EXIT
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUNTIME_ROOT=/share/dai-sys/jiaoyifan/agentkv_runtime_cold_frontier
export TVM_FFI_CACHE_DIR="$RUNTIME_ROOT/tvm_ffi_cache"
export XDG_CACHE_HOME="$RUNTIME_ROOT/xdg_cache"
export SGLANG_OPT_SWA_RADIX_CACHE_COMPACT=0
mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME"
unset ASYNC_TEST_MODE
for mode in lru sync async; do
  if ss -ltn | grep -q ':30000 '; then
    echo 'Port 30000 is in use' >&2; exit 2
  fi
  max_used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -nr | head -1)
  if (( max_used > 1024 )); then
    echo "GPUs busy: ${max_used} MiB" >&2; exit 2
  fi
  arm="$RUN/$mode"
  mkdir -p "$arm/metrics" "$arm/replay"
  echo "$mode START $(date -Is)" | tee "$RUN/status"
  ASYNC_SERVING_MODE="$mode" ASYNC_SERVING_OUT="$arm/metrics" PYTHONPATH="$EXP" \
  "$SGLANG" serve --trust-remote-code \
    --model-path /share/dai-sys/models/deepseek-v4-flash --served-model-name deepseek-v4-flash \
    --tp 8 --moe-runner-backend marlin --reasoning-parser deepseek-v4 --tool-call-parser deepseekv4 \
    --port 30000 --host 127.0.0.1 --mem-fraction-static 0.45 --watchdog-timeout 900 \
    --random-seed 42 --enable-metrics --enable-cache-report --radix-eviction-policy lru \
    >"$arm/server.log" 2>&1 &
  PID=$!
  echo "$PID" > "$arm/server.pid"
  ready=0
  for _ in $(seq 1 180); do
    kill -0 "$PID" 2>/dev/null || { tail -80 "$arm/server.log"; exit 3; }
    if curl -fsS --max-time 3 http://127.0.0.1:30000/health >/dev/null 2>&1; then ready=1; break; fi
    sleep 10
  done
  (( ready == 1 )) || exit 4
  echo "$mode REPLAY $(date -Is)" | tee "$RUN/status"
  curl -fsS http://127.0.0.1:30000/get_server_info > "$arm/server_info.json"
  "$PY" "$BASE/scripts/python/replay_mix_workload.py" \
    --base-url http://127.0.0.1:30000 --workload-dir "$WORK" --output-dir "$arm/replay" \
    --arrival waves --arrival-seed 42 --arrival-horizon-s 300 --arrival-waves 9 \
    --arrival-wave-width-s 20 --gap-scale 0.02 \
    >"$arm/replay.log" 2>&1
  curl -fsS http://127.0.0.1:30000/metrics > "$arm/prometheus.txt"
  cleanup
  wait "$PID" || true
  PID=""
  echo "$mode COMPLETE $(date -Is)" | tee "$RUN/status"
  sleep 3
done
echo "COMPLETE $(date -Is)" | tee "$RUN/status"
