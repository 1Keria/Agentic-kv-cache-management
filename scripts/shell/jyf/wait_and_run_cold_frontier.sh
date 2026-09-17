#!/usr/bin/env bash
set -Eeuo pipefail

BASE=/share/dai-sys/zhoulongsheng/agentkv
EXP="$BASE/experiments/jyf/nn_exp/cold_predictor_exp"
LOG="$EXP/resource_wait.log"
mkdir -p "$EXP"

while true; do
  port_busy=0
  ss -ltn | grep -q ':30000 ' && port_busy=1
  max_used=$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits 2>/dev/null | awk 'BEGIN{m=0} {if ($1>m)m=$1} END{print m}')
  max_used=${max_used:-0}
  if [[ $port_busy -eq 0 && $max_used -le 1024 ]]; then
    echo "[$(date '+%F %T')] resources free; launching collection" | tee -a "$LOG"
    RUN_TAG=${RUN_TAG:-$(date +%Y%m%d_cold_frontier_agent050_v2)} \
      bash "$BASE/scripts/shell/jyf/run_cold_frontier_collection.sh" | tee -a "$LOG"
    exit ${PIPESTATUS[0]}
  fi
  echo "[$(date '+%F %T')] waiting: port_busy=$port_busy max_compute_used_mib=$max_used" | tee -a "$LOG"
  sleep 60
done
