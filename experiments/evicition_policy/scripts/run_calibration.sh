#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/runtime_env.sh"
umask 077
STAMP="$(date -u +%Y%m%dT%H%M%SZ)_$$"
LOG="$EXPERIMENT_ROOT/results/setup/calibration_high_${STAMP}.log"
REPORT="$EXPERIMENT_ROOT/results/analysis/calibration_high_${STAMP}.json"
mkdir -p "$EXPERIMENT_ROOT/results/setup" "$EXPERIMENT_ROOT/results/analysis"
set +e
bash "$EXPERIMENT_ROOT/scripts/run_suite.sh" \
  --config "$EXPERIMENT_ROOT/configs/calibration_high_server.json" \
  --workload "$EXPERIMENT_ROOT/data/workloads/calibration_coverage8_v2/manifest.json" \
  --policies lru 2>&1 | tee "$LOG"
RUN_STATUS=${PIPESTATUS[0]}
"$PYTHON" "$EXPERIMENT_ROOT/scripts/analyze_calibration.py" --controller-log "$LOG" --output "$REPORT"
ANALYSIS_STATUS=$?
set -e
printf 'Run exit=%s analysis exit=%s log=%s report=%s\n' "$RUN_STATUS" "$ANALYSIS_STATUS" "$LOG" "$REPORT"
if [[ "$RUN_STATUS" != 0 ]]; then
  exit "$RUN_STATUS"
fi
exit "$ANALYSIS_STATUS"
