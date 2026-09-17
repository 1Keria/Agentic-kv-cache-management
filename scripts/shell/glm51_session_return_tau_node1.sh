#!/usr/bin/env bash
# 与 glm51_session_return_tau_node0.sh 配套。主节点起好后再跑。
set -euo pipefail
REPO="/share/dai-sys/zhoulongsheng/agentkv"
export SESSION_RETURN_OUT_ROOT="${SESSION_RETURN_OUT_ROOT:-$REPO/experiments/session_return/replay_small_tau}"
export SESSION_RETURN_TAU_CKPT="${SESSION_RETURN_TAU_CKPT:-$REPO/experiments/session_return/k8_model/k8_hazard.pt}"
export RADIX_EVICTION_POLICY="${RADIX_EVICTION_POLICY:-lru}"
exec "$REPO/scripts/shell/glm51_session_return_node1.sh"
