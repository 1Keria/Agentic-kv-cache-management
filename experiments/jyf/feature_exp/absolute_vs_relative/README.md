# Absolute vs Relative 时间表示实验

先读 `conclusion_zh.md`，其中记录主假设、实际数据过滤、两种模型、所有指标与局限。

工作目录：`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/feature_exp/absolute_vs_relative`。

复现命令（在本目录运行）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python run_experiment.py \
  --base ../frontier_time_feature_ablation.py \
  --trace ../../nn_exp/cold_predictor_exp/runs/20260911_cold_frontier_agent050_frozen_v1/frontier_trace/frontier_pid3797866_140187773175760.jsonl \
  --out runs/20260915_v1 --device cuda:0 --epochs 180
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python write_report.py
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python support_check.py
```

`--base` 加载已有 16 维特征构造、HazardNet 和 hazard loss。请求记录按 `(sid, turn)` 去重形成 session gap；测试未来记录仅用于标签和排除共享 prefix，不用于 τ。无历史 owner demand 的 prefix 被排除，不能将未来所属 session 当作当前已知信息。

运行配置固定在脚本中：K=8，训练 session 25%/100%，seed 41–45，ID/×5/×10/mixed，IBS 区间 0–600s，bootstrap 500 次。修改这些值后应写入新的 run 目录。

主实验使用一个 Unified 模型，两个分支仅指 Absolute 与 Relative 两种表示。每个分支内部均无 cold/warm 独立 head。

`support_check.py` 从保存的预测计算 0–120 秒共同有限支持区间敏感性分析，写入 `common_support.json` 并追加报告。先运行 `write_report.py` 再运行它，避免重复追加。`manifest.json` 保存主脚本、特征依赖和 trace 的 SHA256、运行库版本及隔离检查。
