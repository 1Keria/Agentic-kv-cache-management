# 下次前缀复用时间：server 可见特征消融

## 结论

第一版模型建议只保留两类特征：

1. 前缀的在线复用历史统计；
2. API `tools` 的规模信息，并把 tool 名称集合编码作为可选增强项。

Radix tree 的静态形状在这份数据上没有可用的独立预测信号。`child_count` 和 `is_leaf` 的 AUC 约为 0.501；加入 token 深度和节点 token 数后，NLL 相对无特征基线只改善 0.001。现阶段没有理由为这些树特征增加线上状态或模型输入。

## 实验设置

- 数据：`glm-5dot1_onlinedata_lt32k.jsonl`，16,559 个请求。
- 样本：按 message 边界重建 exact logical prefix，共 373,228 个前缀观测。
- 主实验只评估至少有一次历史复用的 warm prefix，共 162,509 个样本。
- 训练/验证/测试按 conversation anchor 做 70/15/15 哈希切分，同一 conversation 的 prefix 不会跨集合。
- 测试集 22,311 个样本，其中 9,886 个在 trace 结束前观察到下一次复用。
- 标签：当前 request start 到下一次包含同一 exact prefix 的 request start。
- 每个 prefix 的最后一次观测按 trace 结束时间做右删失。
- 模型：相同的两层 64-hidden ReLU 离散 hazard MLP，3 个随机种子。
- 指标：离散生存 NLL、5/20/60/180 秒 Brier、相应时间窗内复用的 AUC。

所有输入只来自当前请求结束时 server 已知的信息。实验没有使用 response 内容、tool call 结果、agent 内部状态或系统 pressure。

## 关键结果

| 特征 | NLL ↓ | Mean Brier ↓ | AUC@5s ↑ | AUC@20s ↑ | AUC@60s ↑ |
|---|---:|---:|---:|---:|---:|
| 无特征 population hazard | 1.5332 | 0.2211 | 0.5000 | 0.5000 | 0.5000 |
| 最近 8 次间隔序列 | 1.4586 | 0.2101 | 0.6912 | 0.6247 | 0.6118 |
| 历史统计 | 1.4508 | 0.2093 | 0.6989 | 0.6289 | 0.6138 |
| Radix token 信息 | 1.5302 | 0.2174 | 0.5465 | 0.5577 | 0.5636 |
| Radix shape | 1.5345 | 0.2212 | 0.5013 | 0.5012 | 0.5012 |
| 完整 Radix 特征 | 1.5321 | 0.2174 | 0.5508 | 0.5593 | 0.5656 |
| tool 数量 + schema 大小 | 1.5092 | 0.2138 | 0.6734 | 0.6006 | 0.6016 |
| tool 名称集合 | 1.5080 | 0.2080 | 0.6879 | 0.6222 | 0.6250 |
| 完整 tools | 1.5044 | 0.2083 | 0.6901 | 0.6249 | 0.6253 |
| 历史统计 + tool 数量/schema 大小 | 1.4251 | 0.2029 | 0.7470 | 0.6646 | 0.6593 |
| 历史统计 + tool 名称集合 | 1.4284 | 0.1958 | 0.7499 | 0.6853 | 0.6835 |
| 历史统计 + 完整 tools | 1.4289 | 0.1959 | 0.7452 | 0.6824 | 0.6800 |
| 所有特征 | 1.4228 | 0.1972 | 0.7409 | 0.6742 | 0.6765 |

历史统计单独将 NLL 从 1.5332 降到 1.4508，约改善 5.4%。因此，复用节奏确实包含下次复用时间的预测信号。直接输入最近 8 次间隔并没有优于压缩统计；把两者同时输入也没有继续改善，说明这两组信息高度重复。

`tools` 单独也有信号。规模信息和名称集合的 NLL 接近；名称集合在中长时间窗的 Brier 和 AUC 更好。与历史统计结合后，模型继续得到明显增益，说明 `tools` 并非只是在复制复用历史。

全特征模型获得最低 NLL，但只比“历史统计 + tool 数量/schema 大小”低 0.0023。考虑到 Radix 特征单独几乎无效，这个差异不足以支持在线加入 Radix shape。

## 推荐的第一版输入

核心 12 维输入：

- 最近最多 8 次 gap 的 `mean/std/min/max/EWMA`；
- `reuse_count`；
- 过去 5/20/60/300 秒的访问次数；
- `tool_count`；
- `tool_schema_bytes`。

所有计数和时间使用 `log1p`。这组输入的 NLL 为 1.4251，AUC@5s 为 0.7470，计算和维护成本都很低。

如果部署 workload 中 tool 集合稳定，可以再加入 32 维 signed feature hash of tool names。它将 mean Brier 从 0.2029 降至约 0.1959，并把 AUC@60s 从 0.6593 提升至约 0.6800。由于当前随机切分的训练和测试可能共享 tool 集合，这项收益尚不能证明它能泛化到全新的 agent/tool 配置。

暂不加入：

- `child_count`；
- `is_leaf`；
- prefix token 深度；
- node token 数。

## 结果边界

这次离线重建使用 message boundary 作为 logical Radix node，而真实 SGLang Radix tree 以 token/page 为粒度。历史间隔和 `tools` 的结论不依赖这个近似；树形状的结论只说明当前这组可重建的粗粒度 shape 没有信号。

当前切分验证了对未见 conversation 的泛化，还没有验证跨日期、跨 workload 或全新 tool 集合的泛化。下一轮若继续验证 tool identity，应采用 chronological split 和 leave-one-toolset-out；若两种切分下仍有增益，再把 tool-name hash 放入线上模型。
