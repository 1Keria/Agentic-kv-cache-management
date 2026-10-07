# 动态分区：直接调整比例设计

状态：当前实现（2026-10-02）

动态模式把物理 KV 池分成 Agent 区和普通请求区，但不让两区通过借用页共享容量。系统只维护一个 `agent_ratio`，每次比例变化后分别把它映射到 Full 和 SWA 的区域配额；两种 attention 使用同一比例。

## 反馈信号

控制器只使用已经发生的区域淘汰，不预测工具返回时间、下一轮到达时间或 turn 数量。设当前两区配额为 `Q_agent`、`Q_request`，一次反馈期间的淘汰 token 为 `E_agent`、`E_request`：

```text
agent_pressure   = E_agent / Q_agent
request_pressure = E_request / Q_request
gap              = agent_pressure - request_pressure
step             = clip(alpha * gap, -max_ratio_step, max_ratio_step)
agent_ratio'     = clip(agent_ratio + step, min_ratio, max_ratio)
```

归一化压力避免大工作集仅凭绝对淘汰量长期获得更多容量。正的 `gap` 扩大 Agent 区，负的 `gap` 扩大普通区。

## 稳定性机制

- `pressure_hysteresis` 抑制很小的比例抖动。进入滞回区只是不更新，淘汰反馈仍保留并累积。
- `cooldown_evicted_tokens` 限制比例更新频率，避免一个 page 级淘汰连续触发多次调整。
- 比例到达上下限时，继续把比例推向边界外的那一侧反馈会被丢弃；反向压力不会被旧反馈阻塞。
- 比例更新引起的再平衡淘汰会被标记为控制动作并从下一次反馈中清除，避免控制器自激振荡。

动态模式的默认值为：

```text
feedback_mode             = normalized_pressure
alpha                     = 0.20
max_ratio_step            = 0.05
pressure_hysteresis       = 0.02
cooldown_evicted_tokens   = 4096
```

`eviction_share` 仍可显式配置，用于复现旧实验；它不再是动态模式默认值。

## 观测指标

优先记录普通回访首条命中率、普通区额外重算 token、Agent 区额外重算 token、比例轨迹和 Full/SWA 分区淘汰量。总体 token 命中率只作为汇总指标，因为 Agent prompt token 通常远多于普通请求 token。

## 验证结果

详见 [比例反馈验证报告](../experiments/动态分区试验/results/ratio_adaptation_20261002/analysis.md)。在普通请求密集、初始比例为 0.80 的 192 请求 workload 中，固定比例的普通命中率为 0%，快反馈动态版本达到 84.262%，总体命中率从 77.728% 提高到 88.509%，Agent 命中率保持 89.133%。初始比例为 0.61 且已接近 workload 合适值时，动态与固定结果相同，说明该机制解决的是需求变化和比例失配问题，而不是在所有 workload 上制造额外收益。

完整的机器可读结果和实验轨迹见：

- `experiments/动态分区试验/results/ratio_adaptation_20261002/analysis.json`
- `experiments/动态分区试验/results/ratio_adaptation_20261002/analysis.md`
