#!/usr/bin/env bash
set -Eeuo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/async_exp
PY=/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/python
RUN="runs/${1:-$(date +%Y%m%d_%H%M%S)}"
if [[ -e "$RUN" ]]; then
  echo "Refusing to overwrite existing run: $RUN" >&2
  exit 2
fi
mkdir -p "$RUN"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
"$PY" -m unittest -v test_predictor >"$RUN/tests.log" 2>&1
"$PY" run_experiment.py --output "$RUN" >"$RUN/timing.log" 2>&1
"$PY" additional_experiment.py --run "$RUN" >"$RUN/additional.log" 2>&1
"$PY" build_report.py --run "$RUN"
