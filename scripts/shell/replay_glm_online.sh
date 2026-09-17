#!/usr/bin/env bash
# GLM 线上数据开环重放（对齐 third_party/trace-replayer）
#
# 先起服：
#   bash scripts/shell/glm51_node0.sh   # 或对应起服脚本
#
# 正式跑：
#   bash scripts/shell/replay_glm_online.sh
# dry-run（只算调度、不打模型）：把下面 DRY_RUN=1
#
# 每轮输出到独立子目录：
#   experiments/.../v4flash_vanilla/openloop_runs/run_glm_openloop_<timestamp>/
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv

PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python

# ---------- 参数（与 trace-replayer 对齐）----------
BASE_URL=http://127.0.0.1:30000
DATASET=third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl
OUT_DIR=experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla

SCALE_FACTOR=0.02    # --scale-factor：>1 加速
TIME_IN_SECS=3600   # --time-in-secs：墙钟秒数到点停发
DRY_RUN=0           # 1=只算调度不发请求

RUN_ID="${OPENLOOP_REPLAY_RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
OUT_PREFIX="run_glm_openloop_$RUN_ID"
RUNS_DIR="$OUT_DIR/openloop_runs"
RUN_DIR="$RUNS_DIR/$OUT_PREFIX"

if [[ -e "$RUN_DIR" ]]; then
  echo "实验目录已存在：$RUN_DIR；请更换 OPENLOOP_REPLAY_RUN_ID。" >&2
  exit 1
fi

mkdir -p "$RUN_DIR"

ARGS=(
  --base-url "$BASE_URL"
  --dataset "$DATASET"
  --output-dir "$RUN_DIR"
  --out-prefix "$OUT_PREFIX"
  --scale-factor "$SCALE_FACTOR"
  --time-in-secs "$TIME_IN_SECS"
  --max-tokens-slack 0
)
if [[ "$DRY_RUN" == "1" ]]; then
  ARGS+=(--dry-run)
fi

echo "[replay_glm_online] base_url=$BASE_URL scale=$SCALE_FACTOR t=${TIME_IN_SECS}s dry_run=$DRY_RUN"
echo "[replay_glm_online] run_dir=$RUN_DIR prefix=$OUT_PREFIX （从文件头按 start_time 开环发，不限 inflight）"

exec "$PYTHON" scripts/python/replay_glm_online_openloop.py "${ARGS[@]}" "$@"
