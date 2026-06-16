#!/bin/bash
# 启动 vLLM server 用于 KV cache 实验
# 用法: bash scripts/run_vllm_server.sh [gpu_util] [port]
#
# 环境变量控制可选功能：
#   KV_OFFLOAD_GIB=4       启用 KV offloading，设 4 GiB CPU 缓冲
#   KV_OFFLOAD_BACKEND=native  offloading 后端（native 或 lmcache）
#   ENABLE_KV_EVENTS=1     启用 ZMQ 发布 KV block 存入/驱逐事件
#
# 关键参数说明：
#   --enable-prefix-caching          启用 APC（block-level hash chain 复用）
#   --prefix-caching-hash-algo xxhash  用 xxhash 替代 sha256，更快（实验不需要密码学安全）
#   --enable-prompt-tokens-details   API 返回 cached_tokens 字段
#   --kv-cache-metrics               启用 block 生命周期追踪
#   --kv-cache-metrics-sample 1.0    采样率 100%（实验需要完整数据，生产用默认 0.01）
#   --kv-offloading-size             KV cache offloading 到 CPU 的缓冲区大小 (GiB)
#   --kv-offloading-backend native   使用 vLLM 内置 offloading（也可选 lmcache）
#   --kv-events-config               启用 ZMQ 发布 KV block 存入/驱逐事件（可选）
#   --watermark 0.02                 预留 2% KV 空间，避免频繁驱逐-重算抖动
#   --enable-chunked-prefill         启用分块 prefill（长 prompt 不阻塞短请求）

export LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH

GPU_UTIL=${1:-0.3}
PORT=${2:-8000}
MODEL_PATH="/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/"

# KV offloading 配置（可通过环境变量覆盖）
# 默认 8 GiB，约为 GPU KV 容量 (6 GiB) 的 1.3 倍
# 原理：CPU 缓冲需大于 GPU KV 才能存住被驱逐的 block 并提升命中率
# 参考：vLLM 官方文档 "set cpu_bytes_to_use larger than the aggregate GPU KV cache"
#       SimpleCPUOffloadConnector 默认值也是 8 GiB
KV_OFFLOAD_GIB=${KV_OFFLOAD_GIB:-8}
KV_OFFLOAD_BACKEND=${KV_OFFLOAD_BACKEND:-native}

# KV events 配置
ENABLE_KV_EVENTS=${ENABLE_KV_EVENTS:-0}

echo "Starting vLLM server..."
echo "  Model: Qwen3-8B"
echo "  GPU util: $GPU_UTIL"
echo "  Port: $PORT"
echo "  Prefix caching: ON (xxhash)"
echo "  Prompt tokens details: ON"
echo "  KV cache metrics: ON (sample=100%)"
echo "  KV offloading: ${KV_OFFLOAD_GIB} GiB (backend=$KV_OFFLOAD_BACKEND)"
echo "  KV events: $([ "$ENABLE_KV_EVENTS" = "1" ] && echo 'ON (ZMQ)' || echo 'OFF')"
echo "  Watermark: 0.02"
echo "  Chunked prefill: ON"

# 基础参数
ARGS=(
  --model "$MODEL_PATH"
  --served-model-name Qwen3-8B
  --block-size 16
  --kv-cache-dtype auto
  --enable-prefix-caching
  --prefix-caching-hash-algo xxhash
  --enable-prompt-tokens-details
  --kv-cache-metrics
  --kv-cache-metrics-sample 1.0
  --watermark 0.02
  --enable-chunked-prefill
  --gpu-memory-utilization "$GPU_UTIL"
  --max-model-len 32768
  --port "$PORT"
  --log-level info
)

# 可选：KV offloading 到 CPU
if [ "${KV_OFFLOAD_GIB}" != "0" ] && [ -n "${KV_OFFLOAD_GIB}" ]; then
  ARGS+=(
    --kv-offloading-size "$KV_OFFLOAD_GIB"
    --kv-offloading-backend "$KV_OFFLOAD_BACKEND"
  )
  echo "  → KV offloading enabled: ${KV_OFFLOAD_GIB} GiB via ${KV_OFFLOAD_BACKEND}"
fi

# 可选：KV events（ZMQ 发布 block 级别存入/驱逐事件）
if [ "$ENABLE_KV_EVENTS" = "1" ]; then
  ARGS+=(
    --kv-events-config '{"enable_kv_cache_events": true, "publisher": "zmq", "endpoint": "tcp://*:5557"}'
  )
  echo "  → KV events enabled: ZMQ on tcp://*:5557"
fi

echo ""
echo "Launching vLLM..."
echo ""

exec /share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python -m vllm.entrypoints.openai.api_server "${ARGS[@]}"
