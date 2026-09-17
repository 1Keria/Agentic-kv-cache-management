# node_level_ablation_v1 结果说明

运行目录：runs/node_level_ablation_v1

## 主结果

所有结果使用同一 node-level 数据和 session split；标签为 session-relative next node demand time；无 eviction。

| 输入组 | IBS | AUC@1tau | AUC@2tau | AUC@4tau |
|---|---:|---:|---:|---:|
| full18 | 0.23005 | 0.7047 | 0.7711 | 0.7875 |
| Old-10 | 0.27730 | 0.5651 | 0.6782 | 0.7224 |
| Candidate-8 | 0.33547 | 0.5275 | 0.5153 | 0.5078 |

full18 同时包含 Old-10 和 Candidate-8。当前结果说明，在同一个 node-level ideal-session 数据集上，旧的 node/time/history 特征比当前 8 个 context/history 特征更有效；Candidate-8 单独使用时接近弱基线。

## 分组消融（从 full18 删除一组）

| 删除组 | IBS | AUC@1tau | AUC@2tau | AUC@4tau |
|---|---:|---:|---:|---:|
| old_structure | 0.26135 | 0.6799 | 0.6388 | 0.6454 |
| old_node_time | 0.26312 | 0.6920 | 0.8086 | 0.7946 |
| old_history | 0.23007 | 0.7107 | 0.8168 | 0.8197 |
| old_workload | 0.26539 | 0.6961 | 0.6823 | 0.6933 |
| candidate_context | 0.27688 | 0.6708 | 0.6378 | 0.6634 |
| candidate_history | 0.27573 | 0.5791 | 0.7497 | 0.7804 |
| candidate_position | 0.26399 | 0.6926 | 0.6835 | 0.6902 |

分组结果使用单个 seed，主要用于筛选方向；最终结论应以多 seed 重跑为准。

## 训练集相关性

与相对 next-demand duration 的 Spearman 相关绝对值最高的是：

- idle_seconds: -0.2069
- recent_gap_seconds: -0.2069
- gap_ewma_seconds: -0.2033
- age_seconds: -0.1399
- node_tokens: -0.0804
- hits: +0.0540
- prefix_reuse_rate8: +0.0526

与“在 1 tau 内复用”的 event indicator 相关性最高的是：

- hits: +0.1472
- prefix_reuse_rate8: +0.1449
- last_message_is_tool: +0.1301
- creation_turn_fraction: -0.1259
- prefix_turn_gap_last: +0.1168
- gap_present: +0.1164

## 必须修正/记录的数据事实

1. 当前构造中，node demand 时的 idle_seconds 等于当前 demand 与该 node 上次 demand 的间隔，因此它和 recent_gap_seconds 是同一信息，不能作为两个独立特征。
2. 输入数据没有 workload metadata，is_agent 恒为 0；它没有可测的预测贡献，应在正式比较中标记为 unavailable 或删除。
3. path_tokens 目前采用累计 message-size 近似，因为原始输入没有 tokenizer tokenization；它不是 serving tokenizer 的精确 token 数。
4. Candidate-8 的相对历史特征只有在 session tau 可用时保留，因此结果样本数为 216,874，而原始 node dataset 有更多首请求/未知 tau 样本。

## 文件

- correlations.json: 全部 18 维的 Spearman 矩阵和目标相关性
- ablation_results.json: full18、Old-10、Candidate-8、分组删除和逐特征删除
- report.md: 指标摘要

