#!/usr/bin/env bash
# 原生 SGLang：Qwen3-8B / 1×H800
set -euo pipefail

export CUDA_VISIBLE_DEVICES=0
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache
export XDG_CACHE_HOME=/tmp/xdg_cache
export HOME=/tmp/agentkv_home
export PYTHONPATH=/share/dai-sys/zhoulongsheng/agentkv/Engine/sglang/python${PYTHONPATH:+:$PYTHONPATH}

mkdir -p /tmp/tvm_ffi_cache /tmp/xdg_cache /tmp/agentkv_home

exec /share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/sglang serve \
  --model-path /share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218 \
  --port 8004 \
  --tp 1 \
  --trust-remote-code \
  --mem-fraction-static 0.85 \
  --schedule-policy lpm \
  --enable-metrics \
  --enable-cache-report \
  --chunked-prefill-size 4096 \
  --radix-eviction-policy lru \
  --skip-server-warmup
