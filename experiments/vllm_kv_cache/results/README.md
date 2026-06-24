# AgentKV vLLM KV Cache 实验结果总览

> 日期: 2026-06-23 (更新) | 实验数据: 2026-06-17 | 模型: Qwen3-8B | GPU: NVIDIA H800 | vLLM: 0.8.5.dev0

## 目录结构

```
results/
├── README.md                    ← 本文件
├── key_findings.md              ← 核心发现摘要（6 条，可直接用于论文 Motivation）
├── analysis.md                  ← 完整分析报告
├── figures/
│   ├── simulated/               ← 模拟层图表 [SIMULATED]
│   │   ├── hit_rate_vs_capacity.pdf/png    — 7 个 trace 的命中率 vs 容量曲线
│   │   └── agent_vs_nonagent_compare.pdf/png — Agent vs 非 Agent 对比
│   └── measured/                ← 验证层图表 [MEASURED]
│       ├── exp1_prefix_hit_ttft.pdf/png    — Prefix cache 命中率与 TTFT 降低
│       ├── exp3_offload_compare.pdf/png    — Offloading 对比
│       ├── exp4_l0_l1_l2_reuse.pdf/png     — L0/L1/L2 层次复用
│       ├── exp5_aware_eviction.pdf/png      — Agent-aware vs LRU 驱逐
│       └── exp6_preemption_compare.pdf/png  — Preemption 策略对比
├── tables/                      ← LaTeX 表格
└── simulated_summary.json       ← 模拟层汇总数据
```

## 数据来源标注

| 标签 | 含义 | 使用位置 |
|------|------|---------|
| `[MEASURED]` | vLLM 实际运行测量 | 验证层图表 (figures/measured/) |
| `[SIMULATED]` | 基于 trace hash 的模拟 | 模拟层图表 (figures/simulated/) |
| `[TRACE-ANALYSIS]` | 对已有 trace 的分析统计 | key_findings.md 中 LMCache traces 统计 |
| `[SYNTHETIC]` | 人为构造但基于真实组件 | 未使用（实验全部使用真实 L0/L1） |

## 实验数据完整性

| 实验 | 状态 | 数据文件 | 关键结果 |
|------|------|---------|---------|
| exp1 Prefix Hit | ✅ | run_1.json | TTFT ↓90.9%, hit=79.6% |
| exp2 Block Granularity | ✅ | run_1.json | waste 精确匹配 block_size=16 |
| exp3 Offload ON | ✅ | run_1.json | req_C cached=6160, TTFT=53.8ms |
| exp3 Offload OFF | ✅ | run_1.json | req_C cached=6160, TTFT=53.8ms |
| exp4.1 Same Session | ✅ | run_1_4.1.json | S1-T2 hit=87.4% |
| exp4.2 Same Project | ✅ | run_1_4.2.json | S2-T1 hit=94.4% |
| exp4.3 Cross Project | ⚠️ | 需重跑 | S3-T1 hit=89.3% (之前有数据) |
| exp4.4 Concurrent | ⚠️ | 需重跑 | S_B hit=0% (之前有数据) |
| exp4.5 ON | ⚠️ | 需重跑 | recovery=99.9% (之前有数据) |
| exp4.5 OFF | ⚠️ | 需重跑 | recovery=99.9% (之前有数据) |
| exp4.6 ON | ⚠️ | 需重跑 | CPU recovery=0.18x cold (之前有数据) |
| exp4.6 OFF | ⚠️ | 需重跑 | full recompute=0.13x cold (之前有数据) |
| exp5 LRU | ✅ | run_1.json | sqlfluff_T2 hit=99.9% |
| exp5 Aware | ✅ | run_1.json | sqlfluff_T2 hit=99.9% |
| exp6 Swap | ✅ | run_1.json | recovery hit=99.9%, TTFT=44.7ms |
| exp6 Recompute | ✅ | run_1.json | recovery hit=99.9%, TTFT=39.3ms |
| exp6 Default | ✅ | run_1.json | recovery hit=99.9%, TTFT=40.7ms |

⚠️ 标记的实验数据在之前运行中已收集（终端输出可见），但因 exp4 文件覆盖问题需要重跑保存。

## 已知限制

1. **GPU KV 容量充足，未触发真正驱逐**：gpu_memory_utilization=0.3 在 H800 上提供 ~44K tokens 容量，当前测试请求总量不足。后续需降低利用率或增加请求量。
2. **exp4 子场景 4.3-4.6 的 JSON 文件需重跑**：因 save_run 文件名覆盖问题已修复（添加 suffix），需重跑保存。
3. **并发请求无法利用 APC 缓存**：这是 vLLM APC 的设计限制，非 bug。需要"提前注册"机制解决。
