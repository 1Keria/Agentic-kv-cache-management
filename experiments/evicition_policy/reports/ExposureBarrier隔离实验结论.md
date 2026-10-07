# Exposure Barrier 隔离实验结论

日期：2026-09-29

> 本报告记录只接入 Full 回收路径的第一轮实验。SWA 适配已经完成，最新结论见 `UnifiedExposureBarrier适配实验结论.md`。

## 结论

`LRU + Exposure Barrier` 的核心假设得到验证：**在 Full KV 是主要瓶颈时，单次回收内暂缓刚暴露祖先，可以显著减少沿同一条链继续深入所造成的误删和超额释放。** 该机制不依赖 session ID、工具执行时间、下一轮到达时间或复用预测。

但当前实现还没有覆盖完整的混合缓存回收路径。DeepSeek-V4-Flash 的联合压力下，SWA 成为更严格的瓶颈，而本轮 Exposure Barrier 只接入了 Full 回收入口，因此 Full 侧改善没有转化为最终 cached token 收益。这里不需要为 SWA 设计另一套策略；下一步应把**同一种基于 LRU 的回收前沿屏障语义**实现到 SWA internal tombstone/cascade 路径，并统一 Full/SWA 的工程行为。

## 实验设计

使用上一轮冻结的完全相同 27 请求 trace，包含 4 个会话、22 次续接和 1 次分叉。所有请求输入，以及用于构造后续请求的 frozen output/tool token 均固定。服务本次实际生成的输出只作为观测结果，不参与下一轮输入构造；不同 case 的实际生成输出并不完全一致，因此本轮因果比较建立在固定输入和固定事件顺序上。

| 压力档 | Full 容量 | SWA 容量 | 目的 |
|---|---:|---:|---|
| Control | 32,768 | 16,384 | 计算可复用上限 |
| Full-only | 16,384 | 16,384 | 隔离 Full 淘汰选择 |
| SWA-only | 32,768 | 8,192 | 隔离 SWA cliff |
| Joint | 16,384 | 8,192 | 验证两池组合后的系统效果 |

每个压力档比较原生 LRU、原生 SLRU 和 `LRU + Exposure Barrier`。Barrier 只改变 Full 回收过程：回收开始时的合法叶子进入主堆，删除叶子后新暴露的父节点进入临时延迟堆；只有主堆耗尽且释放仍不足时，才使用延迟堆。下一次回收重新按普通 LRU 开始。

## 主要结果

### 1. Full-only：结构性收益明确

| 指标 | LRU | SLRU | Exposure Barrier | 相对 LRU |
|---|---:|---:|---:|---:|
| 累计 cached token | 84,224 | 84,224 | 96,512 | **+12,288（+14.59%）** |
| 相对 control 的额外处理 token | 25,344 | 25,344 | 13,056 | **-12,288（-48.48%）** |
| 后续仍需求却被 Full 回收的 token | 25,344 | 25,344 | 13,056 | **-48.48%** |
| 其中刚暴露祖先 | 13,056 | 13,056 | 768 | **-94.12%** |
| Full overshoot | 20,736 | 20,736 | 9,472 | **-54.32%** |
| 暴露后继续深入的 victim step | 12 | 12 | 1 | **-11** |

收益来源与设计目标完全对应：Barrier 没有通过长期保护所有父链，而是几乎消除了当前回收中对刚暴露祖先的连续深入。LRU 和 SLRU 在该档仍完全相同。

逐请求看，Barrier 在第 12–15 个请求中分别多命中 3,328 token；第 18 个请求少命中 1,024 token，净收益仍为 12,288 token。这说明 Barrier 不是无代价保护，而是在有限容量下换了一组 victim；本 trace 中净结果显著为正。

### 2. SWA-only：当前实现尚未接入 SWA 回收路径

LRU、SLRU 和当前 Exposure Barrier 实现的累计 cached token 都是 13,312，相对 control 都额外处理 96,256 token；Full 没有发生淘汰，而 Barrier 尚未接入 SWA 回收入口，因此没有改变任何选择。该结果说明的是**工程覆盖不完整**，不能解释为同一策略不适用于 SWA。

SWA-only 的 108 个 victim step 中，82 个是 `swa_internal_tombstone`；它们释放 99,584 token，其中 87,296 token 后续再次需求。SWA 路径需要实现与 Full 相同的原则：**一次回收优先在已有独立前沿之间选择，在主前沿仍有选择时，不继续沿刚处理过的同一结构深入或触发连续 cascade。** Full 通过“新暴露父节点”识别深入，SWA 则需要通过 internal tombstone、cascade 及节点祖先关系映射同一语义。

### 3. Joint：Full 行为改善，但最终收益被 SWA 掩盖

| 指标 | Joint LRU | Joint Barrier | 变化 |
|---|---:|---:|---:|
| 累计 cached token | 13,312 | 13,312 | 0 |
| 相对 control 的额外处理 token | 96,256 | 96,256 | 0 |
| Full 后续仍需求却被回收的 token | 73,472 | 66,816 | -6,656（-9.06%） |
| Full 刚暴露祖先的未来需求损失 | 27,904 | 19,456 | -8,448（-30.28%） |
| Full 暴露后继续深入的 victim step | 17 | 8 | -9 |
| SWA 后续仍需求却被回收的 token | 96,256 | 93,696 | -2,560 |

Barrier 确实改变了 Full victim，并减少了 Full 侧结构性损失；但未修改的 SWA 路径仍使几乎所有压力请求只能命中共享的 512-token 前缀，因此最终 cached token 不变。这个结果说明同一策略必须完整覆盖 Full 与 SWA 两条执行路径，不能只在 Full 入口实现后就评价其系统效果。

## 延迟结果的解释边界

本轮每个配置只运行一次，服务逐次重启，延迟还受 GPU/JIT 和请求位置影响。Full-only 中 Barrier 的 mean TTFT 为 0.675 秒，LRU 为 0.565 秒；p95 分别为 2.314 秒和 2.612 秒。均值与 p95 方向不一致，因此本轮不据此声称延迟改善或退化。缓存选择和 token 损失是这次实验的有效结论；正式延迟结论需要重复运行、顺序互换和更大 workload。

## 工程与有效性检查

- 10 个 GPU case 全部完成，固定 trace 哈希一致。
- 10 个 case 的输入 token 序列完全一致；实际生成输出不完全一致，但不会反馈到后续冻结输入。
- 所有候选集合覆盖完整，所有 eviction begin/end 配对完整。
- 120 项测试和 3 个参数化 subtest 通过。
- Barrier 关闭时保留原生 LRU 行为；启用时只有单次 Full 回收的候选前沿发生变化。
- 没有加入 session、工具时间、等待时间、频率衰减或未来预测。

原始 suite：`results/pilot/exposure_barrier_20260929T064135Z/`

机器分析：`reports/agent_exposure_barrier_20260929.json`

## 下一步

保留 Exposure Barrier 作为统一策略，不再向它叠加更多启发式参数。下一轮不是设计一套独立的 SWA 策略，而是把相同策略语义接入 SWA：

1. 把 SWA victim 分成 `full_leaf_cascade` 和 `swa_internal_tombstone`，恢复每个 victim 的祖先关系、所属回收前沿以及 cascade 来源。
2. 为 SWA 实现与 Full 一致的状态机：初始前沿优先、同链继续深入延迟、主前沿耗尽后安全回退；差异只存在于候选集合和回收 API 的工程适配。
3. 先在当前固定 trace 的 SWA-only 与 Joint 两档验证；只有最终 cached token 和额外处理 token 改善后，再扩大到 20 会话、1,206 请求 workload。
4. 扩大实验时做容量扫描、重复运行和策略顺序互换，再报告延迟与吞吐。

当前最重要的设计判断是：**策略层只有一套基于 LRU 的结构化、有界、无预测启发式；Full 与 SWA 只是同一策略在两种缓存组件和回收接口上的不同工程实现。当前实验验证了 Full 实现，尚未完成 SWA 实现。**
