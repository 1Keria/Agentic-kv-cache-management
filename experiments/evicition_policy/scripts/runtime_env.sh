#!/usr/bin/env bash
set -euo pipefail
EXPERIMENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export EXPERIMENT_ROOT
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1
export PYTHONPYCACHEPREFIX="$EXPERIMENT_ROOT/runtime/pycache"
export HOME="$EXPERIMENT_ROOT/runtime/home"
export XDG_CACHE_HOME="$EXPERIMENT_ROOT/runtime/cache"
export HF_HOME="$EXPERIMENT_ROOT/runtime/cache/huggingface"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export TRITON_CACHE_DIR="$EXPERIMENT_ROOT/runtime/cache/triton"
export TORCH_EXTENSIONS_DIR="$EXPERIMENT_ROOT/runtime/cache/torch_extensions"
export TVM_FFI_CACHE_DIR="$EXPERIMENT_ROOT/runtime/cache/tvm_ffi"
export DG_JIT_CACHE_DIR="$EXPERIMENT_ROOT/runtime/cache/deep_gemm"
export FLASHINFER_WORKSPACE_BASE="$EXPERIMENT_ROOT/runtime/cache/flashinfer"
mkdir -p "$EXPERIMENT_ROOT/runtime/tmp"
IPC_ALIAS="/tmp/evicition-ipc-$(printf '%s' "$EXPERIMENT_ROOT" | sha256sum | cut -c1-12)"
if [[ -L "$IPC_ALIAS" ]]; then
  [[ "$(readlink "$IPC_ALIAS")" == "$EXPERIMENT_ROOT/runtime/tmp" ]] || exit 1
elif [[ -e "$IPC_ALIAS" ]]; then
  echo "Refusing occupied IPC alias: $IPC_ALIAS" >&2
  exit 1
else
  ln -s "$EXPERIMENT_ROOT/runtime/tmp" "$IPC_ALIAS"
fi
export TMPDIR="$IPC_ALIAS"
export SGLANG_ENABLE_UNIFIED_RADIX_TREE=1
export SGLANG_EXPERIMENTAL_CPP_RADIX_TREE=0
export SGLANG_DEFAULT_THINKING=1 SGLANG_DSV4_REASONING_EFFORT=max
export PYTHON="$EXPERIMENT_ROOT/runtime/venv/bin/python"
mkdir -p "$HOME" "$XDG_CACHE_HOME" "$TMPDIR" "$DG_JIT_CACHE_DIR"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing isolated Python: $PYTHON" >&2
  exit 1
fi
