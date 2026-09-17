# 秒级 Hazard MLP 训练结果

已在 H800-1 的 `experiments/evict_position/training/model.pt` 保存新训练的
Unified Hazard MLP。两种 serving 策略共享这一份模型，不使用不同模型比较推理时机。

- 特征：此前联合 16 维；沿用消融的固定 24 维输入，其余列标准化后置零。
- 结构：24 → 128 → 128 → 9 hazard logits，9 个有限区间加剩余尾部质量，共 10 桶。
- 时间边界：2、5、10、20、60、180、600、1800、7200 秒及无限尾部。
- 数据：26,785 个 frontier exposure，1,652 个稳定 prefix digest。
- cold 节点参与训练；仅排除 3,100 个无法重建历史的左截断 warm exposure。
- loss：离散 hazard NLL，支持右删失及桶内部分删失。cold/warm 总权重相等，组内 sqrt-token 加权。
- digest 切分 70/15/15；标准化只使用训练集。此切分不是 session 隔离。

## 模型选择

| seed | 训练 epoch | 最佳加权验证 NLL |
|---:|---:|---:|
| 41 | 91 | 约 1.04 |
| 42 | 100 | **1.009918** |
| 43 | 100 | 约 1.04 |

按验证 NLL 选择 seed 42，完整精度和每个 seed 的指标见 `training/results.json`。
验证 NLL 使用训练同口径权重；以下测试 NLL 未加权，二者不直接比较大小。

## 所选单模型的测试指标

| 子集 | Censor NLL |
|---|---:|
| all | **0.942261** |
| cold | 0.823189 |
| warm | 1.013874 |

| 未来 horizon | AUC | Bernoulli NLL | Token-Brier |
|---|---:|---:|---:|
| 5 秒 | 0.952016 | 0.261921 | 0.091649 |
| 20 秒 | 0.949767 | 0.288716 | 0.085846 |
| 60 秒 | 0.929949 | 0.333631 | 0.084029 |

此前 10-seed ensemble 的 NLL 0.92690 与这里单个 seed 的 0.942261 不是同一部署方案。
本实验使用单模型以测量实际 serving 推理开销。

## 条件更新

在已等待 20 秒、继续观察未来 20 秒的可观测 held-out 风险集中：

| 方法 | Bernoulli NLL | Token-Brier |
|---|---:|---:|
| 不更新原预测 | 0.75221 | 0.21903 |
| log-survival 条件更新 | 0.40033 | 0.12026 |

完整 age/horizon 结果见 `shift_report_zh.md` 与 `shift_results.json`。
这是可观测子集诊断，早删失样本未做 IPCW；不能直接作为 serving 策略收益。

## 系统实验边界

Serving 测试集另行排除了与训练 replay 重叠的 session、来源轨迹及首条用户消息，
剩余 1,970 个请求、572 个 session（943 个 OpenHands turn，1,027 个普通请求）。
公共 system prefix 仍可能重叠。数据标签来自旧 frozen replay 的实际 wall clock，
并不是无压力服务耗时；请求结束时推理还存在观测时刻分布偏移。

CPU 实际缓存测试已验证完整 frontier 超过 16 个候选时可以选择列表尾部的 victim、
split/lock/unlock、SWA 与 Full 释放、新父节点覆盖、等待 pending future。数学测试
验证了条件 survival、价值尺度、右删失 loss、future 复用与异常传播。

正式在线效果仅以完成并通过八个 TP rank 一致性核验的 `report_zh.md` 为准。
