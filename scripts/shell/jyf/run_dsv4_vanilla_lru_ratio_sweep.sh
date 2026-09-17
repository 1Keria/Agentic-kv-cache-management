#!/usr/bin/env bash
#
# dsv4_vanilla_lru LRU 基线 ratio sweep —— 最终集成重放脚本
#
# 职责: 只负责顺序跑 11 组 replay(workloads/ratio_sweep_v4flash_unseen/agent_000..agent_100,
#        --arrival frozen),每组独立输出目录。不负责起/停 server。
#
# 前置: LRU server 已在 $BASE_URL 上就绪 —— 用同目录 dsv4_vanilla_lru_server.sh 起
#        (官方 sglang 0.5.13, env agentkv_jyf, --radix-eviction-policy lru),并 curl /health。
#
# 目录: 默认自建 <repo>/experiments/sglang_kv_cache/dsv4_vanilla_lru/run_ratio_$(date +%Y%m%d_%H%M%S)/
#       及 11 个比例子目录(与 workload 目录同名 agent_000..agent_100);
#        也可用 RUN_RATIO_ROOT=<已存在的 run_ratio_xx> 指定根目录。
# 断点续跑: 某比例子目录已含 summary.json ⇒ 自动跳过。
#
# 用法:
#   bash scripts/shell/jyf/run_dsv4_vanilla_lru_ratio_sweep.sh
#   RUN_RATIO_ROOT=$PWD/experiments/sglang_kv_cache/dsv4_vanilla_lru/run_ratio_20260907_113000 \
#     bash scripts/shell/jyf/run_dsv4_vanilla_lru_ratio_sweep.sh
#
# 可覆盖变量: BASE_URL / REPLAY_PY / RUN_RATIO_ROOT
set -uo pipefail

BASE=/share/dai-sys/zhoulongsheng/agentkv
WORK_BASE="$BASE/workloads/ratio_sweep_v4flash_unseen"
OUT_BASE="$BASE/experiments/sglang_kv_cache/dsv4_vanilla_lru"
REPLAY_PY="${REPLAY_PY:-/share/dai-sys/apps/anaconda3/envs/agentkv_jyf/bin/python}"
REPLAY="$BASE/scripts/python/replay_mix_workload.py"
BASE_URL="${BASE_URL:-http://127.0.0.1:30000}"

RUN_ROOT="${RUN_RATIO_ROOT:-$OUT_BASE/run_ratio_$(date +%Y%m%d_%H%M%S)}"

RATIOS=(agent_000 agent_010 agent_020 agent_030 agent_040 agent_050 agent_060 agent_070 agent_080 agent_090 agent_100)

mkdir -p "$RUN_ROOT"

# 根目录说明(已存在则不覆盖)
README="$RUN_ROOT/README.md"
if [[ ! -f "$README" ]]; then
  cat > "$README" <<'EOF'
# dsv4_vanilla_lru LRU 基线(官方 sglang 0.5.13 / env agentkv_jyf)

本目录为 ratio_sweep_v4flash_unseen(agentic 比例 0→1, 共 11 组)的 **LRU 基线**结果。
每个 agent_XXX 子目录对应用户对比实验里同一组 workload(agentic 比例 = agent_XXX/100)。

每组子目录产物:
- replay.jsonl  逐请求明细
- summary.json  聚合指标(对比报告主要读它)
- report.md     人类可读报告
- meta.json     运行元信息(workload / arrival / wall_clock_s 等)
- replay.log    本次重放 stdout/stderr

对比参照:用户 agentic(mlp) 样本见
experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_ratio000_mlp/
EOF
fi

echo "==> RUN_ROOT = $RUN_ROOT"
echo "==> server  = $BASE_URL  (运行前请确认 /health 就绪)"
echo "==> ratios  = ${RATIOS[*]}"
echo

done_s=(); skip_s=(); fail_s=()
for r in "${RATIOS[@]}"; do
  workdir="$WORK_BASE/$r"
  outdir="$RUN_ROOT/$r"

  if [[ ! -d "$workdir" ]]; then
    echo "[warn] 缺少 workload 目录 $workdir,跳过 $r"
    continue
  fi
  mkdir -p "$outdir"

  if [[ -f "$outdir/summary.json" ]]; then
    echo "[skip] $r 已存在 summary.json → 跳过(断点续跑)"
    skip_s+=("$r")
    continue
  fi

  if ! curl -fsS -m 8 "$BASE_URL/health" >/dev/null 2>&1; then
    echo "[abort] server 不在线: $BASE_URL/health —— 请先起 LRU server。中止。"
    exit 2
  fi

  echo "==> [$r] $(date '+%F %T') 开始 replay: workload=$workdir → out=$outdir"
  start_t=$(date +%s)
  #? frozen情况下不需要其他的参数
  if "$REPLAY_PY" "$REPLAY" \
       --base-url "$BASE_URL" \
       --workload-dir "$workdir" \
       --output-dir "$outdir" \
       --arrival frozen \
       2>&1 | tee "$outdir/replay.log"; then
    if [[ -f "$outdir/summary.json" ]]; then
      echo "<== [$r] $(date '+%F %T') 完成 ($(( $(date +%s) - start_t ))s)"
      done_s+=("$r")
    else
      echo "<== [$r] 退出码 0 但缺 summary.json → 按失败计"
      fail_s+=("$r")
    fi
  else
    echo "<== [$r] $(date '+%F %T') 失败(见 $outdir/replay.log)"
    fail_s+=("$r")
  fi
done

echo
echo "================ 汇总 ================"
echo "RUN_ROOT : $RUN_ROOT"
echo "server   : $BASE_URL"
echo "完成     : ${done_s[*]:-无}"
echo "跳过     : ${skip_s[*]:-无}"
echo "失败     : ${fail_s[*]:-无}"
echo "======================================"

[[ ${#fail_s[@]} -eq 0 ]]
