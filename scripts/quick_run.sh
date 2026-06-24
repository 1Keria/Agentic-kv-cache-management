#!/bin/bash
# 快速运行单个实验的辅助脚本
# 用法: bash scripts/quick_run.sh <exp_script> [args...]
# 例如: bash scripts/quick_run.sh run_exp4.py --subexp 4.1 --num-runs 1

set -e

EXP_SCRIPT="$1"
shift
ARGS="$@"

EXPERIMENT_DIR="/share/dai-sys/zhoulongsheng/agentkv/experiments/vllm_kv_cache"
CONDA_PYTHON="/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python"
SCRIPTS_DIR="/share/dai-sys/zhoulongsheng/agentkv/scripts"
PROJECT_DIR="/share/dai-sys/zhoulongsheng/agentkv"

# 从参数推断 offloading 配置
KV_OFFLOAD_GIB=8
VLLM_LOG_LEVEL="INFO"

# 检查参数中的 offload 配置
for arg in "$@"; do
    case "$arg" in
        off) KV_OFFLOAD_GIB=0 ;;
        recompute|default) KV_OFFLOAD_GIB=0 ;;
    esac
done

# 如果是 exp4.5/4.6/5/6，用 DEBUG
case "$ARGS" in
    *4.5*|*4.6*|*exp5*|*lru*|*aware*|*exp6*|*swap*|*recompute*) VLLM_LOG_LEVEL="DEBUG" ;;
esac
case "$ARGS" in
    *off*) KV_OFFLOAD_GIB=0 ;;
esac

echo "=== Quick Run: $EXP_SCRIPT $ARGS ==="
echo "  Offload: ${KV_OFFLOAD_GIB} GiB"
echo "  Log level: $VLLM_LOG_LEVEL"

# 杀掉旧 server（更彻底）
echo "Killing old server..."
lsof -ti :8000 2>/dev/null | xargs kill -9 2>/dev/null || true
# 杀掉所有vllm相关进程
ps aux | grep "zhoulongsheng.*vllm" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true
sleep 10
# 再杀一次（EngineCore可能在子进程组中）
ps aux | grep "zhoulongsheng.*vllm" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true
sleep 5

# 选择空闲 GPU（自动检测最少占用的 GPU）
FREE_GPU=1
echo "  Using GPU: $FREE_GPU"

# 启动新 server
echo "Starting server..."
cd "$PROJECT_DIR"
CUDA_VISIBLE_DEVICES=$FREE_GPU \
KV_OFFLOAD_GIB=$KV_OFFLOAD_GIB \
VLLM_LOG_LEVEL=$VLLM_LOG_LEVEL \
UVICORN_LOG_LEVEL=$(echo $VLLM_LOG_LEVEL | tr '[:upper:]' '[:lower:]') \
bash scripts/run_vllm_server.sh > "$EXPERIMENT_DIR/server.log" 2>&1 &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"

# 等待 server 就绪
echo "Waiting for server..."
for i in $(seq 1 60); do
    if curl -s http://localhost:8000/v1/models > /dev/null 2>&1; then
        echo "Server ready after ${i}x5s!"
        break
    fi
    sleep 5
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        echo "Server died! Check $EXPERIMENT_DIR/server.log"
        tail -20 "$EXPERIMENT_DIR/server.log"
        exit 1
    fi
done

# 运行实验
echo "Running experiment: $EXP_SCRIPT $ARGS"
cd "$PROJECT_DIR"
$CONDA_PYTHON "scripts/$EXP_SCRIPT" $ARGS 2>&1

RESULT=$?
echo "Experiment exit code: $RESULT"

# 保存 server 日志（DEBUG 模式有用）
if [ "$VLLM_LOG_LEVEL" = "DEBUG" ]; then
    # 从参数中提取实验名
    EXP_NAME=$(echo "$ARGS" | grep -oP '(?:--subexp\s+\K[\d.]+|--config\s+\K\w+|--run\s+\K\w+)' | tr '\n' '_' | sed 's/_$//')
    if [ -n "$EXP_NAME" ]; then
        cp "$EXPERIMENT_DIR/server.log" "$EXPERIMENT_DIR/server_log_debug_${EXP_NAME}.log"
        echo "Debug log saved: server_log_debug_${EXP_NAME}.log"
    fi
fi

echo "=== Done: $EXP_SCRIPT ==="
