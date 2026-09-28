#!/usr/bin/env bash
# Source this file from the Agentic-kv-cache-management root.
export AGENTKV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$AGENTKV_ROOT/scripts/python:$AGENTKV_ROOT/Engine/sglang/python:$AGENTKV_ROOT/Engine/LMCache:$AGENTKV_ROOT:${PYTHONPATH:-}"
export HF_DATASETS_CACHE="${HF_DATASETS_CACHE:-$AGENTKV_ROOT/.cache/huggingface/datasets}"
export HF_HOME="${HF_HOME:-$AGENTKV_ROOT/.cache/huggingface}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"
# Default to the available GPU; override with DEVICE=cpu when needed.
export DEVICE="${DEVICE:-cuda}"
