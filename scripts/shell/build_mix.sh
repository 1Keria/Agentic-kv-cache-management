#!/usr/bin/env bash
# LRU 压力负载、Agent/Request 调用约 50/50：
#   OpenHands 59（前 12 跳严格前缀）+ GLM 100（n>=6）+ WildChat 700（最多 8 跳）。
# 重放用 6 个混合波次制造活跃前缀竞争；旧 workload 不覆盖。
# 写出 workloads/mix_lru_pressure_oh59_g100_r700。
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv
PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python

exec "$PYTHON" scripts/python/build_mix_workload.py \
  --name mix_lru_pressure_oh59_g100_r700 \
  --out-dir workloads/mix_lru_pressure_oh59_g100_r700 \
  --n-openhands 59 \
  --min-openhands-prefix-turns 12 \
  --openhands-max-turns 12 \
  --n-glm 100 \
  --min-glm-turns 6 \
  --n-request 700 \
  --request-gap-cap-s 30 \
  --request-max-turns 8 \
  --delta-openhands-s 1 \
  --delta-glm-s 1 \
  --delta-request-s 1 \
  --seed 42 \
  "$@"
