#!/usr/bin/env bash
# GLM-5.1-FP8 双节点 TP=16 —— 从节点（node-rank 1）
# 模型：/share/dai-sys/models/glm-5.1-fp8
#
# 在从节点（H800-dai-sys-2 / 10.204.86.124）执行：
#   bash scripts/shell/glm51_node1.sh
#
# dist-init 须与 node0 一致；HTTP 只在主节点 :30000 提供。
# KV：GPU radix + HiCache L2（host，ratio=2，write_through）；须与 node0 一致。
set -euo pipefail

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache
export XDG_CACHE_HOME=/tmp/xdg_cache
export HOME=/tmp/agentkv_home
export PYTHONPATH=/share/dai-sys/zhoulongsheng/agentkv/Engine/sglang/python${PYTHONPATH:+:$PYTHONPATH}
# bootstrap 走 eth0；数据面只用 Active IB（须与 node0 一致）
export NCCL_SOCKET_IFNAME="${NCCL_SOCKET_IFNAME:-eth0}"
export GLOO_SOCKET_IFNAME="${GLOO_SOCKET_IFNAME:-eth0}"
export NCCL_IB_DISABLE="${NCCL_IB_DISABLE:-0}"
export NCCL_IB_HCA="${NCCL_IB_HCA:-mlx5_0,mlx5_1,mlx5_6,mlx5_7}"
export NCCL_NET_GDR_LEVEL="${NCCL_NET_GDR_LEVEL:-PHB}"
export NCCL_DEBUG="${NCCL_DEBUG:-WARN}"

mkdir -p "$TVM_FFI_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME"

MODEL="${MODEL:-/share/dai-sys/models/glm-5.1-fp8}"
echo "[glm51_node1] host=$(hostname) NODE_RANK=1/2 TP=16 MODEL=$MODEL DIST_INIT=10.204.92.79:20000 PORT=30000 NCCL_IB_HCA=$NCCL_IB_HCA"

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
  --enable-hierarchical-cache \
  --hicache-ratio 2 \
  --hicache-write-policy write_through \
  --enable-metrics \
  --enable-cache-report \
  --radix-eviction-policy "${RADIX_EVICTION_POLICY:-agentic}"
