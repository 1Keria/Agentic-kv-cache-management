
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
REQUEST_CACHE_REGION_POLICY="${REQUEST_CACHE_REGION_POLICY:-fixed}"
# Deprecated compatibility option; dynamic mode uses eviction feedback.
REQUEST_CACHE_RATIO_WINDOW_REQUESTS="${REQUEST_CACHE_RATIO_WINDOW_REQUESTS:-0}"
REQUEST_CACHE_RATIO_ALPHA="${REQUEST_CACHE_RATIO_ALPHA:-0.2}"
REQUEST_CACHE_RATIO_FEEDBACK_MODE="${REQUEST_CACHE_RATIO_FEEDBACK_MODE:-eviction_share}"
REQUEST_CACHE_RATIO_MAX_STEP="${REQUEST_CACHE_RATIO_MAX_STEP:-0.05}"
REQUEST_CACHE_RATIO_PRESSURE_HYSTERESIS="${REQUEST_CACHE_RATIO_PRESSURE_HYSTERESIS:-0.0}"
REQUEST_CACHE_RATIO_COOLDOWN_EVICTED_TOKENS="${REQUEST_CACHE_RATIO_COOLDOWN_EVICTED_TOKENS:-0}"
REQUEST_CACHE_AGENT_MIN_RATIO="${REQUEST_CACHE_AGENT_MIN_RATIO:-0.2}"
REQUEST_CACHE_AGENT_MAX_RATIO="${REQUEST_CACHE_AGENT_MAX_RATIO:-0.8}"
REQUEST_CACHE_ELASTIC_RECLAIM_ORDER="${REQUEST_CACHE_ELASTIC_RECLAIM_ORDER:-request_first}"
REQUEST_CACHE_ELASTIC_PREFERRED_RECLAIM="${REQUEST_CACHE_ELASTIC_PREFERRED_RECLAIM:-1}"
REQUEST_CACHE_ELASTIC_SOFT_STEP="${REQUEST_CACHE_ELASTIC_SOFT_STEP:-1.0}"
REQUEST_CACHE_ELASTIC_ACTIVITY_WINDOW="${REQUEST_CACHE_ELASTIC_ACTIVITY_WINDOW:-0}"
REQUEST_CACHE_ELASTIC_ACTIVITY_REQUIRES_HIT="${REQUEST_CACHE_ELASTIC_ACTIVITY_REQUIRES_HIT:-0}"
REQUEST_CACHE_ELASTIC_GHOST_CAPACITY_TOKENS="${REQUEST_CACHE_ELASTIC_GHOST_CAPACITY_TOKENS:-0}"
REQUEST_CACHE_ELASTIC_GHOST_PRESSURE_DECAY="${REQUEST_CACHE_ELASTIC_GHOST_PRESSURE_DECAY:-0.95}"
REQUEST_CACHE_ELASTIC_GHOST_BIAS="${REQUEST_CACHE_ELASTIC_GHOST_BIAS:-0.5}"
REQUEST_CACHE_ELASTIC_GHOST_RECLAIM="${REQUEST_CACHE_ELASTIC_GHOST_RECLAIM:-1}"
REQUEST_CACHE_ELASTIC_GHOST_PROTECT="${REQUEST_CACHE_ELASTIC_GHOST_PROTECT:-0}"
REQUEST_CACHE_ELASTIC_GHOST_PROTECT_MIN_TOKENS="${REQUEST_CACHE_ELASTIC_GHOST_PROTECT_MIN_TOKENS:-0}"
REQUEST_CACHE_ELASTIC_FEEDBACK="${REQUEST_CACHE_ELASTIC_FEEDBACK:-0}"
REQUEST_CACHE_FEEDBACK_MIN_EVICTED_TOKENS="${REQUEST_CACHE_FEEDBACK_MIN_EVICTED_TOKENS:-0}"
# Keep borrowed prefixes until the shared pool is full. Set these explicitly
# for experiments that want proactive hysteretic reclaim.
REQUEST_CACHE_BORROW_HIGH_WATERMARK_TOKENS="${REQUEST_CACHE_BORROW_HIGH_WATERMARK_TOKENS:-0}"
REQUEST_CACHE_BORROW_LOW_WATERMARK_TOKENS="${REQUEST_CACHE_BORROW_LOW_WATERMARK_TOKENS:-0}"
REQUEST_CACHE_BORROW_LAZY_RECLASSIFY="${REQUEST_CACHE_BORROW_LAZY_RECLASSIFY:-0}"
REQUEST_CACHE_BORROWED_SEGMENT_TOKENS="${REQUEST_CACHE_BORROWED_SEGMENT_TOKENS:-0}"
# The model may choose a conservative SWA/full split by default.  Experiments
# can override it explicitly while keeping the same value across all modes.
SWA_FULL_TOKENS_RATIO="${SWA_FULL_TOKENS_RATIO:-}"

REQUEST_CACHE_ARGS=()
if [[ "$ENABLE_REQUEST_CACHE_REGIONS" == "1" ]]; then
  # Region-aware caches currently require the classic RadixCache/SWARadixCache
  # implementations.  The unified and experimental C++ trees do not carry
  # the region bookkeeping yet; force the supported backend here so an
  # inherited shell environment cannot make a partitioned run fail during
  # cache construction.
  export SGLANG_ENABLE_UNIFIED_RADIX_TREE=0
  export SGLANG_EXPERIMENTAL_CPP_RADIX_TREE=0
  REQUEST_CACHE_ARGS=(
    --enable-request-cache-regions
    --request-classifier-checkpoint "$REQUEST_CLASSIFIER_CHECKPOINT"
    --request-classifier-threshold "$REQUEST_CLASSIFIER_THRESHOLD"
    --request-agent-cache-ratio "$REQUEST_AGENT_CACHE_RATIO"
    --request-cache-region-policy "$REQUEST_CACHE_REGION_POLICY"
    --request-cache-ratio-window-requests "$REQUEST_CACHE_RATIO_WINDOW_REQUESTS"
    --request-cache-ratio-alpha "$REQUEST_CACHE_RATIO_ALPHA"
    --request-cache-ratio-feedback-mode "$REQUEST_CACHE_RATIO_FEEDBACK_MODE"
    --request-cache-ratio-max-step "$REQUEST_CACHE_RATIO_MAX_STEP"
    --request-cache-ratio-pressure-hysteresis "$REQUEST_CACHE_RATIO_PRESSURE_HYSTERESIS"
    --request-cache-ratio-cooldown-evicted-tokens "$REQUEST_CACHE_RATIO_COOLDOWN_EVICTED_TOKENS"
    --request-cache-agent-min-ratio "$REQUEST_CACHE_AGENT_MIN_RATIO"
    --request-cache-agent-max-ratio "$REQUEST_CACHE_AGENT_MAX_RATIO"
    --request-cache-elastic-reclaim-order "$REQUEST_CACHE_ELASTIC_RECLAIM_ORDER"
    --request-cache-elastic-soft-step "$REQUEST_CACHE_ELASTIC_SOFT_STEP"
    --request-cache-elastic-activity-window "$REQUEST_CACHE_ELASTIC_ACTIVITY_WINDOW"
    --request-cache-elastic-ghost-capacity-tokens "$REQUEST_CACHE_ELASTIC_GHOST_CAPACITY_TOKENS"
    --request-cache-elastic-ghost-pressure-decay "$REQUEST_CACHE_ELASTIC_GHOST_PRESSURE_DECAY"
    --request-cache-elastic-ghost-bias "$REQUEST_CACHE_ELASTIC_GHOST_BIAS"
    --request-cache-elastic-ghost-protect-min-tokens "$REQUEST_CACHE_ELASTIC_GHOST_PROTECT_MIN_TOKENS"
    --request-cache-feedback-min-evicted-tokens "$REQUEST_CACHE_FEEDBACK_MIN_EVICTED_TOKENS"
    --request-cache-borrow-high-watermark-tokens "$REQUEST_CACHE_BORROW_HIGH_WATERMARK_TOKENS"
    --request-cache-borrow-low-watermark-tokens "$REQUEST_CACHE_BORROW_LOW_WATERMARK_TOKENS"
    --request-cache-borrowed-segment-tokens "$REQUEST_CACHE_BORROWED_SEGMENT_TOKENS"
  )
  if [[ "$REQUEST_CACHE_ELASTIC_PREFERRED_RECLAIM" == "1" ]]; then
    REQUEST_CACHE_ARGS+=(--request-cache-elastic-preferred-reclaim)
  else
    REQUEST_CACHE_ARGS+=(--no-request-cache-elastic-preferred-reclaim)
  fi
  if [[ "$REQUEST_CACHE_ELASTIC_GHOST_RECLAIM" == "1" ]]; then
    REQUEST_CACHE_ARGS+=(--request-cache-elastic-ghost-reclaim)
  elif [[ "$REQUEST_CACHE_ELASTIC_GHOST_RECLAIM" == "0" ]]; then
    REQUEST_CACHE_ARGS+=(--no-request-cache-elastic-ghost-reclaim)
  else
    echo "REQUEST_CACHE_ELASTIC_GHOST_RECLAIM 只能为 0 或 1。" >&2
    exit 1
  fi
  if [[ "$REQUEST_CACHE_ELASTIC_GHOST_PROTECT" == "1" ]]; then
    REQUEST_CACHE_ARGS+=(--request-cache-elastic-ghost-protect)
  elif [[ "$REQUEST_CACHE_ELASTIC_GHOST_PROTECT" == "0" ]]; then
    REQUEST_CACHE_ARGS+=(--no-request-cache-elastic-ghost-protect)
  else
    echo "REQUEST_CACHE_ELASTIC_GHOST_PROTECT 只能为 0 或 1。" >&2
    exit 1
  fi
  if [[ "$REQUEST_CACHE_ELASTIC_FEEDBACK" == "1" ]]; then
    REQUEST_CACHE_ARGS+=(--request-cache-elastic-feedback)
  elif [[ "$REQUEST_CACHE_ELASTIC_FEEDBACK" == "0" ]]; then
    REQUEST_CACHE_ARGS+=(--no-request-cache-elastic-feedback)
  else
    echo "REQUEST_CACHE_ELASTIC_FEEDBACK 只能为 0 或 1。" >&2
    exit 1
  fi
  if [[ "$REQUEST_CACHE_BORROW_LAZY_RECLASSIFY" == "1" ]]; then
    REQUEST_CACHE_ARGS+=(--request-cache-borrow-lazy-reclassify)
  elif [[ "$REQUEST_CACHE_BORROW_LAZY_RECLASSIFY" != "0" ]]; then
    echo "REQUEST_CACHE_BORROW_LAZY_RECLASSIFY 只能为 0 或 1。" >&2
    exit 1
  fi
  if [[ "$REQUEST_CACHE_ELASTIC_ACTIVITY_REQUIRES_HIT" == "1" ]]; then
    REQUEST_CACHE_ARGS+=(--request-cache-elastic-activity-requires-hit)
  elif [[ "$REQUEST_CACHE_ELASTIC_ACTIVITY_REQUIRES_HIT" != "0" ]]; then
    echo "REQUEST_CACHE_ELASTIC_ACTIVITY_REQUIRES_HIT 只能为 0 或 1。" >&2
    exit 1
  fi
fi

SWA_CAPACITY_ARGS=()
if [[ -n "$SWA_FULL_TOKENS_RATIO" ]]; then
  SWA_CAPACITY_ARGS+=(--swa-full-tokens-ratio "$SWA_FULL_TOKENS_RATIO")
fi

if [[ ! -x "$SGLANG_BIN" ]]; then
  SGLANG_BIN="$(command -v sglang || true)"
fi
if [[ -z "$SGLANG_BIN" ]]; then
  echo "找不到 sglang 可执行文件，请设置 SGLANG_BIN。" >&2
  exit 1
fi

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME" "$DG_JIT_CACHE_DIR"

echo "[v4flash] host=$(hostname) TP=$TP_SIZE PORT=$PORT MODEL=$MODEL_PATH EVICTION=lru REGION_POLICY=$REQUEST_CACHE_REGION_POLICY AGENT_RATIO=$REQUEST_AGENT_CACHE_RATIO"

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
  "${SWA_CAPACITY_ARGS[@]}" \
  "${REQUEST_CACHE_ARGS[@]}" \
  "$@"
