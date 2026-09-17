#!/usr/bin/env bash
# V4 Flash TP=8 —— 把 GLM 线上切分在 Flash 上 LRU 采集 request_end
#
# 纯 LRU，不挂 τ̂。输出在
# experiments/session_return/replay_glm_on_v4flash/latest/
#
# 就绪后：curl http://127.0.0.1:30000/health
# 然后：  bash scripts/shell/replay_glm_on_v4flash.sh
# 冒烟：  MAX_EVENTS=200 bash scripts/shell/replay_glm_on_v4flash.sh
set -euo pipefail

REPO="/share/dai-sys/zhoulongsheng/agentkv"
# shellcheck source=/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/v4flash_session_return_out.sh
source "$REPO/scripts/shell/v4flash_session_return_out.sh"
session_return_init_run

DUMP_HOOK="$REPO/scripts/python/session_return_dump"
ENGINE="$REPO/Engine/sglang/python"
export SESSION_RETURN_DUMP_DIR="$RUN_DIR/server_dump"
mkdir -p "$SESSION_RETURN_DUMP_DIR"
unset SESSION_RETURN_TAU_CKPT

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
# /tmp/agentkv_home 里 flashinfer cached_ops 被 root 建成 755，JIT lock 写不进去会把 TP worker 打崩。
RUNTIME_ROOT="${RUNTIME_ROOT:-/share/dai-sys/${USER:-$(id -un)}/agentkv_runtime}"
export HOME="$RUNTIME_ROOT"
export TVM_FFI_CACHE_DIR="$RUNTIME_ROOT/tvm_ffi_cache"
export XDG_CACHE_HOME="$RUNTIME_ROOT/xdg_cache"
export PYTHONPATH="$DUMP_HOOK:$ENGINE${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME"

MODEL="${MODEL:-/share/dai-sys/models/deepseek-v4-flash}"
echo "[v4flash_session_return] host=$(hostname) run=$RUN_DIR dump=$SESSION_RETURN_DUMP_DIR policy=lru model=$MODEL home=$HOME"

exec /share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/sglang serve \
  --trust-remote-code \
  --model-path "$MODEL" \
  --served-model-name deepseek-v4-flash \
  --tp 8 \
  --moe-runner-backend marlin \
  --reasoning-parser deepseek-v4 \
  --tool-call-parser deepseekv4 \
  --port 30000 \
  --host 0.0.0.0 \
  --mem-fraction-static "${MEM_FRACTION_STATIC:-0.45}" \
  --watchdog-timeout 900 \
  --enable-metrics \
  --enable-cache-report \
  --radix-eviction-policy lru
