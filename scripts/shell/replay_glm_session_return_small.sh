#!/usr/bin/env bash
# 小型 GLM 压缩重放 + 原生字段采集（2200 条发完为止）
#
# 主节点先起 glm51_session_return_node0.sh，从节点起 node1.sh，
# :30000 就绪后直接跑本脚本。输出在
# experiments/session_return/replay_small/latest/
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv
# shellcheck source=/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/session_return_out.sh
source scripts/shell/session_return_out.sh
session_return_load_run

PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python
BASE_URL="${BASE_URL:-http://127.0.0.1:30000}"
mkdir -p "$RUN_DIR/client"

ARGS=(
  --base-url "$BASE_URL"
  --dataset third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl
  --split-dir experiments/session_return/splits/small
  --output-dir "$RUN_DIR/client"
  --out-prefix "small_2200"
  --max-inflight "${MAX_INFLIGHT:-2}"
)
if [[ -n "${TIME_IN_SECS:-}" ]]; then
  ARGS+=(--time-in-secs "$TIME_IN_SECS")
fi
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  ARGS+=(--dry-run)
fi

echo "[replay small native] run_dir=$RUN_DIR inflight=${MAX_INFLIGHT:-2} send-all"
exec "$PYTHON" scripts/python/replay_glm_session_return.py "${ARGS[@]}" "$@"
