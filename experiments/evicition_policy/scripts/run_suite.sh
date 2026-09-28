#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/runtime_env.sh"
exec "$PYTHON" "$EXPERIMENT_ROOT/scripts/run_suite.py" "$@"
