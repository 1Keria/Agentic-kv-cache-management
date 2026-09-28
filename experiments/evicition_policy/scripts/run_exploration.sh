#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/runtime_env.sh"
umask 077
STAMP="$(date -u +%Y%m%dT%H%M%SZ)_$$"
LOG="$EXPERIMENT_ROOT/results/setup/exploration_${STAMP}.log"
exec "$PYTHON" -u "$EXPERIMENT_ROOT/scripts/run_exploration.py" "$@" > "$LOG" 2>&1
