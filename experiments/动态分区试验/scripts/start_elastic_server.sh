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
# Elastic mode derives its soft tier from the resident mix.  Keep the legacy
# ratio at the neutral midpoint when callers do not provide one; it is not a
# workload forecast or a hard quota in this mode.
# Keep the shared-pool candidate conservative when one region has been idle;
# callers can set 0 to reproduce the ungated tail-first control.
ENABLE_REQUEST_CACHE_REGIONS=1 \
REQUEST_CACHE_REGION_POLICY=elastic \
REQUEST_AGENT_CACHE_RATIO="${REQUEST_AGENT_CACHE_RATIO:-0.50}" \
REQUEST_CACHE_AGENT_MIN_RATIO="${REQUEST_CACHE_AGENT_MIN_RATIO:-0.2}" \
REQUEST_CACHE_AGENT_MAX_RATIO="${REQUEST_CACHE_AGENT_MAX_RATIO:-0.8}" \
REQUEST_CACHE_ELASTIC_RECLAIM_ORDER="${REQUEST_CACHE_ELASTIC_RECLAIM_ORDER:-request_first}" \
REQUEST_CACHE_ELASTIC_SOFT_STEP="${REQUEST_CACHE_ELASTIC_SOFT_STEP:-0.1}" \
REQUEST_CACHE_ELASTIC_ACTIVITY_WINDOW="${REQUEST_CACHE_ELASTIC_ACTIVITY_WINDOW:-32}" \
REQUEST_CACHE_ELASTIC_GHOST_CAPACITY_TOKENS="${REQUEST_CACHE_ELASTIC_GHOST_CAPACITY_TOKENS:-0}" \
REQUEST_CACHE_ELASTIC_GHOST_PRESSURE_DECAY="${REQUEST_CACHE_ELASTIC_GHOST_PRESSURE_DECAY:-0.95}" \
REQUEST_CACHE_ELASTIC_GHOST_BIAS="${REQUEST_CACHE_ELASTIC_GHOST_BIAS:-0.5}" \
REQUEST_CACHE_ELASTIC_GHOST_RECLAIM="${REQUEST_CACHE_ELASTIC_GHOST_RECLAIM:-1}" \
REQUEST_CACHE_ELASTIC_GHOST_PROTECT="${REQUEST_CACHE_ELASTIC_GHOST_PROTECT:-0}" \
REQUEST_CACHE_ELASTIC_GHOST_PROTECT_MIN_TOKENS="${REQUEST_CACHE_ELASTIC_GHOST_PROTECT_MIN_TOKENS:-0}" \
REQUEST_CACHE_ELASTIC_FEEDBACK="${REQUEST_CACHE_ELASTIC_FEEDBACK:-0}" \
REQUEST_CACHE_BORROWED_SEGMENT_TOKENS="${REQUEST_CACHE_BORROWED_SEGMENT_TOKENS:-0}" \
  exec bash scripts/shell/v4flash.sh "${SERVER_ARGS[@]}" "$@"
