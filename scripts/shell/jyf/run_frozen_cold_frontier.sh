#!/usr/bin/env bash
set -Eeuo pipefail

BASE=/share/dai-sys/zhoulongsheng/agentkv
EXP="$BASE/experiments/jyf/nn_exp/cold_predictor_exp"
PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/python
RUN_TAG=${RUN_TAG:-$(date +%Y%m%d_cold_frontier_agent050_frozen)}
RUN="$EXP/runs/$RUN_TAG"

COLD_ARRIVAL_MODE=frozen COLD_GAP_SCALE=1 RUN_TAG="$RUN_TAG" \
  bash "$BASE/scripts/shell/jyf/run_cold_frontier_collection.sh"

mkdir -p "$RUN/analysis"
"$PYTHON" "$BASE/scripts/shell/jyf/analyze_cold_frontier.py" \
  --trace-dir "$RUN/frontier_trace" --out-dir "$RUN/analysis"
ln -sfn "$RUN" "$EXP/latest_frozen"
