#!/usr/bin/env bash
# 第一层 τ̂ 淘汰：整段 small 2200 重放，只在 test 段对比 LRU。
# 用法与采集相同：先本脚本，再 glm51_session_return_node1.sh（同样 export
# SESSION_RETURN_TAU_CKPT 和 SESSION_RETURN_OUT_ROOT），:30000 就绪后跑
# replay_glm_session_return_small.sh。
set -euo pipefail
REPO="/share/dai-sys/zhoulongsheng/agentkv"
export SESSION_RETURN_OUT_ROOT="${SESSION_RETURN_OUT_ROOT:-$REPO/experiments/session_return/replay_small_tau}"
export SESSION_RETURN_TAU_CKPT="${SESSION_RETURN_TAU_CKPT:-$REPO/experiments/session_return/k8_model/k8_hazard.pt}"
export RADIX_EVICTION_POLICY="${RADIX_EVICTION_POLICY:-lru}"
exec "$REPO/scripts/shell/glm51_session_return_node0.sh"
