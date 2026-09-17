#!/usr/bin/env bash
#
# dsv4_vanilla_lru LRU server 启动器(官方 sglang 0.5.13 / env agentkv_jyf)
#
# 镜像 scripts/shell/v4flash.sh 的参数,但:
#   * python/sglang 用 agentkv_jyf(官方 upstream 0.5.13,未改动) —— 作 LRU 对比基线;
#   * 关键:不设置 PYTHONPATH 指向 Engine/sglang(fork 源码),否则会退回 fork 版。
#
# 用法: bash scripts/shell/jyf/dsv4_vanilla_lru_server.sh
# 起来后: curl http://127.0.0.1:30000/health
# 然后:   bash scripts/shell/jyf/run_dsv4_vanilla_lru_ratio_sweep.sh
set -euo pipefail

export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# 运行时缓存目录放共享盘,不放节点本地:
# (1) 原 v4flash.sh 的 /tmp/agentkv_home 等是 zhoulongsheng 建的(775,对他人只读),
#     flashinfer 0.6.12 启动要往 $HOME/.cache/flashinfer/ 追加 JIT 日志 → PermissionError;
# (2) 本节点 /tmp、/home、/ 都在同一个 overlay 100G(已用 ~50G),内核/编译缓存堆 /tmp 会写爆。
# 所以这里按用户自建到共享盘 /share/dai-sys/<user>/agentkv_runtime/(Lustre 大分区,可跨重启/节点复用)。
RUNTIME_ROOT="/share/dai-sys/${USER:-$(id -un)}/agentkv_runtime"
export HOME="$RUNTIME_ROOT"
export TVM_FFI_CACHE_DIR="$RUNTIME_ROOT/tvm_ffi_cache"
export XDG_CACHE_HOME="$RUNTIME_ROOT/xdg_cache"

# 注意: 这里不要导出 PYTHONPATH=.../agentkv/Engine/sglang/python

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME"

SGLANG=/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/sglang

echo "[dsv4_vanilla_lru] host=$(hostname) TP=8 PORT=30000 MODEL=/share/dai-sys/models/deepseek-v4-flash EVICTION=lru ENV=agentkv_jyf(official sglang 0.5.13)"

exec "$SGLANG" serve \
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
