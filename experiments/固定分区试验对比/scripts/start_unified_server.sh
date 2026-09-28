#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

export MODEL_PATH="${MODEL_PATH:-/inspire/hdd/global_public/public_models/deepseek-ai/deepSeek-V4-Flash}"
export SGLANG_BIN="${SGLANG_BIN:-$SCRIPT_DIR/sglang_venv.sh}"

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
ENABLE_REQUEST_CACHE_REGIONS=0 \
  exec bash scripts/shell/v4flash.sh "${SERVER_ARGS[@]}" "$@"
