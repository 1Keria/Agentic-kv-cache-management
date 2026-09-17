#!/usr/bin/env bash
# 冻结混合负载重放（Session 内闭环）。产出格式对齐 replay_glm_online.sh。
#
# 先起服：
#   bash scripts/shell/v4flash.sh
#
# 正式跑（默认 LRU 压力负载；2h 内 6 个三类混合波次）：
#   bash scripts/shell/replay_mix_workload.sh
# dry-run：后面加 --dry-run
# 不 flush cache：后面加 --no-flush-cache
#
# 旧份：
#   bash scripts/shell/replay_mix_workload.sh --workload-dir workloads/mix_oh108_g208_r1450 --arrival uniform --arrival-horizon-s 7200
#   bash scripts/shell/replay_mix_workload.sh --workload-dir workloads/mix_oh100_g100_r2000 --arrival uniform --arrival-horizon-s 7200
#   bash scripts/shell/replay_mix_workload.sh --workload-dir workloads/mix_oh100_g100_r5000 --arrival uniform --arrival-horizon-s 7200
#   bash scripts/shell/replay_mix_workload.sh --workload-dir workloads/mix_a140_r560 --arrival staggered --delta-agent-s 10 --delta-request-s 3 --request-gap-cap-s 30
#   bash scripts/shell/replay_mix_workload.sh --workload-dir workloads/mix_oh20_glm_r8400 --arrival staggered --delta-agent-s 2 --delta-request-s 3 --request-gap-cap-s 30
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv

PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python

RUN_ID="${MIX_REPLAY_RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
OUT_PREFIX="run_mix_$RUN_ID"
RUN_ROOT="${MIX_REPLAY_RUN_ROOT:-experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs}"
RUN_DIR="$RUN_ROOT/$OUT_PREFIX"

if [[ -e "$RUN_DIR" ]]; then
  echo "实验目录已存在：$RUN_DIR；请更换 MIX_REPLAY_RUN_ID。" >&2
  exit 1
fi

mkdir -p "$RUN_DIR"

echo "[replay_mix] run_dir=$RUN_DIR （Session 闭环；replay.jsonl / summary.json / meta.json / report.md）"

exec "$PYTHON" scripts/python/replay_mix_workload.py \
  --base-url http://127.0.0.1:30000 \
  --workload-dir workloads/mix_lru_pressure_oh59_g100_r700 \
  --output-dir "$RUN_DIR" \
  --arrival waves \
  --arrival-horizon-s 7200 \
  --arrival-waves 6 \
  --arrival-wave-width-s 10 \
  --delta-agent-s 1 \
  --delta-request-s 1 \
  --request-gap-cap-s 30 \
  --mean-gap-agent-s 15 \
  --mean-gap-request-s 5 \
  --arrival-seed 42 \
  "$@"
