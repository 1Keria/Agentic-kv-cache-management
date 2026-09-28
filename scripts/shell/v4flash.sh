
#   bash scripts/shell/v4flash.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
RUNTIME_CACHE_ROOT="${AGENTKV_RUNTIME_CACHE_ROOT:-/tmp/agentkv_v4flash_runtime}"
export TVM_FFI_CACHE_DIR="${TVM_FFI_CACHE_DIR:-$RUNTIME_CACHE_ROOT/tvm_ffi_cache}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$RUNTIME_CACHE_ROOT/xdg_cache}"
export HOME="${AGENTKV_SERVER_HOME:-$RUNTIME_CACHE_ROOT/home}"
export DG_JIT_CACHE_DIR="${DG_JIT_CACHE_DIR:-$HOME/.cache/deep_gemm}"
export PYTHONPATH="${SGLANG_REPO_ROOT:-$REPO_ROOT}/Engine/sglang/python${PYTHONPATH:+:$PYTHONPATH}"

SGLANG_BIN="${SGLANG_BIN:-/usr/local/bin/sglang}"
MODEL_PATH="${MODEL_PATH:-/inspire/hdd/global_public/public_models/deepseek-ai/deepSeek-V4-Flash}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-deepseek-v4-flash}"
TP_SIZE="${TP_SIZE:-8}"
PORT="${PORT:-30000}"
MEM_FRACTION_STATIC="${MEM_FRACTION_STATIC:-0.45}"
ENABLE_REQUEST_CACHE_REGIONS="${ENABLE_REQUEST_CACHE_REGIONS:-0}"
REQUEST_CLASSIFIER_CHECKPOINT="${REQUEST_CLASSIFIER_CHECKPOINT:-$REPO_ROOT/models/request_classifier/checkpoints/final_system_free/budget_4/request_classifier.pt}"
REQUEST_CLASSIFIER_THRESHOLD="${REQUEST_CLASSIFIER_THRESHOLD:-0.5}"
REQUEST_AGENT_CACHE_RATIO="${REQUEST_AGENT_CACHE_RATIO:-0.5}"

REQUEST_CACHE_ARGS=()
if [[ "$ENABLE_REQUEST_CACHE_REGIONS" == "1" ]]; then
  REQUEST_CACHE_ARGS=(
    --enable-request-cache-regions
    --request-classifier-checkpoint "$REQUEST_CLASSIFIER_CHECKPOINT"
    --request-classifier-threshold "$REQUEST_CLASSIFIER_THRESHOLD"
    --request-agent-cache-ratio "$REQUEST_AGENT_CACHE_RATIO"
  )
fi

if [[ ! -x "$SGLANG_BIN" ]]; then
  SGLANG_BIN="$(command -v sglang || true)"
fi
if [[ -z "$SGLANG_BIN" ]]; then
  echo "找不到 sglang 可执行文件，请设置 SGLANG_BIN。" >&2
  exit 1
fi

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME" "$DG_JIT_CACHE_DIR"

echo "[v4flash] host=$(hostname) TP=$TP_SIZE PORT=$PORT MODEL=$MODEL_PATH EVICTION=lru"

exec "$SGLANG_BIN" serve \
  --trust-remote-code \
  --model-path "$MODEL_PATH" \
  --served-model-name "$SERVED_MODEL_NAME" \
  --tp "$TP_SIZE" \
  --moe-runner-backend marlin \
  --reasoning-parser deepseek-v4 \
  --tool-call-parser deepseekv4 \
  --port "$PORT" \
  --host 0.0.0.0 \
  --mem-fraction-static "$MEM_FRACTION_STATIC" \
  --watchdog-timeout 900 \
  --enable-metrics \
  --enable-cache-report \
  --radix-eviction-policy lru \
  "${REQUEST_CACHE_ARGS[@]}" \
  "$@"
