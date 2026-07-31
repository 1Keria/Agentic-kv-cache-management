#!/usr/bin/env bash
# DeepSeek-V4-Flash 原版基线：radix=LRU。
# 用途：混合流量实验 —— 先跑 vanilla 看问题。
set -euo pipefail

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
# ~/.cache/{tvm-ffi,deep_gemm} 属 root，JIT 无法写入 → PermissionError
# deep_gemm 走 $HOME/.cache/deep_gemm，不认 XDG_CACHE_HOME，需一并改 HOME
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache
export XDG_CACHE_HOME=/tmp/xdg_cache
export HOME=/tmp/agentkv_home
export PYTHONPATH=/share/dai-sys/zhoulongsheng/agentkv/Engine/sglang/python${PYTHONPATH:+:$PYTHONPATH}

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME"

MODEL="${MODEL:-/share/dai-sys/models/deepseek-v4-flash}"
PORT="${PORT:-30000}"
TP="${TP:-8}"

exec /share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/sglang serve \
  --trust-remote-code \
  --model-path "$MODEL" \
  --served-model-name deepseek-v4-flash \
  --tp "$TP" \
  --moe-runner-backend marlin \
  --port "$PORT" \
  --host 0.0.0.0 \
  --mem-fraction-static "${MEM_FRACTION_STATIC:-0.85}" \
  --enable-metrics \
  --enable-cache-report \
  --radix-eviction-policy lru
