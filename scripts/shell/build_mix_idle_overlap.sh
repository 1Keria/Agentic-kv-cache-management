#!/usr/bin/env bash
# 把 20 条长空档 OH 叠在开头 60s 内并发，轮间空档至少 180s，
# Request 仍 9 波打满 KV。不覆盖 mix_eval_idle_oh20_r1050。
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv
PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python

exec "$PYTHON" scripts/python/build_mix_idle_prefix.py \
  --parent workloads/mix_eval_longgap_oh59_g150_r1050 \
  --out-dir workloads/mix_eval_idle_oh20_r1050_overlap \
  --burst-gap-s 10 \
  --min-idle-s 60 \
  --idle-floor-s 180 \
  --oh-start-window-s 60 \
  --n-request 1050 \
  --horizon-s 10800 \
  --arrival-waves 9 \
  --seed 42 \
  "$@"
