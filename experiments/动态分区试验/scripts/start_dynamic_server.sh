#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

export MODEL_PATH="${MODEL_PATH:-/inspire/hdd/global_public/public_models/deepseek-ai/deepSeek-V4-Flash}"
export SGLANG_BIN="${SGLANG_BIN:-$REPO_ROOT/experiments/固定分区试验对比/scripts/sglang_venv.sh}"

SERVER_ARGS=()
case "${DISABLE_CUDA_GRAPH:-1}" in
  1) SERVER_ARGS+=(--disable-cuda-graph) ;;
  0)
    SERVER_ARGS+=(--cuda-graph-max-bs-decode "${CUDA_GRAPH_MAX_BS_DECODE:-96}")
    if [[ "${DISABLE_PREFILL_CUDA_GRAPH:-1}" == "1" ]]; then
      SERVER_ARGS+=(--cuda-graph-backend-prefill disabled)
    fi
    ;;
  *) echo "DISABLE_CUDA_GRAPH 只能为 0 或 1。" >&2; exit 1 ;;
esac
SERVER_ARGS+=(--random-seed "${SERVER_RANDOM_SEED:-42}")

cd "$REPO_ROOT"
# Kept only for compatibility with old launch wrappers; dynamic mode ignores it.
ENABLE_REQUEST_CACHE_REGIONS=1 \
REQUEST_CACHE_REGION_POLICY=dynamic \
REQUEST_AGENT_CACHE_RATIO="${REQUEST_AGENT_CACHE_RATIO:-0.61}" \
REQUEST_CACHE_RATIO_WINDOW_REQUESTS="${REQUEST_CACHE_RATIO_WINDOW_REQUESTS:-0}" \
REQUEST_CACHE_RATIO_ALPHA="${REQUEST_CACHE_RATIO_ALPHA:-0.2}" \
REQUEST_CACHE_RATIO_FEEDBACK_MODE="${REQUEST_CACHE_RATIO_FEEDBACK_MODE:-normalized_pressure}" \
REQUEST_CACHE_RATIO_MAX_STEP="${REQUEST_CACHE_RATIO_MAX_STEP:-0.05}" \
REQUEST_CACHE_RATIO_PRESSURE_HYSTERESIS="${REQUEST_CACHE_RATIO_PRESSURE_HYSTERESIS:-0.02}" \
REQUEST_CACHE_RATIO_COOLDOWN_EVICTED_TOKENS="${REQUEST_CACHE_RATIO_COOLDOWN_EVICTED_TOKENS:-4096}" \
REQUEST_CACHE_AGENT_MIN_RATIO="${REQUEST_CACHE_AGENT_MIN_RATIO:-0.2}" \
REQUEST_CACHE_AGENT_MAX_RATIO="${REQUEST_CACHE_AGENT_MAX_RATIO:-0.8}" \
REQUEST_CACHE_FEEDBACK_MIN_EVICTED_TOKENS="${REQUEST_CACHE_FEEDBACK_MIN_EVICTED_TOKENS:-0}" \
  exec bash scripts/shell/v4flash.sh "${SERVER_ARGS[@]}" "$@"
