#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV_ROOT="${AGENTKV_V4FLASH_VENV:-/inspire/hdd/project/inference-chip/czxs25240022/.venvs/agentkv-v4flash}"

if [[ ! -x "$VENV_ROOT/bin/python" ]]; then
  echo "V4 Flash 虚拟环境不存在：$VENV_ROOT" >&2
  exit 1
fi

export PYTHONPATH="$REPO_ROOT/Engine/sglang/python${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV_ROOT/bin/python" -c 'from sglang.cli.main import main; main()' "$@"
