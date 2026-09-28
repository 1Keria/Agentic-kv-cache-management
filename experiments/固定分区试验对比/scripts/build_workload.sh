#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PYTHON="${PARTITION_WORKLOAD_PYTHON:-${PYTHON:-python}}"

cd "$REPO_ROOT"
exec "$PYTHON" experiments/固定分区试验对比/scripts/build_workload.py "$@"
