#!/usr/bin/env bash
set -Eeuo pipefail
BASE=/share/dai-sys/zhoulongsheng/agentkv
PY=/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/python
TRACE="$BASE/experiments/jyf/nn_exp/cold_predictor_exp/runs/20260911_cold_frontier_agent050_frozen_v1/frontier_trace"
exec "$PY" "$BASE/scripts/shell/jyf/compare_unified_shared_heads.py" \
  --trace-dir "$TRACE" \
  --unified-out "$BASE/experiments/jyf/nn_exp/unified_mlp" \
  --heads-out "$BASE/experiments/jyf/nn_exp/shared_and_heads"
