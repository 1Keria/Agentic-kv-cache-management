# Hazard Curve 桶内插值实验结论

## 结论

测试集对“桶内 constant hazard / log-survival 线性”假设提供了**近似支持**，但它不是精确规律。

1. 不依赖 MLP 的 Kaplan–Meier 经验曲线中，log-survival 在 K=5、K=10、K=20 下都比 linear-survival 更接近真实桶内 survival。
2. 固定同一个 MLP 输出的 bucket 端点后，log 与 linear 的实际预测差异通常很小；分桶变细带来的收益远大于选择哪一种平滑插值。
3. right-step（把桶内概率都推迟到右端点）明显更差，说明宽桶内不能完全不插值。
4. Conditional Shift 的主要收益不是由 log 插值“制造”的。在 K=10/K=20 的短期场景中，log 与 linear 的 token-Brier 差异通常不超过 0.00016，小于此前 Shift 与 Re-predict 约 0.002–0.008 的差异。

因此建议继续使用 log-survival 作为默认插值：它有常数连续 hazard 的明确解释，经验 KM 曲线整体也更支持它。但应把它表述为合理近似，而不是数据严格服从该模型。

## 实验方法

只使用原实验的 held-out test split（history >= 1），共 23,786 个 prefix observation。

比较三种桶内定义：

- `log_survival`：`S(t)/S(left) = (1-h)^u`；
- `linear_survival`：`S(t)/S(left) = 1-u*h`；
- `right_step`：到 bucket 右端点才释放该桶概率质量。

其中 `u=(t-left)/(right-left)`。

验证分为两部分：

1. 用精确 gap 和删失信息计算测试集 Kaplan–Meier survival；在每个 bucket 的 25%、50%、75% 位置，比较三种插值与经验条件 survival 的误差。该部分不使用 MLP。
2. 固定原有 Initial MLP 的相同 bucket 端点，在桶内点以及 Conditional Shift 的 `(age, future horizon)` 上比较 token-Brier、Bernoulli NLL 和 ECE10。

## Kaplan–Meier 经验曲线结果

下表为 token-weighted KM 的平均绝对 survival 误差：

| 分桶 | log-survival | linear-survival | right-step |
|---|---:|---:|---:|
| K=5 | **0.052328** | 0.054941 | 0.122463 |
| K=10 | **0.014650** | 0.016682 | 0.068220 |
| K=20 | **0.004710** | 0.004999 | 0.032660 |

按 bucket 内事件数量加权后仍是同样方向：

| 分桶 | log-survival | linear-survival | right-step |
|---|---:|---:|---:|
| K=5 | **0.060088** | 0.063629 | 0.143103 |
| K=10 | **0.014135** | 0.017945 | 0.105721 |
| K=20 | **0.004862** | 0.005522 | 0.058284 |

这说明 log-survival 比 linear 更符合总体经验曲线，但更重要的现象是：K 从 5 增加到 20 后，误差下降了约一个数量级。细分 bucket 比插值形式更重要。

## 固定 MLP 端点的桶内预测

对所有 bucket 内部 25%、50%、75% 检查点取平均：

| 分桶 | 插值 | token-Brier | token Bernoulli NLL | token ECE10 |
|---|---|---:|---:|---:|
| K=5 | log | **0.171717** | 0.506083 | **0.052479** |
| K=5 | linear | 0.171906 | **0.506046** | 0.053800 |
| K=10 | log | **0.177698** | **0.514885** | **0.041008** |
| K=10 | linear | 0.177828 | 0.515241 | 0.042147 |
| K=20 | log | **0.181998** | **0.524426** | **0.039033** |
| K=20 | linear | 0.182017 | 0.524479 | 0.039291 |

K=5 的 NLL 中 linear 仅好 0.000037，而 log 的 Brier 和 calibration 更好。K=10/K=20 中 log 三项都略好，但绝对差距很小。

不同 K 的平均分数不能直接用于选择 K，因为各配置的内部检查点集合不同；这里主要比较同一个 K 内的插值。

## Conditional Shift 的关键结果

短期代表性场景：

| K | age | future | log token-Brier | linear token-Brier | 更好 |
|---|---:|---:|---:|---:|---|
| K=5 | 5s | 5s | **0.154810** | 0.159345 | log |
| K=5 | 20s | 20s | **0.074361** | 0.074521 | log |
| K=10 | 5s | 20s | 0.210985 | **0.210983** | 基本相同 |
| K=10 | 20s | 5s | **0.046560** | 0.046602 | log |
| K=10 | 20s | 20s | **0.074619** | 0.074769 | log |
| K=20 | 5s | 5s | **0.152115** | 0.152185 | log |
| K=20 | 20s | 20s | **0.071695** | 0.071696 | 基本相同 |

除了非常粗的 K=5、`age=5/future=5`，log 与 linear 的差别都很小。边界恰好对齐时两者完全相同，因为插值只影响 bucket 内部。

小时级长尾中 linear 有时略好，例如 K=10、`age=600/future=3600`：

- log：0.004715；
- linear：0.004617。

但绝对差仅约 0.00010，且该区域事件较少。

## 限制

- 模型层测试复用了已有 checkpoint；原模型的部分删失 loss 使用了 log-survival 插值，因此模型层比较对 log 有轻微训练偏置。
- Kaplan–Meier 部分不依赖 MLP训练，仍然得到 log 更好的方向，缓解了上述疑虑。
- KM 是混合所有 prefix 后的总体曲线；不同 prefix 的个体 hazard 不一定都是常数。
- 最后一个无限 tail bucket 无法做桶内插值，本实验不评价超过最后有限边界的查询。

## 建议

- K=10/K=20 继续使用 log-survival；不需要为此增加额外模型。
- 正式描述为“piecewise-constant hazard approximation”。
- 不把宽 tail bucket 内的概率用于精细定时判断。
- 如果将来需要更高时间精度，优先增加关键区间的 bucket，而不是设计更复杂的桶内插值函数。
