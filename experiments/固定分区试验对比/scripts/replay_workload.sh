#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EXPERIMENT_ROOT="$REPO_ROOT/experiments/固定分区试验对比"

export MIX_REPLAY_RUN_ROOT="${MIX_REPLAY_RUN_ROOT:-$EXPERIMENT_ROOT/results/replays}"

cd "$REPO_ROOT"
exec bash scripts/shell/replay_mix_workload.sh \
  --workload-dir experiments/固定分区试验对比/data/token_balanced_openhands_wildchat \
  --arrival frozen \
  --fixed-output-tokens \
  "$@"
