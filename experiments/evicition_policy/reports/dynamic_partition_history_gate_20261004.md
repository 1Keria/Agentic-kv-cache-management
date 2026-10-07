# 动态分区历史门控策略实验记录（2026-10-04）

本轮目标是减少 elastic soft-tier 在短暂的单类切换中误伤活跃 Agent 续接，同时保留长期混合流量的共享池收益。策略仍由同一个 region 控制器同时驱动 Full 和 SWA。

实现位于：

- `Engine/sglang/python/sglang/srt/mem_cache/radix_cache.py`
- `Engine/sglang/python/sglang/srt/mem_cache/swa_radix_cache.py`

## 当前策略

1. `elastic_activity_window=32` 仍只使用在线观察到的分类请求访问 epoch 判断某一类是否暂时 inactive。
2. inactive 时恢复配置的固定保障比例，避免空闲类别的 return reserve 被当前 burst 立即吞掉。
3. soft-tier 是否启用增加历史门控：如果 stale 类累计访问数少于一个 activity window，则关闭 soft-tier，按 borrow 的普通 LRU 回收；累计访问达到一个 window 后重新允许 soft-tier，以保留混合流量中已有历史的共享前缀。
4. Full/SWA 共享同一访问历史、stale 判断和 reclaim order；SWA 只在 Full/SWA 两个池中分别执行同一顺序。
5. 新增 `elastic_region_access_count`、`elastic_preferred_reclaim_active` 诊断字段，便于解释每次切换。

该门控不读取工具调用时间、turn 返回时间，也不需要离线统计 workload 比例。

## 受控结果

| 流量和策略 | 总体命中率 | Agent 命中率 | 普通命中率 | cached token | Full/SWA 驱逐 token |
|---|---:|---:|---:|---:|---:|
| short borrow | 39.48% | 39.28% | 70.43% | 3,240,960 | 2,455,296 / 4,920,064 |
| short elastic（历史门控） | **45.52%** | **45.36%** | 70.43% | **3,737,088** | 2,041,600 / 4,423,424 |
| mixed_scaled elastic（历史门控） | 90.17% | 94.61% | **42.59%** | 8,040,704 | 294,400 / 687,616 |
| request-agent-request elastic（历史门控） | 89.72% | 94.72% | 36.07% | 8,000,256 | 317,696 / 728,064 |

短 Agent 压力流量中，历史门控复现了活动门控的收益：相对 borrow，Agent 命中率提高约 6.08 个百分点，cached token 增加 496,128，Full/SWA 驱逐均下降。

长 mixed 的单次结果存在 GPU 调度和请求交错带来的波动。已有同 trace 的最好 elastic 结果为 90.48% 总体、95.09% Agent、41.11% 普通；本轮历史门控为 90.17% 总体、94.61% Agent、42.59% 普通，说明它改善了普通请求侧的保留，但尚未稳定超过最好总体命中率。此前简单 activity gate 为 90.06% 总体、94.73% Agent、40.10% 普通，历史门控在普通侧更好。

## Shadow 额外重算

shadow 使用无限输入前缀索引，只把实际命中低于 shadow 命中的部分计为容量淘汰可能造成的额外重算；混合 replay 没有生成 token，因此 coverage gap 单独保留。

| 流量 | 分组 | shadow h_inf | 实际 cached | 额外重算 |
|---|---|---:|---:|---:|
| short | agent | 7,755,264 | 3,699,456 | 4,061,440 |
| mixed_scaled | agent | 7,755,264 | 7,716,352 | 47,360 |
| mixed_scaled | request | 326,656 | 324,352 | 2,560 |
| request-agent-request | agent | 7,755,264 | 7,725,568 | 37,632 |
| request-agent-request | request | 326,656 | 274,688 | 51,968 |

这说明正式 mixed 流量中的 Agent 前缀大部分已经接近 shadow 上限，剩余损失集中在少量切换和普通请求侧；短 Agent-only 流量则仍然是容量严重不足的压力场景，适合继续评估 Agent 区专用策略。

## 结论和下一步

当前应保留历史门控作为 elastic 的候选实现，不再继续增加基于时间预测的逻辑。它已经解决了短 Agent burst 中 soft-tier 误回收的问题，并且在 mixed 流量中减少了对普通请求的伤害；总体收益是否超过 borrow 仍需要多次同配置重复运行后用均值和方差确认。

下一步优先做两件事：

1. 对 `short`、`mixed_scaled`、`request-agent-request` 各重复 3 次，固定同一 GPU、seed 和 replay 配置，报告均值、标准差和 shadow 额外重算。
2. 若 mixed 的额外重算已经接近 shadow 上限，停止继续堆叠淘汰启发式，转向评估动态分区本身的容量预算和 Full/SWA 共享池大小；只有在 shadow gap 仍显著时，才继续修改回收顺序。
