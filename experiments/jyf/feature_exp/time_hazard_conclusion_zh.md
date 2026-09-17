# 秒级 Hazard 特征探索结论

## 结论

本实验预测真实 eviction frontier 上某个稳定 prefix 距离下一次 demand 的 wall-clock 时间。标签为：

```text
next_demand.wall_s - current_frontier.wall_s
```

模型使用与最终时间模型相同的 K=10 秒级边界：

```text
2, 5, 10, 20, 60, 180, 600, 1800, 7200, +inf 秒
```

最强的已测试输入是同时保留秒数和 cache-access event 两套历史尺度的 `both_candidate16`：

1. `node_tokens`
2. `path_tokens`
3. `age_events`
4. `age_seconds`
5. `idle_events`
6. `idle_seconds`
7. `lru_frac`
8. `hits`
9. `gap_present`
10. `recent_gap_events`
11. `recent_gap_seconds`
12. `gap_ewma_events`
13. `gap_ewma_seconds`
14. `gap_std_events`
15. `gap_std_seconds`
16. `is_openhands`

秒数和 event 不是互相替代的重复输入。秒数表达真实等待时间，event 数表达等待期间 workload 推进了多少；两者同时输入明显优于任意一套单独输入。

## 主要结果

### 主方案分别做了什么

五个主方案用于回答不同问题：

| 方案 | 具体输入 | 要回答的问题 |
|---|---|---|
| `original16` | 用户最初提出的 16 维，所有 age/gap 都按 cache-access event 计数 | 原始方案预测秒级 hazard 的基线表现 |
| `original_time16` | 在原始 16 维中用 `age_seconds` 替换 `age_events`，用 `recent_gap_seconds` 替换 `recent_gap_events`，其余不变 | 只把原始时间字段换成秒是否足够 |
| `event_candidate11` | `node/path tokens, age_events, idle_events, lru, hits, gap mask, recent/ewma/std event gaps, traffic` | 清除 depth、family、重复 bit 后，纯 event-history 能做到什么程度 |
| `time_candidate11` | 与 event 11 维结构相同，但 `age/idle/recent/ewma/std` 全部换成 seconds | 对秒级 hazard，纯 second-history 是否优于纯 event-history |
| `both_candidate16` | 共享的 size/LRU/hits/mask/traffic 之外，同时输入 event 和 seconds 两套 `age/idle/recent/ewma/std` | 两个时间尺度是否含有互补信息 |

`original_time16` 不是在原始 16 维上新增时间特征，而是做一一替换；`both_candidate16` 才是真正同时保留两种尺度的方案。

以下为 held-out prefix 上的 10-seed ensemble：

| 输入 | Censor NLL ↓ | AUC@5s ↑ | AUC@20s ↑ | AUC@60s ↑ |
|---|---:|---:|---:|---:|
| `original16` | 1.25458 | 0.8677 | 0.8748 | 0.8667 |
| `original_time16` | 1.21814 | 0.8791 | 0.8870 | 0.8618 |
| `event_candidate11` | 1.14327 | 0.9125 | 0.9057 | 0.8918 |
| `time_candidate11` | 0.99402 | 0.9369 | 0.9351 | 0.9209 |
| `both_candidate16` | **0.92690** | **0.9528** | **0.9510** | **0.9305** |

相对原始 16 维，联合 16 维的 censor-aware NLL 降低 26.1%。相对纯秒级 11 维，联合输入的 censor-aware NLL 降低 6.75%。

联合 16 维在子集上的结果：

| 子集 | Censor NLL ↓ | AUC@5s ↑ | AUC@20s ↑ | AUC@60s ↑ |
|---|---:|---:|---:|---:|
| all | 0.92690 | 0.9528 | 0.9510 | 0.9305 |
| cold | 0.81882 | 0.9352 | 0.9315 | 0.8096 |
| warm | 0.99190 | 0.9310 | 0.9346 | 0.9540 |

所有模型都是一个 Unified Hazard MLP。cold/warm 只用于分桶诊断，没有训练两个 head。

### 最终候选的完整指标

`both_candidate16` 在 all test exposure 上共有 4,910 行：

| 指标 | @5s | @20s | @60s |
|---|---:|---:|---:|
| 正例率 | 0.3823 | 0.4800 | 0.5925 |
| AUC ↑ | 0.9528 | 0.9510 | 0.9305 |
| AP ↑ | 0.9015 | 0.9389 | 0.9491 |
| Brier ↓ | 0.07872 | 0.08673 | 0.10270 |
| Bernoulli NLL ↓ | 0.26315 | 0.28197 | 0.32950 |
| Token-Brier ↓ | 0.09389 | 0.08925 | 0.08686 |

完整 K=10 survival target 的 censor-aware NLL 为 **0.92690**。它是主 loss 指标；上表的 `@5s/@20s/@60s` 是从同一条 hazard curve 导出的累计概率指标。

- AUC：随机选一个 horizon 内复用和一个 horizon 内未复用样本，前者得分更高的概率，只衡量排序。
- AP：precision-recall 曲线的平均精度，对短 horizon 的低正例率比 AUC 更敏感。
- Brier：预测概率与 0/1 标签的均方误差，衡量概率质量。
- Bernoulli NLL：指定 horizon 上累计复用概率的对数损失。
- Token-Brier：按 candidate KV token 数加权的 Brier，更关注大节点。
- Censor NLL：对全部 K=10 hazard bucket 计算的删失似然，能够使用“直到 trace 结束仍未复用”的样本。

## 特征证据

下表以联合 16 维为基线。`Δ Censor NLL` 是删除特征后的变化；正数表示删除后变差。配对差值使用相同的 10 个 seed 和相同初始化。

| 删除内容 | Ensemble Δ NLL | 10-seed 配对均值 ± std | 判断 |
|---|---:|---:|---|
| `idle_seconds` | +0.11332 | +0.13796 ± 0.05264 | 最强单项时间特征，保留 |
| event gap 三项 | +0.04354 | +0.04074 ± 0.02193 | 整组有效，保留 |
| `node_tokens` | +0.04191 | +0.04525 ± 0.01461 | 稳定有效，保留 |
| `is_openhands` | +0.02742 | +0.03253 ± 0.02274 | 有效，保留一个 traffic bit |
| `age_events` | +0.02140 | +0.02618 ± 0.02049 | 有效，保留 |
| `path_tokens` | +0.02142 | +0.02891 ± 0.02923 | 有增量，尤其影响长 horizon |
| `hits` | +0.02124 | +0.02138 ± 0.03380 | 有增量，保留 |
| `recent_gap_seconds` | +0.01077 | +0.01236 ± 0.01256 | 小幅增量 |
| `gap_std_seconds` | +0.01012 | +0.01002 ± 0.01246 | 小幅增量 |
| `age_seconds` | +0.00818 | +0.00713 ± 0.02099 | 较弱，但 @20s 明显变差 |
| `idle_events` | +0.00707 | +0.00620 ± 0.00679 | 很弱；可作为压缩候选 |
| `gap_present` | +0.00552 | +0.00528 ± 0.01747 | 很弱；作为 missingness mask 保留更稳妥 |
| `gap_ewma_seconds` | +0.00437 | +0.00455 ± 0.00992 | 与其他 gap 统计高度相关，单项较弱 |
| `lru_frac` | +0.00418 | +0.00462 ± 0.00660 | 很弱且不同 horizon 方向混合 |

event-gap 的 `recent/ewma/std` 单独删除时差异不大，但同时删除三项使 NLL 明显恶化，说明三者存在替代性，不能根据单项消融把整组都删掉。

`idle_seconds` 与 `idle_events` 的结论不同。删除 `idle_seconds` 会使 AUC@5/20/60 从 0.9528/0.9510/0.9305 降到 0.9333/0.9343/0.9092；删除 `idle_events` 基本不变。因此 wall-clock hazard 必须维护距最近 demand 的秒数。

## 没有稳定增益的原始特征

从纯秒级 11 维候选逐项加回时：

- `owner_turn` 使 overall NLL@5/20/60 全部变差；
- `is_swa` 基本不变；
- `parent_hits`、`siblings`、`warm_sibling_fraction` 只有很小且不一致的变化；
- `is_cold` 没有新增信息，因为当前 trace 中它与 `hits == 0` 完全等价；
- `is_request` 是 `1 - is_openhands`，属于确定性冗余；
- `depth` 在之前的 event 消融中没有独立增益，且 `path_tokens` 更稳定。

因此这些特征暂不进入主候选。family 特征不能称为完全无相关性，只能说在已有 history、size、traffic 输入后没有稳定的增量收益。

## 数据和训练方法

- 来源：真实 SGLang eviction-frontier trace，共 692 个 frontier。
- 原始 candidate exposure 29,885 个；排除 3,100 个无法从 trace 左边界重建时间历史的 warm exposure，使用 26,785 行。
- 1,652 个稳定 prefix digest，按 digest 做 70/15/15 切分，同一 prefix 不跨 split。
- 网络：固定 24 维输入宽度，两个 128-unit ReLU hidden layer，9 个有限区间 hazard 输出。
- 被删除的特征在标准化后置零，因此同一个 seed 的网络初始化保持一致。
- Loss：支持右删失和桶内部分删失的 discrete-hazard NLL。
- 训练权重：`sqrt(kv_tokens)`，并使 cold/warm 两组的总训练权重相等。
- 结果：seed 41–50 的 hazard 概率平均。

`wall_s` 是 frozen 在线 replay 的真实 wall clock。它与离线 `mlp_exp` 都以秒为单位，但时间原点略有不同：离线数据是 request-start 到 next-request-start，本实验是 eviction frontier 到 next demand。后者更符合 eviction 打分时真正需要预测的剩余时间。

## 当前建议

下一阶段先用 `both_candidate16` 作为秒级 Unified Hazard MLP 的完整候选。若要压缩输入，优先尝试删除 `idle_events` 和 `lru_frac` 的联合消融；不要删除 `idle_seconds`、`node_tokens` 或整组 event-gap。

最终决定仍应由 eviction replay 的 recomputed tokens 和 evicted-then-soon-reused tokens 给出。AUC 和 NLL 只验证预测质量。

## 结果边界

当前数据来自一次 frozen replay 和一组 50% OpenHands / 50% request workload。digest 已隔离，但还不是独立 workload。秒级间隔也会受到 replay 调度和在线服务延迟影响；跨 workload 泛化需要在另一条 replay 上复验。
