# 动态分区三路验证（2026-10-02）

## 实验配置

- workload：`experiments/动态分区试验/data/bidirectional_reuse_8agent_swa020_20261002`
- 132 请求：120 Agent、12 普通请求；普通请求在 Agent 压力前后重复。
- DeepSeek-V4-Flash，H800×8，Full KV capacity 102,656 token，page size 256。
- 三组使用相同 LRU、相同模型、相同容量、相同 replay 顺序：`unified`、`fixed(Agent=0.61)`、`borrow(Agent=0.61)`。
- `swa_full_tokens_ratio=0.20`，`max_inflight=1`，固定输出 16 token。

结果目录：`experiments/动态分区试验/results/reuse8agent_mem035_swa020_serial_threeway`。

## 结果

| 模式 | 总体 token 命中率 | Agent 命中率 | 普通命中率 | 普通回访首条 | 墙钟 |
|---|---:|---:|---:|---:|---:|
| unified | 88.8687% | 89.1325% | 61.9644% | 0/2 | 346.2 s |
| fixed | **89.0191%** | 89.1325% | **77.4555%** | 2,048/2,048（约 92%） | 351.3 s |
| borrow | **89.0191%** | 89.1325% | **77.4555%** | 2,048/2,048（约 92%） | 346.9 s |

fixed/borrow 相对 unified 的总体提升为 **+0.1504 个百分点**；普通请求命中率提升 **+15.4911 个百分点**，Agent 命中率没有变化。borrow 在这一条串行 workload 上没有超过 fixed：它确实缓存了借用页（最终 Agent 侧 borrowed Full 35,840 token、SWA 7,936 token），但这些借用页没有带来额外 Agent 命中。

## 结论

1. 分区机制已经被验证：相同 LRU 下，unified 会在 Agent 压力后删除普通热前缀；fixed 和 borrow 保住了普通区保障，普通回访首条重新命中 2,048 token。
2. 总体收益小的主要原因是流量 token 极度偏向 Agent（Agent 约 99% 的输入 token）。普通侧保护的收益只占总 token 的很小比例，不能用总体命中率判断分区是否生效。
3. 当前动态分区的核心收益应先用“普通回访保护率、普通侧重算 token、普通侧 TTFT”衡量，再报告总体平均命中率。
4. borrow 机制已经在工作，但本 workload 没有出现“普通区有空闲容量、Agent 区随后归还 borrowed 页后得到额外复用”的时序，因此不能据此声称 borrow 优于 fixed。
5. 额外压力试验表明，两个并发 Agent 活动 KV 同时增长时，若禁止全局兜底会直接 prefill OOM；现实现为保证服务进度保留全局兜底，并新增 `REGION_EVICT_FALLBACK` 日志。该日志意味着普通区保障可能被活动 KV 和 SWA 页粒度突破，属于下一阶段需要单独解决的 admission/backpressure 问题。

## 下一步

- 保持这条 workload 作为“普通侧保护”回归测试。
- 新增普通请求重复次数，而不是简单放大普通工作集；工作集必须仍低于 request quota，避免把实验变成普通区自我淘汰。
- 单独测量 borrowed 页的产生、归还原因和回访命中，构造 request→Agent→request 的借用归还场景。
- 并发场景另设 admission/backpressure 实验，不能把全局兜底造成的跨区驱逐归因于 LRU 策略。

