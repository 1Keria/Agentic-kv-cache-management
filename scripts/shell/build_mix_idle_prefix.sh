#!/usr/bin/env bash
# 理想夹具：一种 Agent（OH），tool 环压成 round，只留分钟级空档 session；
# Request 当 KV 压力；不要 GLM。父负载是 mix_eval_longgap（不覆盖）。
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv
PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python

exec "$PYTHON" scripts/python/build_mix_idle_prefix.py \
  --parent workloads/mix_eval_longgap_oh59_g150_r1050 \
  --out-dir workloads/mix_eval_idle_oh20_r1050 \
  --burst-gap-s 10 \
  --min-idle-s 60 \
  --n-request 1050 \
  --horizon-s 10800 \
  --arrival-waves 9 \
  --seed 42 \
  "$@"
