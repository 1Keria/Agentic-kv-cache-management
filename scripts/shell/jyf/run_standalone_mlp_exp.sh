#!/usr/bin/env bash
set -Eeuo pipefail

BASE=/share/dai-sys/zhoulongsheng/agentkv
PYTHON=${PYTHON:-/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/python}
SCRIPT="$BASE/scripts/shell/jyf/mlp_reuse_offline.py"
DATASET="$BASE/third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl"
EXP="$BASE/experiments/jyf/nn_exp/mlp_exp"
DATA="$EXP/data/prefix_reuse_samples.npz"
RUN_TAG=${RUN_TAG:-$(date +%Y%m%d_%H%M%S)}
RUN_DIR="$EXP/runs/$RUN_TAG"

mkdir -p "$EXP/data" "$RUN_DIR"
exec > >(tee "$RUN_DIR/run.log") 2>&1

if [[ ! -f "$DATA" ]]; then
  "$PYTHON" "$SCRIPT" build --dataset "$DATASET" --output "$DATA"
fi

"$PYTHON" "$SCRIPT" run \
  --data "$DATA" \
  --out-dir "$RUN_DIR" \
  --buckets k5 k10 k20 \
  --seeds 41 42 43 \
  --epochs 15 \
  --device cuda

ln -sfn "$RUN_DIR" "$EXP/latest"
printf 'DONE %s\n' "$(date '+%F %T')"
