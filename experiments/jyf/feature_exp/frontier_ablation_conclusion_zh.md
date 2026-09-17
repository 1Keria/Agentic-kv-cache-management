# 真实 eviction frontier 的特征消融结论

## 实验回答

原始 16 维可以预测未来复用，但不是合适的最终输入。真实 frontier 上，以下 11 维统一模型比原始 16 维明显更好：

1. `node_tokens`
2. `path_tokens`
3. `age_events`
4. `idle_events`
5. `lru_frac`
6. `hits`
7. `gap_present`
8. `recent_gap_events`
9. `gap_ewma_events`
10. `gap_std_events`
11. `is_openhands`

原始 16 维中的 `depth`、`is_request`、`is_cold` 可以删除。`parent_hits`、`siblings`、`warm_sibling_fraction`、`is_swa` 在这个统一模型里没有稳定增益；`owner_turn` 对 warm 有负作用，但对 cold 有明显价值，因此更适合只输入 cold head。

## 数据和方法

- 数据来自真实 SGLang eviction frontier trace，而不是 message-boundary 模拟树。
- 692 次 eviction frontier，原始 29,885 个 candidate exposure。
- 为重建 `idle_events`，排除 3,100 个在 trace 开始前已经 warm、但 trace 内没有过去 demand 的左截断 exposure，最终使用 26,785 行。
- 1,652 个不同的稳定 prefix digest。
- 按 digest 做 70/15/15 切分，同一 prefix 的重复 exposure 不跨训练、验证和测试集合。
- 预测未来 5、20、100 个真实 cache-access event 内是否再次 demand 同一 prefix。
- trace 中的 demand 使用稳定 token-prefix digest，因此节点被 evict 后重新创建，后续 demand 仍能成为正标签。
- 每组使用相同的固定 19 维输入网络，被消融的列置零，避免输入维数改变其他权重初始化。
- 模型为两层 64 hidden unit MLP；结果为 10 个 seed 的概率 ensemble。
- `recent_gap_events` 的离线重建值与 server 日志字段在 99.66% 的可核验 exposure 上一致。

## 最终对比

以下是全部 test frontier exposure 的结果：

| 输入 | NLL@5 ↓ | AUC@5 ↑ | NLL@20 ↓ | AUC@20 ↑ | NLL@100 ↓ | AUC@100 ↑ |
|---|---:|---:|---:|---:|---:|---:|
| 原始 16 维 | 0.43132 | 0.8708 | 0.43420 | 0.8803 | 0.40850 | 0.8882 |
| 新 11 维 | **0.36511** | **0.9103** | **0.38934** | **0.9017** | **0.36430** | **0.9103** |

新 11 维相对原 16 维的 NLL 分别降低 15.4%、10.3% 和 10.8%。AUC 分别提高 0.0395、0.0214 和 0.0221。这一差异是在 held-out prefix 和 10-seed ensemble 上得到的，不是训练集拟合结果。

对 warm exposure，改善更明显：

| 输入 | NLL@5 ↓ | AUC@5 ↑ | NLL@20 ↓ | AUC@20 ↑ | NLL@100 ↓ | AUC@100 ↑ |
|---|---:|---:|---:|---:|---:|---:|
| 原始 16 维 | 0.53189 | 0.8027 | 0.42143 | 0.8565 | 0.32861 | 0.9103 |
| 新 11 维 | **0.41684** | **0.8892** | **0.33670** | **0.9110** | **0.25753** | **0.9477** |

## 每组特征的证据

### 必须保留历史特征

从 revised 模型删除 `age/idle/hits/gap` 历史组后：

- NLL@5：0.40150 → 0.56983；
- AUC@5：0.8941 → 0.7856；
- NLL@20：0.41027 → 0.51264。

这是所有消融中最大的退化。历史特征是主要预测信号。

`idle_events` 和 gap 统计也确实提供新增信息。规范化的 13 维原始输入 NLL 为 0.40546/0.41952/0.39579；加入 `idle_events + gap_ewma + gap_std` 后，NLL 降为 0.40038/0.41033/0.38403。对 warm exposure，AUC@20 从 0.8727 提升至 0.8937。

### `gap_present` 不能删除

数据中有 2,305 个 exposure 已经 warm，但只有一次历史 hit，尚未产生 reuse gap。因此 `gap_present` 与 `is_cold` 不等价。删除它后，全部 exposure 的 NLL@5 从 0.43132 变差到 0.43627，warm NLL@20 从 0.42143 变差到 0.43215。

### `is_cold` 可以删除

在全部 29,885 个原始 exposure 中：

```text
is_cold == 1  <=>  hits == 0
```

删除 `is_cold` 没有损失，反而使原始模型的 NLL@5 从 0.43132 降至 0.41073。它没有增加信息。

### `is_request` 可以删除

当前 workload 的 traffic 只有 `openhands` 和 `request` 两种，因此：

```text
is_request = 1 - is_openhands
```

删除 `is_request` 后，NLL/AUC 基本不变：NLL@20 为 0.43342，而原模型为 0.43420。保留两个 bit 只会引入完全共线的输入。

### `depth` 没有独立增益

删除 `depth` 后结果基本不变：

- NLL@5：0.43132 → 0.43261；
- NLL@20：0.43420 → 0.43390；
- AUC@100：0.8882 → 0.8890。

`path_tokens` 已经表达路径长度，而且比受 node split 粒度影响的 `depth` 更稳定。

### `node_tokens/path_tokens` 应保留

这两个特征单独预测能力弱，但与历史和 traffic 存在有用交互。从 revised 模型同时删除它们后：

- NLL@5：0.40150 → 0.41836；
- NLL@20：0.41027 → 0.43425；
- AUC@20：0.8968 → 0.8822。

单独删除 `node_tokens` 也使紧凑 revised 模型 NLL@5 从 0.40038 变差到 0.41420。因此不能根据单特征 AUC 将它们删除。

### `lru_frac` 有新增信号

从 revised 模型删除 `lru_frac` 后：

- NLL@5：0.40150 → 0.41391；
- NLL@20：0.41027 → 0.42299；
- AUC@5：0.8941 → 0.8864。

它不是最强特征，但在 `idle_events` 已存在时仍提供额外的 frontier-relative 信息。

### traffic type 很重要

删除 `is_openhands` 后是仅次于删除历史组的退化：

- NLL@5：0.40150 → 0.46088；
- NLL@20：0.41027 → 0.46828；
- AUC@100：0.9044 → 0.8655。

因此应保留一个 traffic bit；当前二分类 workload 不需要两个 one-hot bit。

### parent/sibling family 不适合统一模型

从 revised 模型删除整个 family 后，NLL@5 反而从 0.40150 改善到 0.38025。以最终 11 维为基准逐项加回：

| 加回特征 | NLL@5 | NLL@20 | 结论 |
|---|---:|---:|---|
| 不加，11 维基线 | **0.36511** | **0.38934** | 最好 |
| `parent_hits` | 0.36920 | 0.39267 | 无增益 |
| `siblings` | 0.38245 | 0.41028 | 明显变差 |
| `warm_sibling_fraction` | 0.36920 | 0.38988 | 基本无增益 |

family 特征对 cold 有一些弱排序信号，但加入统一模型后被 warm exposure 的相反关系干扰。当前结果不支持把它们放进共享输入。

### `owner_turn` 在 cold 子集有信号，但不能据此拆 head

对全部 exposure，将 `owner_turn` 加回最终 11 维后 NLL@5 从 0.36511 变差到 0.36829；warm NLL@100 从 0.25753 变差到 0.27974。

但对 cold exposure，它有明显帮助：

- AUC@5：0.7402 → 0.8069；
- NLL@5：0.27910 → 0.25926；
- NLL@20：0.47700 → 0.44660。

因此它不是垃圾特征，而是在 cold 子集上有条件价值。不过，这只是统一模型的分桶评估，不能证明应当拆分 cold/warm head；是否保留 `owner_turn` 应由统一模型的整体验证指标和最终 eviction replay 决定。

### `is_swa` 没有稳定增益

将 `is_swa` 加回最终 11 维后差异很小：NLL@5 为 0.36405，基线为 0.36511；AUC@100 为 0.9105，基线为 0.9103。这个量级不值得增加输入。它可以在跨配置数据更多后重新验证。

## 推荐实现

继续使用一个 Unified MLP。仓库中专门的架构对照实验已经表明，Unified 在三段累计输出的全部 overall 指标上胜过 shared trunk + cold/warm heads；10-bucket 实验也得到同样结论。当前 feature ablation 没有重新比较这两种架构，cold/warm 表格只是同一个 Unified 模型在两个数据子集上的诊断，因此不能用来推翻已有结论。

统一模型的候选输入使用上述 11 维；`hits` 与 `gap_present` 已经显式表达历史及其缺失状态。`is_cold` 在当前 trace 中与 `hits == 0` 完全等价，可以为了接口清晰保留，也可以删除以避免重复信息，二者需要在固定 Unified 训练设置中最终确定。

`owner_turn` 加入 11 维候选后会改善 cold 子集，但损害 warm 和 overall 指标，所以目前不加入主输入。这个现象只说明应继续观察 cold 子集，不能证明需要独立 head。最终选择应通过 Unified 模型的 eviction replay 比较 recomputed tokens 和 evicted-then-soon-reused tokens，而不是仅凭某个子集的 AUC。

`parent_hits/siblings/warm_sibling_fraction` 暂不进入主模型，可以留作后续跨 workload 验证。cold grace-period 仍可作为模型之外的策略保护。

## 结果边界

本实验验证的是一个 50% OpenHands、50% request 的 held-out workload。prefix 按 digest 隔离，但训练和测试仍来自同一次 replay。`is_openhands`、`owner_turn` 和 `lru_frac` 还需要在其他 traffic ratio 和另一条 replay 上复验，才能声称跨 workload 泛化。
