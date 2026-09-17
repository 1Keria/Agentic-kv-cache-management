# Feature experiments 文件说明

本目录用于研究 eviction frontier 上哪些 server-visible 特征能够预测 prefix 的下一次复用。目录中保留了两类目标：早期的 cache-access event distance，以及与最终 Hazard MLP 对齐的 wall-clock seconds。新的实验应优先引用秒级结果。

## 根目录文件

### `frontier_time_feature_ablation.py`

当前主实验脚本。读取真实 SGLang frontier trace，用 `wall_s` 构造从 eviction frontier 到下一次 demand 的秒级右删失标签，训练 K=10 Unified Hazard MLP，并执行固定输入宽度的特征消融。

默认包含完整基线、event/seconds 对照、family/LRU/size 单组基线、逐项加回和逐项删除实验。可用 `--feature-sets` 只运行指定组。

### `time_hazard_conclusion_zh.md`

秒级实验的中文结论。包含实验定义、最强候选、主要指标、逐特征证据、实现建议和结果边界。这是当前应优先阅读和引用的结论文档。

### `frontier_feature_ablation.py`

早期真实 frontier 实验脚本。预测未来 5/20/100 个 cache-access event 内是否复用。它用于研究 event-distance，不是秒级 Hazard MLP 的最终验证。

### `frontier_ablation_conclusion_zh.md`

event-distance frontier 实验的中文结论。它仍可用于对照 event-space 信号，但其中的 feature 排名不能直接替代秒级结果。

### `run_feature_ablation.py`

最早的逻辑 message-boundary prefix 实验。它从原始 API 请求离线重建逻辑前缀，对 history、Radix shape、token size 和 tools 信息做组级消融。它没有使用真实 SGLang eviction frontier。

### `conclusion_zh.md`

逻辑 prefix 实验的中文总结。主要用途是记录早期假设和说明为什么后来改用真实 frontier trace。

## `runs/` 目录

### `20260912_frontier_time_hazard_v1/`

秒级主实验，21 组特征、10 个 seed。包含 event-only、seconds-only、combined、原始 16 维和主要组级消融。

### `20260912_frontier_time_hazard_event_detail_v1/`

秒级追加实验，10 组、10 个 seed。拆解 event-history 在 seconds-history 之外的增量，主要比较 `age_events`、`idle_events` 和 event-gap 统计。

### `20260912_frontier_time_hazard_individual_v1/`

秒级逐特征删除实验，13 组、10 个 seed。以 combined 16 维为基线，分别删除秒级历史、event-gap、hits、size、LRU 和 traffic。

### `20260912_frontier_ablation_v4_final/`

event-distance 实验的最终固定宽度 10-seed 版本。需要查看旧的 5/20/100 event 结果时使用。

### `20260912_frontier_ablation_v1/`

真实 frontier 的初始试验版本。仅保留用于复现实验演进，不作为结论来源。

### `20260912_frontier_ablation_v2_10seed/`

早期 10-seed event 版本。网络输入宽度会随特征组变化，可能混入初始化差异，不作为结论来源。

### `20260912_frontier_ablation_v3_fixedwidth_10seed/`

固定输入宽度后的中间 event 版本。最终修订由 `v4_final` 取代。

### `20260912_v1/`

逻辑 message-boundary prefix 的离线实验输出，对应 `run_feature_ablation.py`。

## 每个 run 中的文件

- `report.md`：人可读指标表，通常分为 all/cold/warm 三个测试子集。
- `results.json`：完整机器可读结果，包含 feature set、每个 seed 的验证结果、ensemble 指标、trace 和数据元信息。
- `run.log`：正式训练日志。早期 run 可能没有保存日志。
- `feature_samples.npz`：只有逻辑 prefix 实验保存的预处理样本。
- `feature_samples.meta.json`：逻辑 prefix 样本的数据量、字段和切分元信息。

## 指标含义

- `censor NLL`：完整离散 hazard likelihood，能够利用右删失样本，是秒级实验的主预测指标，越低越好。
- `AUC@5s/20s/60s`：在对应秒数内会复用的 prefix 是否排在不会复用的 prefix 前面，越高越好。
- `NLL@5s/20s/60s`：对应累计复用概率的 Bernoulli NLL，越低越好。
- cold/warm 表格只是同一个 Unified 模型的子集诊断，不表示训练了两个模型。

## 当前引用顺序

1. 秒级结论：`time_hazard_conclusion_zh.md`
2. 秒级完整结果：三个 `frontier_time_hazard_*` run
3. event-distance 对照：`frontier_ablation_conclusion_zh.md` 和 `v4_final`
4. 逻辑 prefix 早期实验：`conclusion_zh.md` 和 `20260912_v1`

## Absolute vs Relative 时间表示实验

见 bsolute_vs_relative/README.md（复现）和 bsolute_vs_relative/conclusion_zh.md（ID/OOD 与跨 session 排序结论）。正式结果位于 bsolute_vs_relative/runs/20260915_v1/。
