#!/usr/bin/env bash
# 原生 SGLang：部署 GLM-5.1（BF16 / GlmMoeDsa）vanilla。
# 模型别名：/share/dai-sys/models/glm-5.1 → zhoulongsheng/models/zai-org/GLM-5.1
# 参考：SGLang 测试 COMMON_ARGS（reasoning=glm45, tool-call=glm47）
set -euo pipefail

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
# ~/.cache/{tvm-ffi,deep_gemm} 属 root 时 JIT 会 PermissionError；
# deep_gemm 走 $HOME/.cache/deep_gemm，需一并改 HOME
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache
export XDG_CACHE_HOME=/tmp/xdg_cache
export HOME=/tmp/agentkv_home
export PYTHONPATH=/share/dai-sys/zhoulongsheng/agentkv/Engine/sglang/python${PYTHONPATH:+:$PYTHONPATH}

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME"

MODEL="${MODEL:-/share/dai-sys/models/glm-5.1}"
PORT="${PORT:-30000}"
TP="${TP:-8}"

# BF16 全量约 1.4T 落盘；8×80GB 可能吃紧，OOM 时可调低 mem-fraction 或加卡/换量化权重
exec /share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/sglang serve \
  --trust-remote-code \
  --model-path "$MODEL" \
  --served-model-name glm-5.1 \
  --tp "$TP" \
  --port "$PORT" \
  --host 0.0.0.0 \
  --reasoning-parser glm45 \
  --tool-call-parser glm47 \
  --mem-fraction-static "${MEM_FRACTION_STATIC:-0.85}" \
  --enable-metrics \
  --enable-cache-report \
  --radix-eviction-policy lru
