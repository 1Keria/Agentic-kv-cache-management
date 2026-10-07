# 动态分区：最低保障、弹性池与实际重算反馈（2026-10-05）

本轮验证的是混合请求下的 `elastic` 动态分区。策略保留两类请求的最低保障，把剩余容量作为共享弹性池；借用区只按固定 token 粒度切分。缓存节点被回收后，bounded ghost 只保留 page 对齐的前缀指纹，后续请求若因该回收产生额外重算，就给对应借用节点增加保护分数。保护只作用于借用区回收，区域内部仍使用原生 LRU。它使用已经发生的回收和重算事实，不读取工具调用时间、turn 返回时间或离线流量比例。

Full 和 SWA 分别维护 ghost 元数据，但使用相同参数、门槛和排序规则。节点发生 radix split 时清除旧指纹，避免结构变化后保护错误后缀。

## 候选配置

```text
request_cache_region_policy=elastic
request_agent_cache_ratio=0.50              # 冷启动参考点，不是流量预测
request_cache_agent_min_ratio=0.20          # Agent 最低保障
request_cache_agent_max_ratio=0.80          # 普通请求最低保障为 1-0.80
request_cache_elastic_activity_window=32
request_cache_elastic_preferred_reclaim=true
request_cache_elastic_soft_step=0.1
request_cache_borrowed_segment_tokens=1024
request_cache_elastic_ghost_capacity_tokens=1048576
request_cache_elastic_ghost_pressure_decay=0.995
request_cache_elastic_ghost_protect=true
request_cache_elastic_ghost_protect_min_tokens=1024
request_cache_elastic_ghost_reclaim=false
request_cache_elastic_feedback=false
```

`elastic_feedback` 是按区域总驱逐量移动软比例的另一条控制路径，本轮保持关闭；实际重算反馈由 ghost 保护路径使用。此前短压力轨迹中直接打开比例反馈的结果较差（总体命中率约 34.9%–37.2%，额外重算约 4.74M–4.94M token），说明当前应优先使用节点级、回收后的事实反馈，不让比例控制器过快改变共享边界。

活动窗口有一个明确的冷启动保护：当只有一类请求在最近 32 个分类请求内出现时，保留中性的 50/50 返回保障；只有两类都近期活动时，才把两侧保障线放宽到 20%/20%，其余 60% 作为共享弹性池。这个 50% 是固定的中性起点，不是从离线流量比例预测出来的；最终普通请求回访后，状态中的 `base_full_capacity_tokens` 回到约 20%/20%。

## 受控实验

Workload 为 `experiments/动态分区试验/data/bidirectional_reuse_short_phased_20261001`，227 个请求，7 个 Agent session 并行压力，普通请求 warm/return，`gap_scale=0.1`、固定生成 16 token、最大并发 2、`mem_fraction_static=0.35`、TP=8。所有有效运行均使用经典 Radix/SWA 实现、同一模型、同一 workload 和同一启动参数。请求命中率在该 workload 中稳定为 77.2283%，所以收益主要来自 Agent 历史保存。

| 配置 | 有效运行数 | 总体命中率 | Agent 命中率 | 普通命中率 | 额外重算 token | 墙钟 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 无 ghost，2048 分段 | 2 | 46.0181% ± 3.382 个百分点 | 45.8093% ± 3.405 个百分点 | 77.2283% | 4,024,320 ± 277,684 | 562.9 s | 1,681.2 ms |
| ghost 保护，2048 分段 | 2 | 52.0327% ± 0 | 51.8642% ± 0 | 77.2283% | 3,531,008 ± 0 | 568.2 s | 1,756.0 ms |
| **ghost 保护，1024 分段** | **3** | **54.6959% ± 0.439 个百分点** | **54.5452% ± 0.442 个百分点** | **77.2283%** | **3,311,445 ± 37,109** | **578.8 s** | **1,813.3 ms** |

均值差异：

- 1024+ghost 相对无 ghost 基线总体命中率提高 **8.678 个百分点**，额外重算减少 **712,875 token（17.71%）**。
- 1024+ghost 相对 2048+ghost 再提高 **2.663 个百分点**，额外重算再减少 **219,563 token（6.22%）**。
- 相对 2048+ghost，墙钟增加约 **1.86%**，TTFT p50 增加约 **3.26%**；1024 的三次运行结果比无 ghost 基线稳定得多。

三次 1024+ghost 的总体命中率分别为 54.8846%、55.0090%、54.1941%，额外重算分别为 3,297,024、3,283,712、3,353,600 token。差异来自并行请求的完成顺序，但方向一致。

## 反馈是否真的被使用

在三次 1024+ghost 运行结束时，单个缓存实现的 ghost 元数据约 323K token、约 1,263 条记录，低于 1,048,576 token 上限。Agent 侧衰减压力约 3.29M–3.34M token，普通请求侧约 3.2K token；这与 Agent 压力阶段的额外重算来源一致。Full/SWA 都记录回收和回访，且各自索引隔离，避免跨 attention 池误保护。

策略并没有减少所有回收，而是把借用尾部拆成 1024 token 的可回收单位，并在已有回访证据的节点上延后回收。因此收益来自减少一次回收连带删除的后缀范围，以及把真实重算过的节点从下一轮借用候选中暂时排后。`ghost_reclaim=false` 保留了简单的区域回收顺序；本 workload 的普通请求回访压力不足以证明更复杂的跨区域压力排序有益。

## 工程修复与验证

实验启动脚本现在在启用请求区域时强制使用经典 Radix/SWA backend。这样即使外层环境继承 `SGLANG_ENABLE_UNIFIED_RADIX_TREE=1` 或 C++ radix tree 开关，也不会在区域缓存尚未支持的实现上启动失败。对应修改在 [`scripts/shell/v4flash.sh`](/mnt/dai-sys/zhoulongsheng/agentkv/scripts/shell/v4flash.sh:62)。

相关 Full/SWA 单元测试结果为 **79 passed, 19 warnings**；shell 脚本通过 `bash -n`。GPU 运行中有四个失败目录被保留但不计入均值：前三个因外部 VLLM 占用 GPU，第四个因 unified radix tree 不支持区域缓存；修复后第三次有效复核顺利完成。

## 结论

当前可以保留“20% 最低保障 + 共享弹性池 + 1024 token 借用尾部分段 + 请求级 bounded ghost 重算保护”作为动态分区候选。它在三次有效复核中相对无 ghost 基线稳定减少约 17.7% 的额外重算，相对 2048+ghost 还有约 6.2% 的额外重算下降，同时普通请求命中率没有下降。

1024 的代价是 TTFT p50 比 2048+ghost 高约 3.3%。如果后续 workload 对尾延迟更敏感，保留 2048+ghost 作为保守版本；若当前目标是压力下的总重算和 Agent 命中，1024 是更好的候选。下一阶段应在更长、不同 Agent/普通比例的 workload 上做同参数复核，再决定是否把它写入正式默认配置；不应把这条短轨迹的数值直接当作统计显著的通用结论。

结果 JSON：[`dynamic_partition_ghost_protection_20261005.json`](/mnt/dai-sys/zhoulongsheng/agentkv/experiments/evicition_policy/reports/dynamic_partition_ghost_protection_20261005.json)
