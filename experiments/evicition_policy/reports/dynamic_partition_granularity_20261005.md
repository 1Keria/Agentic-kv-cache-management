# 动态分区借用尾部分段复核（2026-10-05）

本轮继续优化混合流量下的 `elastic` 动态分区。目标是减少一侧借用共享容量时的整段 radix 后缀回收，同时保持 Full 和 SWA 使用同一套规则，不引入工具调用时间、turn 返回时间或离线流量比例预测。

## 机制

`request_cache_borrowed_segment_tokens=0` 保持旧行为：新增的借用后缀可以作为一个长 radix 节点保存。设置为正数后，只有跨过本区域保障线、进入共享借用区的后缀才按该上限拆分，并向下对齐到模型 page size（本模型为 256 token）。保障线以内的前缀仍按正常 radix 结构保存；Full/SWA 都使用相同的 segment 参数和判定规则。

这样，当全局压力只需要释放几页时，回收器可以删除借用尾部的小节点，而不必连带删除整条长 Agent 后缀。区内候选顺序仍由 LRU 和现有 preferred reclaim 决定。

## 严格同序复核

原 phased replay 的 Agent 阶段有 7 个并行 session，真实缓存插入顺序由请求完成顺序决定。为排除配置之间完成顺序交换的影响，新增 `scripts/build_completion_order_workload.py`：从一次真实并行运行提取完成顺序，保留每个原始完整 prompt 和 traffic class，构造同序的一次性 prompt 回放。这个 workload 只用于机制对照，不能代替并发 serving 性能结论。

固定模型、Full/SWA 容量、prompt 顺序、输出 16 token、`agent_ratio=0.5`、保障范围 0.2～0.8、LRU、preferred reclaim，结果如下：

| 配置 | 总体命中率 | Agent 命中率 | 普通请求命中率 | 额外重算 token | Agent borrowed Full/SWA 驱逐 token | 墙钟秒 |
|---|---:|---:|---:|---:|---:|---:|
| 无分段（0） | 28.2748% | 27.9986% | 70.4310% | 5,479,680 | 3,286,272 / 5,835,008 | 746.8 |
| 2048 + history gate | **29.8278%** | **29.4833%** | **82.4091%** | **5,352,192** | **729,344 / 4,132,352** | 748.3 |
| 4096 + history gate | 28.8330% | 28.4820% | 82.4091% | 5,433,856 | 1,108,224 / 3,316,224 | 750.4 |
| 2048 + no-gate | 33.5886% | 33.3064% | 76.6596% | 5,043,456 | 4,529,664 / 5,396,480 | 726.9 |

在这条固定顺序上，2048 相对无分段提高总体命中 1.5530 个百分点，额外重算减少 127,488 token（2.32%）。4096 退化，说明更粗的节点会重新放大整段回收；此前并行探索中的 1024 也低于 2048，暂不选择“越细越好”的方向。

2048/no-gate 的固定顺序结果看起来更高，但它不能直接作为策略结论。用原始并行 phased workload 做独立复核：

| 配置 | 总体命中率 | Agent 命中率 | 普通请求命中率 | 额外重算 token |
|---|---:|---:|---:|---:|
| 2048 + history gate | **53.5621%** | **53.4516%** | 70.4310% | **3,407,616** |
| 2048 + no-gate | 43.0156% | 42.7952% | **76.6596%** | 4,270,080 |

no-gate 虽然把部分普通请求回访收益提高了约 6.23 个百分点，但 Agent 命中下降 10.66 个百分点，额外重算增加 862,464 token。它对完成顺序非常敏感，不能作为默认配置。history gate 的作用是：当另一类请求已经长期没有可观察活动时，仍保留其返回保障，避免把 Agent 最新尾部策略误用于不同的并行交错。

## 当前推荐配置

当前动态分区候选保持：

```text
REQUEST_CACHE_REGION_POLICY=elastic
REQUEST_AGENT_CACHE_RATIO=0.50
REQUEST_CACHE_AGENT_MIN_RATIO=0.20
REQUEST_CACHE_AGENT_MAX_RATIO=0.80
REQUEST_CACHE_ELASTIC_ACTIVITY_WINDOW=32
REQUEST_CACHE_ELASTIC_PREFERRED_RECLAIM=1
REQUEST_CACHE_ELASTIC_SOFT_STEP=0.1
REQUEST_CACHE_ELASTIC_GHOST_CAPACITY_TOKENS=0
REQUEST_CACHE_ELASTIC_GHOST_RECLAIM=0
REQUEST_CACHE_ELASTIC_FEEDBACK=0
REQUEST_CACHE_BORROWED_SEGMENT_TOKENS=2048
REQUEST_CACHE_BORROW_HIGH_WATERMARK_TOKENS=0
REQUEST_CACHE_BORROW_LOW_WATERMARK_TOKENS=0
```

其中 0.50 是对称的冷启动线，不是从 workload 统计出的 Agent/普通请求比例；运行期间容量仍由观察到的区域占用、借用页和回收压力决定。`high=0/low=0` 保持只在真实全局压力下归还借用页，避免主动水位回收提前删除仍可复用的前缀。

## 结论和限制

1. 主要工程瓶颈确实是借用 radix 长尾的回收粒度；2048 页组在当前模型上能稳定修复一部分过度回收。
2. 2048 是当前候选拐点：1024 的节点数量和链结构扰动更大，4096 又太粗；不能把粒度继续缩小当作一般性优化。
3. history gate 必须保留。no-gate 的收益只在冻结完成顺序下出现，在真实并行交错中反而明显退化。
4. 分段只减少“错误地整段删除”的损失，Agent 区剩余额外重算仍然很大；下一步应围绕固定顺序、多次并行重复和不同压力容量验证，而不是继续叠加 ghost 或时间预测。
5. 固定完成顺序回放把每个 prompt 变成一次性 session，适合比较缓存状态，不适合报告并发吞吐或 TTFT 的最终收益。当前并行结果仍受完成顺序波动影响，正式论文数字需要至少做顺序平衡或多次重复。

## 结果路径

- 固定顺序无分段：`experiments/动态分区试验/results/short_completion_order_gran0_20261005/`
- 固定顺序 2048：`experiments/动态分区试验/results/short_completion_order_gran2048_20261005/`
- 固定顺序 4096：`experiments/动态分区试验/results/short_completion_order_gran4096_20261005/`
- 固定顺序 2048/no-gate：`experiments/动态分区试验/results/short_completion_order_gran2048_nogate_20261005/`
- 原始并行 2048/no-gate：`experiments/动态分区试验/results/short_elastic_gran2048_nogate_20261005/`
- 完成顺序构造器：`experiments/动态分区试验/scripts/build_completion_order_workload.py`
