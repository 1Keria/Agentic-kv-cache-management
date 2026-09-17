#!/usr/bin/env bash
# 分钟级空档评测夹具：OpenHands 保留完整严格前缀链（不截 12 跳），
# GLM / Request 仍做坑位压力。旧 mix_eval_3h 不覆盖。
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv
PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python

exec "$PYTHON" scripts/python/build_mix_workload.py \
  --name mix_eval_longgap_oh59_g150_r1050 \
  --out-dir workloads/mix_eval_longgap_oh59_g150_r1050 \
  --n-openhands 59 \
  --min-openhands-prefix-turns 12 \
  --n-glm 150 \
  --min-glm-turns 6 \
  --n-request 1050 \
  --request-gap-cap-s 30 \
  --request-max-turns 8 \
  --delta-openhands-s 1 \
  --delta-glm-s 1 \
  --delta-request-s 1 \
  --seed 42 \
  "$@"
