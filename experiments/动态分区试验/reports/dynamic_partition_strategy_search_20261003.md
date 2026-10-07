# 动态分区策略搜索记录（2026-10-03）

## 当前判断

`borrow` 仍是当前正式动态分区方案：两区保留 61/39 的硬保障，一侧低于保障时允许另一侧借用，发生全局物理压力时只优先回收 borrowed 页。Full 和 SWA 使用同一套区域规则，区内仍是 LRU。

本轮没有发现能稳定超过 `borrow` 的候选。新增候选都保留为研究对照，不改变默认启动脚本。

## 候选对照

### 全局 borrowed LRU：`borrow_global`

它在共享池压力时忽略区域优先顺序，在所有 borrowed 页中做全局 LRU。`scan_mixed_256`、`mem_fraction_static=0.40` 的结果：

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | Full/SWA 驱逐 token | 墙钟 |
|---|---:|---:|---:|---:|---:|
| `borrow` | 80.0592% | 87.0920% | 42.3610% | 59,648 / 117,504 | 70.678 s |
| `borrow_global` | 78.7162% | 85.8236% | 40.6178% | 64,256 / 127,744 | 72.110 s |

全局排序牺牲了较多 Agent 历史，拒绝作为默认方案。结果目录：`results/borrow_global_scan_20261003/`。

### 延迟补标：`borrow_reclass`

当一侧释放保障容量后，扫描树并把此前未标记的 surplus 页补标为 borrowed；实现曾分别尝试旧页优先和新尾部优先。

在 `scan_mixed_256` 上，旧页优先为 79.2369% 总体命中率、87.0920% Agent、37.1313% 普通请求；同一运行中的 `borrow` 为 80.0866%、87.5148%、40.2691%。新尾部优先为 78.7436%、85.4659%、42.7097%。补标带来的可回收空间不足以弥补 Agent 历史损失。

### 只补标普通请求：`borrow_request_reclass`

该版本只允许普通请求 surplus 页在 Agent 保障空闲时补标，Agent 页保持原有借用标签，目标是避免 Agent 历史被补标机制扰动。

在 `scan_mixed_256` 上结果为 78.2777% 总体、85.4659% Agent、39.7461% 普通请求；对应的 `borrow` 为 80.0866%、87.5148%、40.2691%。Full/SWA 驱逐为 82,432 / 145,408 token，也高于 `borrow` 的 59,648 / 117,504 token。

在 Agent 高压、普通请求较少的 132 请求闭环 workload（`mem_fraction_static=0.35`、SWA/Full=0.20）中，`borrow_request_reclass` 与 `borrow` 的命中 token 和驱逐量完全相同：

| 策略 | 总体 | Agent | 普通请求 | Full/SWA 驱逐 token | 墙钟 |
|---|---:|---:|---:|---:|---:|
| `borrow` | 87.7381% | 89.2370% | 66.0244% | 248,320 / 320,000 | 352.163 s |
| `borrow_request_reclass` | 87.7381% | 89.2370% | 66.0244% | 248,320 / 320,000 | 370.858 s |

该 workload 的严格阶段判据还显示两条普通热链的回访首条前缀均为 0 命中；这是普通热链自身超出 SWA 保障并在 Agent 压力期间被驱逐的结果。允许记录判据失败后两种策略仍完成 132/132 请求，不能把这次现象误判为服务故障。结果目录：`results/strategy_high_pressure_20261003_nonstrict/`。

## 工程修复：分区回收后的 borrowed-only fallback

服务日志显示，分区范围内没有足够可驱逐页时，allocator 原先直接调用无区域的全局 LRU fallback。例如 `borrow_request_reclass` 的日志出现 `REGION_EVICT_FALLBACK`，随后可能删除对侧受保障页，这会削弱分区保护。

当前实现已调整为：

1. 先回收请求区域的合法候选；
2. 如果策略支持借用，再从两区的 borrowed 页中回收；
3. 只有所有合法 borrowed 页不足或被锁定时，才保留最后的无区域 fallback，以保证 allocator 进度。

新增回归覆盖 hybrid Full/SWA allocator 的调用顺序。当前区域测试结果为 `32 passed`
（Classic）和 `19 passed`（SWA），合计 51 项。该改动属于回收边界修复，不改变 LRU
排序或保障比例。

在修复后的真实 serving 回归中，`scan_mixed_256`（256 请求、`mem_fraction_static=0.40`）
连续三次运行均为 256/256 请求成功，但命中率波动明显：

| 运行 | 总体 | Agent | 普通请求 | Full/SWA 驱逐 token | `REGION_EVICT_FALLBACK` | borrowed reclaim reason |
|---|---:|---:|---:|---:|---:|---|
| 第一次 | 78.2228% | 85.4659% | 39.3975% | 85,504 / 145,664 | 40 | 仅 `global_overage` |
| 第二次 | 79.8125% | 87.8074% | 36.9569% | 61,696 / 121,856 | 16 | 含 3 次 `allocator_fallback` |
| 第三次 | 80.0592% | 87.0920% | 42.3610% | 55,040 / 114,688 | 16 | 含 2 次 `allocator_fallback` |

三次总体命中率均值为 `79.3648%`，样本标准差约 `0.97` 个百分点；Agent 均值为
`86.7884%`，普通请求均值为 `39.5712%`。因此这组回归只能确认服务完整性和
borrowed-only 路径确实会被触发，不能把单次 1～2 个百分点的差异直接归因于 allocator
修复。

第二、三次运行证明新路径在确有可回收 borrowed 页时会被触发；三次结果差异也说明当前
闭环 serving 调度存在较大单次波动，不能把这些差异直接归因于修复。该回归只验证了
路径生效和服务完整性，是否改善平均命中率需要固定并发、重复多次后再判断。

## 修复后的 fixed/borrow 成对复核

在同一份 `scan_mixed_256`、`mem_fraction_static=0.40`、固定 61/39 和固定输出 16
token 下，重新启动服务依次运行 fixed 与 borrow。两组均为 256/256 请求成功、0 错误：

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | Full/SWA 驱逐 token | 墙钟 |
|---|---:|---:|---:|---:|---:|
| fixed | 79.4014% | 87.8074% | 34.3421% | 69,888 / 129,792 | 77.553 s |
| borrow | **79.8399%** | 87.8074% | **37.1313%** | 64,768 / 122,368 | **75.357 s** |

borrow 相对 fixed 多命中 `4,096` token，总体提高 `0.4385` 个百分点，普通请求提高
`2.7892` 个百分点，墙钟缩短约 `2.8%`。Agent 命中率没有变化，说明在这个容量点上
额外借用主要改善普通请求的保留；收益仍然很小，符合该 workload 压力不够高的判断。
结果位于 `results/fixed_borrow_pair_20261003/`。

## 高压 fixed/borrow 复核

使用 8 Agent、4 普通 session、`mem_fraction_static=0.35`、SWA/Full=0.20 的高压
workload，并分别测试 `max_inflight=1` 和 `max_inflight=2`。两种并发设置下两组都
完成 132/132 请求且 0 错误；命中率完全相同：总体 `89.0191%`、Agent `89.1325%`、
普通请求 `77.4555%`。borrow 将 Agent 区 Full 驱逐从 `235,008` 降至 `194,048`
token，但没有转化为额外命中；SWA 驱逐仅从 `265,472` 降至 `263,168`。两组结果的
墙钟也没有稳定收益（borrow 分别为 352.219 s 和 355.438 s，fixed 为 350.664 s
和 348.821 s）。

这说明“有更多可借用容量”本身不足以带来命中率提升：只有被保留下来的节点在后续
确实回访，收益才会出现。该结果不否定 borrow，而是把准入标准具体化为“额外保留量必须
转化为后续命中”；后续策略优化应优先构造和测量这种回访，而不是只看驱逐量下降。
结果位于 `results/high_pressure_fixed_borrow_20261003/` 和
`results/high_pressure_fixed_borrow_20261003_inflight2/`。

## `borrow_dynamic` 实验性合并

为检验“反馈调比例是否能与借用机制互补”，新增实验策略 `borrow_dynamic`。它沿用
`dynamic` 的归一化淘汰压力控制器，但在比例变化后仍按 borrowed-only 规则回收；借用
标签在比例变化后只增不撤，避免把控制动作当作新的外部压力。随后又把它的反馈限制为
只有真实 borrowed-only 回收才计入，排除区内 LRU 淘汰噪声。Classic 和 SWA 区域单测
共 53 项通过，`borrow`、`dynamic` 和 `fixed` 的默认路径没有改变。

在旧反馈口径下，首个 `scan_mixed_256` 单次回归中 `borrow_dynamic` 比 `borrow` 多命中
`5,632` token，总体、Agent、普通请求命中率分别为 `79.8399%`、`87.4497%`、
`39.0488%`，但墙钟慢约 `1.6%`，期间更新 10 次。这个局部收益不能作为替代依据。

在同一容量和参数下的完整 `request_agent_request` workload 中，`borrow_dynamic` 的
总体、Agent、普通请求命中率为 `90.0279%`、`94.6554%`、`40.4718%`，`borrow` 为
`90.3236%`、`94.9473%`、`40.8079%`；动态合并低 `0.2967` 个百分点，TTFT 均值
为 `1,504.6 ms`，高于 borrow 的 `1,099.9 ms`，控制器更新 41 次。把累计反馈阈值和
冷却提高到 `32,768` token 后，更新减少到 18 次，但总体仍为 `90.1428%`，低于 borrow
`0.1818` 个百分点，TTFT 均值仍为 `1,396.6 ms`。这表明“借用 + 频繁移动保障线”仍
会引入控制开销和工作集扰动；`borrow_dynamic` 只保留为研究对照，不进入正式策略。
过滤区内淘汰后的最新 `scan_mixed_256` 回归中，`borrow_dynamic` 总体命中率为
`78.0858%`，低于同轮 `borrow` 的 `78.4969%`；Agent 命中率相同（`85.8887%`），
普通请求从 `38.8745%` 降到 `36.2596%`，比例仍发生 5 次更新并降至 `0.5886`。
因此减少反馈噪声仍不能消除移动保障线的不可逆代价，`borrow_dynamic` 明确淘汰，
不进入正式启动脚本。结果位于 `results/borrow_dynamic_borrowed_feedback_scan_20261004/`；
旧口径结果仍保留在 `results/borrow_dynamic_scan_20261003/`、
`results/borrow_dynamic_phase_20261004/` 和
`results/borrow_dynamic_phase_threshold32768_20261004/`。

## 后续准入标准

后续候选只有在相同 trace、相同容量和至少一次高压闭环中同时满足以下条件，才考虑替代 `borrow`：

- 总体 token 加权命中率不低于 `borrow`；
- Agent 命中率不下降；
- 普通请求收益足以抵消 Agent 侧代价；
- Full/SWA 驱逐量和 TTFT 没有系统性恶化；
- 不依赖工具调用时间、turn 返回时间或离线流量比例预测。

在满足这些条件前，继续堆叠补标、全局排序或动态数学控制器没有证据支持。下一轮重点是用新的 borrowed-only fallback 重跑容量压力和阶段切换基线，并重复运行以估计波动范围。
