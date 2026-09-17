#!/usr/bin/env bash
# 6 条 OH 铺在 15min，Request 错开 180s，180s 轮间空档。
# 对齐 overlap serving 的 C≈44373：离线 Belady 相对 LRU 约 +50%。
# 不覆盖 overlap / idle v1。
set -euo pipefail
cd /share/dai-sys/zhoulongsheng/agentkv
PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python

exec "$PYTHON" scripts/python/build_mix_idle_prefix.py \
  --parent workloads/mix_eval_longgap_oh59_g150_r1050 \
  --out-dir workloads/mix_eval_idle_oh6_r1050_spread \
  --burst-gap-s 10 \
  --min-idle-s 60 \
  --idle-floor-s 180 \
  --n-openhands 6 \
  --oh-start-window-s 900 \
  --request-start-offset-s 180 \
  --n-request 1050 \
  --horizon-s 10800 \
  --arrival-waves 9 \
  --seed 42 \
  "$@"
