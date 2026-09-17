#!/usr/bin/env bash
# GLM-5.1-FP8 双节点 TP=16 —— Session 返回时间采集（从节点）
#
# 主节点起好后再跑。输出跟主节点同一 run 目录。
set -euo pipefail

REPO="/share/dai-sys/zhoulongsheng/agentkv"
# shellcheck source=/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/session_return_out.sh
source "$REPO/scripts/shell/session_return_out.sh"
session_return_load_run

DUMP_HOOK="$REPO/scripts/python/session_return_dump"
ENGINE="$REPO/Engine/sglang/python"
export SESSION_RETURN_DUMP_DIR="$RUN_DIR/server_dump_node1"
mkdir -p "$SESSION_RETURN_DUMP_DIR"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache
export XDG_CACHE_HOME=/tmp/xdg_cache
export HOME=/tmp/agentkv_home
export PYTHONPATH="$DUMP_HOOK:$ENGINE${PYTHONPATH:+:$PYTHONPATH}"
export NCCL_SOCKET_IFNAME="${NCCL_SOCKET_IFNAME:-eth0}"
export GLOO_SOCKET_IFNAME="${GLOO_SOCKET_IFNAME:-eth0}"
export NCCL_IB_DISABLE="${NCCL_IB_DISABLE:-0}"
export NCCL_IB_HCA="${NCCL_IB_HCA:-mlx5_0,mlx5_1,mlx5_6,mlx5_7}"
export NCCL_NET_GDR_LEVEL="${NCCL_NET_GDR_LEVEL:-PHB}"
export NCCL_DEBUG="${NCCL_DEBUG:-WARN}"
export RADIX_EVICTION_POLICY="${RADIX_EVICTION_POLICY:-lru}"
if [[ -n "${SESSION_RETURN_TAU_CKPT:-}" ]]; then
  export SESSION_RETURN_TAU_CKPT
fi

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME"

MODEL="${MODEL:-/share/dai-sys/models/glm-5.1-fp8}"
echo "[glm51_session_return_node1] host=$(hostname) run=$RUN_DIR dump=$SESSION_RETURN_DUMP_DIR policy=$RADIX_EVICTION_POLICY tau=${SESSION_RETURN_TAU_CKPT:-off}"

exec /share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/sglang serve \
  --trust-remote-code \
  --model-path "$MODEL" \
  --served-model-name glm-5.1-fp8 \
  --tp 16 \
  --nnodes 2 \
  --node-rank 1 \
  --dist-init-addr 10.204.92.79:20000 \
  --port 30000 \
  --host 0.0.0.0 \
  --reasoning-parser glm45 \
  --tool-call-parser glm47 \
  --mem-fraction-static "${MEM_FRACTION_STATIC:-0.85}" \
  --enable-metrics \
  --enable-cache-report \
  --radix-eviction-policy "$RADIX_EVICTION_POLICY"
