#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

export MODEL_PATH="${MODEL_PATH:-/mnt/public/dai-sys/.cache/hub/hub/models--deepseek-ai--DeepSeek-V4-Flash/snapshots/fd53f944496234770ba80e15004f9b6d269a71f5}"
export SGLANG_BIN="${SGLANG_BIN:-$REPO_ROOT/experiments/evicition_policy/runtime/venv/bin/sglang}"

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
ENABLE_REQUEST_CACHE_REGIONS=1 \
REQUEST_CACHE_REGION_POLICY=borrow \
REQUEST_CACHE_BORROW_LAZY_RECLASSIFY=1 \
REQUEST_AGENT_CACHE_RATIO="${REQUEST_AGENT_CACHE_RATIO:-0.61}" \
  exec bash scripts/shell/v4flash.sh "${SERVER_ARGS[@]}" "$@"
