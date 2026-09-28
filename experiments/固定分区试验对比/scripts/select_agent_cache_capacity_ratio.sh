#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV_ROOT="${AGENTKV_V4FLASH_VENV:-/inspire/hdd/project/inference-chip/czxs25240022/.venvs/agentkv-v4flash}"
PYTHON="${PARTITION_EXPERIMENT_PYTHON:-$VENV_ROOT/bin/python}"

if [[ ! -x "$PYTHON" ]]; then
  echo "比例选择 Python 不可执行：$PYTHON" >&2
  exit 1
fi

cd "$REPO_ROOT"
exec "$PYTHON" \
  experiments/固定分区试验对比/scripts/select_agent_cache_capacity_ratio.py \
  "$@"
