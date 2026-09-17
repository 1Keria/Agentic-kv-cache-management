#!/usr/bin/env bash
# 把 splits/small 的 GLM jsonl 压缩重放到已就绪的 V4 Flash 采集服。
#
# 先起 v4flash_session_return.sh，:30000 /health 通过后再跑本脚本。
# 冒烟：MAX_EVENTS=200 bash scripts/shell/replay_glm_on_v4flash.sh
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv
# shellcheck source=/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/v4flash_session_return_out.sh
source scripts/shell/v4flash_session_return_out.sh
session_return_load_run

PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python
BASE_URL="${BASE_URL:-http://127.0.0.1:30000}"
mkdir -p "$RUN_DIR/client"

if ! curl -fsS -m 8 "$BASE_URL/health" >/dev/null; then
  echo "Flash 服务未就绪：$BASE_URL/health" >&2
  exit 1
fi

PREFIX="${OUT_PREFIX:-small_2200}"
if [[ -n "${MAX_EVENTS:-}" ]]; then
  PREFIX="smoke_${MAX_EVENTS}"
fi

ARGS=(
  --base-url "$BASE_URL"
  --dataset third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl
  --split-dir experiments/session_return/splits/small
  --output-dir "$RUN_DIR/client"
  --out-prefix "$PREFIX"
  --max-inflight "${MAX_INFLIGHT:-2}"
)
if [[ -n "${MAX_EVENTS:-}" ]]; then
  ARGS+=(--max-events "$MAX_EVENTS")
fi
if [[ "${NO_TOOLS:-0}" == "1" ]]; then
  ARGS+=(--no-tools)
fi

echo "[replay glm on v4flash] run_dir=$RUN_DIR inflight=${MAX_INFLIGHT:-2} max_events=${MAX_EVENTS:-all}"
exec "$PYTHON" scripts/python/replay_glm_session_return.py "${ARGS[@]}" "$@"
