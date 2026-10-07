# Unified Exposure Barrier 适配实验结论

日期：2026-09-29

## 结论

将同一套 `LRU + Exposure Barrier` 语义适配到 Full 和 SWA 后，固定 trace 上出现了明确的系统收益：

- SWA-only 的额外处理 token 减少 **64.89%**；
- Full/SWA 联合压力下的额外处理 token 减少 **38.56%**；
- 联合压力下不再始终退化到只命中 512-token 共享前缀；
- 原生 LRU 与 SLRU 仍完全相同，收益来自回收前沿控制，而不是频率计数。

这验证了统一设计：策略层只有一套“初始前沿优先、同链连续回收延迟、主前沿耗尽后安全回退”的规则。Full 和 SWA 的差异只是候选表示和回收 API。

## 统一策略的工程映射

基础排序仍然使用 LRU，不使用 session ID、工具调用时间、下一轮到达预测或长期历史信用。

- **Full 路径**：删除叶子后刚暴露的父节点进入延迟集合；仍有初始叶子时不继续向父链深入。
- **SWA 路径**：回收开始时保存合法 LRU 候选及其祖先路径；本轮已经选择一条链上的节点后，该链上的其他祖先或后代候选进入延迟集合，优先选择其他独立链。
- **安全回退**：独立前沿不足以满足释放量时，继续处理延迟集合，不改变容量正确性和锁规则。

第一轮 SWA 适配中，所有压力请求都能在独立前沿阶段满足释放量，因此没有使用回退候选。这不是回退失效，而是说明当前四会话 trace 中存在足够多的独立链可供选择。

## 实验设计

继续使用相同的 27 请求冻结 trace：4 个会话、22 次续接、1 次分叉。所有 case 的输入 token 序列和事件顺序完全一致；实际生成输出不反馈到后续冻结输入。

| 压力档 | Full 容量 | SWA 容量 |
|---|---:|---:|
| Control | 32,768 | 16,384 |
| Full-only | 16,384 | 16,384 |
| SWA-only | 32,768 | 8,192 |
| Joint | 16,384 | 8,192 |

每个压力档比较原生 LRU、原生 SLRU 和统一 Exposure Barrier。结果 suite 为 `results/pilot/exposure_barrier_20260929T073410Z/`。

## 主要结果

### 1. Full-only 结果保持不变

| 指标 | LRU | Unified Barrier | 变化 |
|---|---:|---:|---:|
| 累计 cached token | 84,224 | 96,512 | +12,288 |
| 相对 control 的额外处理 token | 25,344 | 13,056 | -48.48% |
| 刚暴露祖先的未来需求损失 | 13,056 | 768 | -94.12% |
| Full overshoot | 20,736 | 9,472 | -54.32% |

SWA 适配没有改变此前已经验证的 Full 行为。

### 2. SWA-only 获得显著改善

| 指标 | LRU / SLRU | Unified Barrier | 变化 |
|---|---:|---:|---:|
| 累计 cached token | 13,312 | 75,776 | **+62,464** |
| 相对 control 的额外处理 token | 96,256 | 33,792 | **-64.89%** |
| 后续仍需求却被 SWA 回收的 token | 96,256 | 48,640 | -49.47% |
| SWA 回收次数 | 27 | 14 | -13 |
| SWA victim step | 108 | 30 | -78 |
| `swa_internal_tombstone` step | 82 | 20 | -62 |
| SWA overshoot | 55,552 | 27,392 | -50.69% |

相对 control，可保留的缓存复用比例从 12.15% 提高到 69.16%。14 个请求的 cached token 增加，没有请求变差，净增加 62,464 token。

结构证据与机制一致：LRU 在 22 次 SWA 回收中出现 132 对同一祖先链上的连续 victim；Unified Barrier 中该数字为 **0**。

### 3. Joint 压力下已经产生端到端收益

| 指标 | LRU / SLRU | Unified Barrier | 变化 |
|---|---:|---:|---:|
| 累计 cached token | 13,312 | 50,432 | **+37,120** |
| 相对 control 的额外处理 token | 96,256 | 59,136 | **-38.56%** |
| Full 后续需求损失 | 73,472 | 52,480 | -28.57% |
| SWA 后续需求损失 | 96,256 | 66,048 | -31.38% |
| Full overshoot | 45,056 | 29,952 | -33.52% |
| SWA overshoot | 64,000 | 45,056 | -29.60% |
| Full 深入同链 victim step | 17 | 4 | -13 |

相对 control，可保留的缓存复用比例从 12.15% 提高到 46.03%。8 个后半段续接请求全部改善，没有请求变差，净增加 37,120 cached token。

LRU 在 14 次联合压力 SWA 回收中出现 28 对同链连续 victim；Unified Barrier 中同样降为 **0**。这说明 Full 与 SWA 两条路径现在执行的是同一个策略原则。

## 延迟结果

本轮延迟仍是单次顺序运行，以下只作为描述性结果：

| 压力档 | 指标 | LRU | Unified Barrier | 变化 |
|---|---|---:|---:|---:|
| SWA-only | mean TTFT | 0.750 s | 0.379 s | -49.48% |
| SWA-only | p95 TTFT | 2.480 s | 1.579 s | -36.34% |
| SWA-only | mean latency | 0.989 s | 0.619 s | -37.39% |
| Joint | mean TTFT | 0.816 s | 0.477 s | -41.53% |
| Joint | p95 TTFT | 2.946 s | 2.118 s | -28.11% |
| Joint | mean latency | 1.056 s | 0.718 s | -32.03% |

缓存行为、victim 序列和额外处理 token 可以支持机制结论；延迟百分比仍需要重复运行和顺序互换后才能作为正式性能结论。

## 有效性检查

- 10 个 GPU case 全部完成。
- 所有输入 trace 完全一致。
- 所有候选集合覆盖完整，eviction begin/end 完整配对。
- 原生 LRU 与 SLRU 的 Full/SWA victim 和 cached token 仍完全相同。
- Barrier 关闭时，本轮 LRU 结果与上一轮结果一致。
- 121 项测试和 3 个参数化 subtest 通过。
- 没有观察到分配失败、OOM 或缓存结构断言失败。

机器结果：`reports/agent_unified_exposure_barrier_20260929.json`

原始结果：`results/pilot/exposure_barrier_20260929T073410Z/`

## 下一步

当前不需要继续修改策略定义。下一阶段应验证泛化性：

1. 扩展到此前冻结的 20 会话、1,206 请求 Agent-only workload。
2. 扫描多个 Full/SWA 绝对容量点，确认收益区间。
3. 至少重复运行并交换策略顺序，正式评估 TTFT、延迟和吞吐。
4. 统计独立活跃链数量不足时使用安全回退的频率和代价。
5. Agent-only 结果稳定后，再与请求分类、静态分区和动态分区组合。

当前结论是：**统一 Exposure Barrier 已从局部结构诊断升级为在 Full/SWA 联合压力下能够减少实际重算的候选策略，值得进入更大 workload 验证。**
