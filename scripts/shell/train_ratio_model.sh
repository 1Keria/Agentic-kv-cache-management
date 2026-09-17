#!/usr/bin/env bash
set -euo pipefail

# Build node-level samples and final-fit one ratio-specific MLP.
#
# Usage:
#   bash scripts/shell/train_ratio_model.sh agent_050
#
# Optional:
#   PYTHON=/path/to/python DEVICE=cpu EPOCHS=5 BATCH_SIZE=8192 \
#     bash scripts/shell/train_ratio_model.sh agent_050

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python}"
DEVICE="${DEVICE:-cpu}"
EPOCHS="${EPOCHS:-5}"
BATCH_SIZE="${BATCH_SIZE:-8192}"
RATIO="${1:-}"

if [[ ! "$RATIO" =~ ^agent_(000|010|020|030|040|050|060|070|080|090|100)$ ]]; then
  echo "用法：bash scripts/shell/train_ratio_model.sh agent_000|...|agent_100" >&2
  exit 2
fi

WORKLOAD_DIR="$REPO_ROOT/workloads/ratio_train_v4flash/$RATIO"
RUN_DIR="$REPO_ROOT/experiments/sglang_kv_cache/ratio_daily_models/$RATIO"
REPLAY_DIR="$RUN_DIR/replay/run_mix_train_lru"
SAMPLES_DIR="$RUN_DIR/samples"
CHECKPOINT_DIR="$RUN_DIR/checkpoint"

if [[ ! -f "$REPLAY_DIR/replay.jsonl" || ! -f "$REPLAY_DIR/summary.json" ]]; then
  echo "缺少完整训练重放：$REPLAY_DIR" >&2
  exit 1
fi
if [[ -e "$CHECKPOINT_DIR/leaf_mlp.pt" && "${FORCE:-0}" != "1" ]]; then
  echo "checkpoint 已存在；如需覆盖请设置 FORCE=1：$CHECKPOINT_DIR/leaf_mlp.pt" >&2
  exit 1
fi

mkdir -p "$SAMPLES_DIR" "$CHECKPOINT_DIR"

"$PYTHON" models/MLP/src/build_samples.py \
  --workload "$WORKLOAD_DIR/workload.jsonl" \
  --replay "$REPLAY_DIR/replay.jsonl" \
  --out-dir "$SAMPLES_DIR" \
  --all-train \
  2>&1 | tee "$SAMPLES_DIR/build_samples.log"

"$PYTHON" models/MLP/src/train_mlp.py \
  --train "$SAMPLES_DIR/samples_train.jsonl.gz" \
  --out-dir "$CHECKPOINT_DIR" \
  --epochs "$EPOCHS" \
  --batch-size "$BATCH_SIZE" \
  --device "$DEVICE" \
  --final-fit \
  2>&1 | tee "$CHECKPOINT_DIR/train.log"

echo "[done] $RATIO checkpoint: $CHECKPOINT_DIR/leaf_mlp.pt"
