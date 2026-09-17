# Log-linear 区间内插值校准实验

## 结论

在当前 K=10 hazard MLP 上，`log-survival` 区间内插值的校准性略优于 `linear-survival`，并明显优于不插值的 `right-step`。但 log 与 linear 的差距很小，因此实验支持“使用 log-linear 作为默认实现”，不能说明它相对普通线性插值有数量级优势。

当前更显著的问题不是插值公式，而是部分时间点的基础 hazard/端点概率没有完全校准。特别是已经等待 20 秒后，模型明显低估未来 5 秒和 20 秒内发生 reuse 的概率；log 与 linear 在这里表现接近，换插值方法无法解决该问题。

## 实验设置

- 数据：`prefix_reuse_samples.npz` 的固定 test split。
- 测试样本：23,786，其中 observed reuse 12,019，right-censored 11,767。
- 模型：K=10 hazard MLP，使用 seed 41/42/43 的预测均值；不重新训练。
- 权重：同时报告 object-weighted 与 token-weighted。
- 区间内检查点：每个有限 bucket 内的 10%、25%、50%、75%、90% 位置。
- 条件检查：先存活到 age，再预测未来 horizon 内 reuse，即 `P(T <= age+horizon | T > age)`。
- 右删失：观测风险使用 Kaplan-Meier 估计，而不是把删失样本直接标成“永不复用”。

比较三种从 bucket 端点生成任意时刻生存概率的方法：

1. `log_survival`：在相邻端点之间对 `log S(t)` 做线性插值，对应区间内 hazard 为常数。
2. `linear_survival`：直接对 `S(t)` 做线性插值。
3. `right_step`：区间内保持左端点值，直到右端点才跳变，作为不做平滑插值的基线。

## 汇总结果

ECE10 越低越好。它把预测风险分成十组，比较每组平均预测风险与 Kaplan-Meier 观测风险，再按组大小加权。

| 权重 | 方法 | 区间内 mean ECE10 | 区间内 p90 | 条件预测 mean ECE10 | 条件预测 p90 |
|---|---|---:|---:|---:|---:|
| object | log-survival | 0.04185 | 0.05197 | 0.01566 | 0.04401 |
| token | log-survival | **0.03992** | **0.05442** | **0.01529** | **0.03872** |
| object | linear-survival | 0.04225 | 0.05248 | 0.01592 | 0.04401 |
| token | linear-survival | 0.04069 | 0.05654 | 0.01537 | 0.03890 |
| object | right-step | 0.05989 | 0.11698 | 0.01892 | 0.05580 |
| token | right-step | 0.06160 | 0.12681 | 0.01799 | 0.04292 |

token-weighted 区间内 mean ECE10 中，log 比 linear 低 0.00077；条件预测中低 0.00008。方向一致，但绝对差距很小。right-step 则明显更差，说明区间内部确实需要平滑展开概率。

## 关键误差案例

token-weighted、已经等待 20 秒的条件预测如下：

| 未来窗口 | 方法 | 平均预测风险 | KM 观测风险 | ECE10 |
|---|---|---:|---:|---:|
| 5s | log-survival | 0.00701 | 0.04728 | 0.04033 |
| 5s | linear-survival | 0.00670 | 0.04728 | 0.04064 |
| 20s | log-survival | 0.02750 | 0.08052 | 0.05365 |
| 20s | linear-survival | 0.02681 | 0.08052 | 0.05434 |
| 60s | log-survival | 0.05368 | 0.08348 | 0.03178 |
| 60s | linear-survival | 0.05368 | 0.08348 | 0.03178 |

这说明 age=20s 后的短期 reuse 风险被系统性低估。由于两种连续插值几乎给出相同结果，主要原因应在 bucket 端点输出、训练目标或该条件子群的分布偏移，而不是 log-linear 公式。

## 判断与后续建议

- 当前实现可以保留 log-survival 插值：它具有明确的 piecewise-constant hazard 解释，汇总校准也略好。
- 不建议采用 right-step；它在 bucket 内无法表达时间推进，校准显著更差。
- 下一步优先做 endpoint/conditional recalibration，而不是继续微调插值公式。可在 validation split 上对累计 hazard 做 temperature/isotonic calibration，再观察 age=20s 子群是否改善。
- 当前 NPZ 未保存 trajectory ID，因此本次无法按 trajectory 做 cluster bootstrap。后续数据构造应保留 trajectory/request group ID，再给 log-vs-linear 差值计算置信区间，判断微小优势是否稳定。

## 产物

- `results.json`：完整汇总及逐检查点结果。
- `point_calibration.csv`：所有区间内时刻的校准指标。
- `conditional_calibration.csv`：所有 age/horizon 条件预测指标。
- `reliability_bins.csv`：每个检查点的十等分 reliability 数据。
- `run_insection_calibration.py`：可复现实验脚本。
