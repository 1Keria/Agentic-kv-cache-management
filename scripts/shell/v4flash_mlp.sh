#!/usr/bin/env bash
# DeepSeek-V4-Flash 单节点 TP=8，MLP 驱逐。
# 除 --radix-eviction-policy 及 MLP 参数外，与 v4flash.sh 相同。
# 权重：/share/dai-sys/models/deepseek-v4-flash
#
#   bash scripts/shell/v4flash_mlp.sh
set -euo pipefail

export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache
export XDG_CACHE_HOME=/tmp/xdg_cache
export HOME=/tmp/agentkv_home
export PYTHONPATH=/share/dai-sys/zhoulongsheng/agentkv/Engine/sglang/python

MLP_CKPT="${MLP_CKPT:-/share/dai-sys/zhoulongsheng/agentkv/models/MLP/checkpoints/leaf_mlp.pt}"

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME"

echo "[v4flash-mlp] host=$(hostname) TP=8 PORT=30000 MODEL=/share/dai-sys/models/deepseek-v4-flash EVICTION=mlp ckpt=$MLP_CKPT lambda=0.05 alpha=1.0,1.0,1.0"

exec /share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/sglang serve \
  --trust-remote-code \
  --model-path /share/dai-sys/models/deepseek-v4-flash \
  --served-model-name deepseek-v4-flash \
  --tp 8 \
  --moe-runner-backend marlin \
  --reasoning-parser deepseek-v4 \
  --tool-call-parser deepseekv4 \
  --port 30000 \
  --host 0.0.0.0 \
  --mem-fraction-static 0.45 \
  --watchdog-timeout 900 \
  --enable-metrics \
  --enable-cache-report \
  --radix-eviction-policy mlp \
  --radix-mlp-checkpoint "$MLP_CKPT" \
  --radix-mlp-hold-lambda 0.05 \
  --radix-mlp-delta-alpha 1.0,1.0,1.0
