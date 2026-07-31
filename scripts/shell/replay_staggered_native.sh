#!/usr/bin/env bash
# 全量 staggered 重放：lmcache_traces 全部 Session、全部轮次、按轨迹 output_length 生成。
# 先起服例如：
#   bash scripts/shell/start_sglang_qwen3_8b_vanilla.sh
#   bash scripts/shell/start_sglang_v4flash_vanilla.sh
#
# 规模：约 767 Session / ~25k 轮；delta_s=2 时末 Session 约在 25min 后才启动，总墙钟可能很多小时。
#
# 输出隔离（避免覆盖旧结果），任选：
#   OUT_DIR=... OUT_PREFIX=... bash scripts/shell/replay_staggered_native.sh
#   bash scripts/shell/replay_staggered_native.sh \
#     --output-dir experiments/sglang_kv_cache/staggered_native_replay/v4flash_vanilla \
#     --out-prefix run_v4flash_vanilla
#   # 或固定文件名：--output-name my_run.json
#   # 不更新 latest 软链：--no-latest
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv

PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python
# V4-Flash 默认 :30000；Qwen3-8B 用：BASE_URL=http://127.0.0.1:8004
BASE_URL="${BASE_URL:-http://127.0.0.1:30000}"
OUT_DIR="${OUT_DIR:-experiments/sglang_kv_cache/staggered_native_replay}"
OUT_PREFIX="${OUT_PREFIX:-run_staggered_full}"
UPDATE_LATEST="${UPDATE_LATEST:-1}"
TS=$(date +%Y%m%d_%H%M%S)
# OUT_NAME 若已通过环境变量给出则保留；否则用 prefix + 时间戳
OUT_NAME="${OUT_NAME:-${OUT_PREFIX}_${TS}.json}"

PASS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir|--out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --output-name|--out-name)
      OUT_NAME="$2"
      shift 2
      ;;
    --out-prefix|--output-prefix)
      OUT_PREFIX="$2"
      OUT_NAME="${OUT_PREFIX}_${TS}.json"
      shift 2
      ;;
    --no-latest)
      UPDATE_LATEST=0
      shift
      ;;
    --latest)
      UPDATE_LATEST=1
      shift
      ;;
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    *)
      PASS+=("$1")
      shift
      ;;
  esac
done

REPORT_NAME="${OUT_NAME%.json}_report.md"
mkdir -p "$OUT_DIR"

if [[ " ${PASS[*]} " == *" --dry-run "* ]]; then
  MODEL=dry-run
else
  MODEL=$(curl -sf "${BASE_URL}/v1/models" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])")
fi

"$PYTHON" scripts/python/replay_lmcache_staggered_native.py \
  --base-url "$BASE_URL" \
  --model "$MODEL" \
  --trace-dir experiments/vllm_kv_cache/lmcache_traces \
  --output-dir "$OUT_DIR" \
  --output-name "$OUT_NAME" \
  --all-sessions \
  --use-trace-output-length \
  --delta-s 2.0 \
  --gap-scale 1.0 \
  --flush-cache \
  "${PASS[@]+"${PASS[@]}"}"

if [[ "$UPDATE_LATEST" == "1" ]]; then
  ln -sfn "$OUT_NAME" "$OUT_DIR/latest.json"
  REPORT_INPUT="$OUT_DIR/latest.json"
else
  REPORT_INPUT="$OUT_DIR/$OUT_NAME"
fi

"$PYTHON" scripts/python/report_staggered_replay.py \
  --input "$REPORT_INPUT" \
  --output "$OUT_DIR/$REPORT_NAME"

if [[ "$UPDATE_LATEST" == "1" ]]; then
  ln -sfn "$REPORT_NAME" "$OUT_DIR/latest_report.md"
  echo "latest -> $OUT_DIR/latest.json"
  echo "report -> $OUT_DIR/latest_report.md"
else
  echo "json   -> $OUT_DIR/$OUT_NAME"
  echo "report -> $OUT_DIR/$REPORT_NAME"
fi
