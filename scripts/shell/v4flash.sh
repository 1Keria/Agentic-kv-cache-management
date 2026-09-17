
#   bash scripts/shell/v4flash.sh
set -euo pipefail

export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache
export XDG_CACHE_HOME=/tmp/xdg_cache
export HOME=/tmp/agentkv_home
export PYTHONPATH=/share/dai-sys/zhoulongsheng/agentkv/Engine/sglang/python

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME"

echo "[v4flash] host=$(hostname) TP=8 PORT=30000 MODEL=/share/dai-sys/models/deepseek-v4-flash EVICTION=lru"

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
  --radix-eviction-policy lru
