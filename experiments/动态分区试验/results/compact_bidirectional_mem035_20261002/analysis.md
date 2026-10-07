# 双向复用高压三方实验（2026-10-02）

- workload：`experiments/动态分区试验/data/bidirectional_reuse_compact_20261002/workload.jsonl`，223 请求（211 Agent、12 普通）。
- 模型：DeepSeek-V4 tokenizer/服务端同源消息编码；page size=256。
- 配置：`mem_fraction_static=0.35`、Agent 基准份额 0.61、`max_inflight=2`、固定输出 16 token、gap scale=0.1。
- 三组使用同一 workload 和同一回放顺序。fixed 的门槛在回访首条命中 0 时中止了 runner，但 223 个请求均已返回成功；borrow 使用只记录门槛、不中止的 replay plan 完成相同回放。

## Workload 审计

| 项目 | 结果 |
|---|---:|
| 普通终端 prompt | 2,228 / 2,225 token |
| 页对齐后普通工作集 | 2,048 token / 链 |
| 普通区 SWA 基准保障 | 6,989 token |
| 普通终端 LCP | 2,228 / 2,225 token |
| Agent prompt 范围 | 12,262～94,203 token |

普通热链确实具有可复用的 2,048 token 对齐前缀，且低于普通区 SWA 保障。

## 主结果

| 模式 | 总体命中率 | Agent 命中率 | 普通请求命中率 | Agent 冷 miss | 墙钟（s） | TTFT p50（ms） |
|---|---:|---:|---:|---:|---:|---:|
| unified | 40.1696% | 40.0989% | 61.9644% | 41.2322% | 873.50 | 1929.6 |
| fixed | 28.9250% | 28.8179% | 61.9644% | 73.9336% | 910.83 | 1967.7 |
| borrow | 41.0613% | 40.9935% | 61.9644% | 27.4882% | 877.37 | 1703.1 |

相对 unified：fixed 总体命中率 −11.2446 pp，Agent −11.2810 pp；borrow 总体 +0.8917 pp，Agent +0.8945 pp。borrow 相对 fixed 总体 +12.1363 pp，Agent +12.1756 pp。

## 普通热链回访

| 模式 | 预热后续命中 | 回访首条命中 | 回访后续命中 |
|---|---:|---:|---:|
| unified | 62.6204% | 0.0000% | 91.9829% |
| fixed | 62.6204% | 0.0000% | 91.9829% |
| borrow | 62.6204% | 0.0000% | 91.9829% |

三种模式的两条普通回访首条均为 0；回访第二、第三条均重新命中 2,048 token。当前结果不能声称分区已经保护普通热链。

## 区域证据

| 模式 | Agent Full 驱逐 | Agent SWA 驱逐 | borrowed eviction | borrowed cache（Full/SWA） | 对侧 request 驱逐 |
|---|---:|---:|---:|---:|---:|
| fixed | 5,400,576 | 5,772,288 | 0 | 0 / 0 | 4,096 / 4,096 |
| borrow | 2,104,832 | 4,775,168 | 623 | 99,584 / 9,728 | 4,096 / 4,096 |

borrow 的 borrowed 回收原因是 `global_overage`。它将 Agent 的 Full/SWA 驱逐分别从 fixed 的 5,400,576 / 5,772,288 token 降到 2,104,832 / 4,775,168 token，并把 Agent 冷 miss 从 73.93% 降到 27.49%。

## 结论

在 mem_fraction_static=0.35 的真实高压混合 workload 上，borrow 是三者最好：总体命中率 41.0613%，比 unified 高 0.8917 个百分点，比 fixed 高 12.1363 个百分点；Agent 命中率比 unified 高 0.8945 个百分点，比 fixed 高 12.1756 个百分点。

该 workload 中 fixed 和 borrow 都没有保住普通热链回访的首条 2048 对齐 token；两条回访首条命中均为 0，后续两条重新建立后命中 2048。说明当前实现尚未证明普通区的跨 Agent 压力保护。

fixed/borrow 的 request 区都在 Agent 压力阶段发生一次 4,096 token Full/SWA 驱逐，即使请求区保障容量仍远大于 2,048 token 工作集。这指向当前 allocator 的全局物理回收兜底或跨 Full/SWA 回收路径，而非 workload 没有复用；需要先修复严格保护语义，再评价双向动态分区。

下一步应围绕“全局兜底回收不能驱逐未超额的对侧保障页”做最小修复，并用同一 workload 重跑；同时保留 borrow 的 Agent 侧结果作为容量借用收益证据。
