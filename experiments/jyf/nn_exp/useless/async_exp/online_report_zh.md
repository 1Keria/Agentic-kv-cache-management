# LRU / 同步 MLP / 异步 MLP：实际 Serving 对比

三种策略均实际处理 2000 个请求并改变/执行真实 Full/SWA 缓存淘汰，不是 shadow 排序。同步与异步的 TP 八个 rank 的逐 eviction victim digest 和释放 token 数已核对一致。

模型 DeepSeek-V4-Flash，TP=8，mem-fraction-static=0.45，32-token decode 上限；使用相同 agent050_decode32 workload，temperature=0，seed=42，9 waves/300s，gap-scale=0.02。每组重启服务，执行相同内置预热后回放，顺序 LRU→sync→async。三组有效配置、实际 token capacity、逐请求标识和 prompt token 数已核对一致；capacity=705,280。

每组一个在线运行。这是高压、压缩间隔 workload，结果不能代表原始三小时 frozen 稳态；不同策略的延迟也会改变 session 内后续请求的实际到达时间。

| 指标 | LRU | 同步 MLP | 异步 MLP |
|---|---:|---:|---:|
| 成功请求 | 2000 | 2000 | 2000 |
| cached/prompt token % | 52.41 | 61.86 | 53.98 |
| 未命中 prompt tokens | 22,461,035 | 18,001,515 | 21,718,379 |
| TTFT p50 ms | 8400.39 | 2662.99 | 8370.96 |
| TTFT p90 ms | 35701.43 | 26477.73 | 32782.02 |
| E2E p50 ms | 16492.87 | 6600.84 | 17452.00 |
| E2E p90 ms | 48180.55 | 42085.62 | 46968.61 |
| 请求/秒 | 1.769 | 2.098 | 1.799 |
| 回放时长秒 | 1130.43 | 953.39 | 1111.67 |
| request-end 总耗时 p50 µs | 206.36 | 582.73 | 383.18 |
| request-end 总耗时 p99 µs | 2333.44 | 4600.92 | 2569.14 |
| 预测 hook p50 µs | 0.53 | 244.02 | 74.67 |
| 预测 hook p99 µs | 1.98 | 3099.80 | 396.79 |
| eviction p50 µs | 154870.95 | 111733.70 | 114568.91 |
| eviction p99 µs | 204563.15 | 201332.92 | 202844.25 |
| 实际 eviction 次数 | 3610 | 3182 | 3843 |
| 回放期 cache_finished_req 调用数（含少量健康检查） | 2002 | 2001 | 2007 |
| 使用 MLP 的 victim 选择比例 % | N/A | 7.89 | 6.94 |
| 偏离当前 LRU 的选择比例 % | N/A | 5.71 | 5.01 |
| 预测队列丢弃数 | 0 | 0 | 0 |

## 分流量类型的 token 命中率

| 流量 | LRU | 同步 MLP | 异步 MLP |
|---|---:|---:|---:|
| Agent 全部 % | 53.16 | 62.72 | 54.73 |
| Agent 非首轮 % | 53.74 | 63.43 | 55.34 |
| 普通请求 % | 13.46 | 17.11 | 15.34 |

## 本次结果的判断

异步确实降低了 request-end 预测 hook 的耗时：p50 从 244.02µs 降到 74.67µs，下降 69.4%。但本次同步组的缓存命中率和端到端延迟更好；异步组相对 LRU 的缓存收益较小，E2E p50 反而更高。不能将主线程开销下降直接等同于 serving 整体收益。
同步/异步实际使用 MLP 的 victim 选择都不足 8%，大多数选择仍回退 LRU；实际偏离当前 LRU 的选择分别为 318 和 314 次。因此，低覆盖率不能全部归因为异步队列来不及，当前合法候选覆盖、episode 失效、500-event 范围限制和整组回退规则都可能起作用。本轮没有记录每项回退原因，不能进一步确定占比。
每组只跑了一次，session 内下一轮在上一轮完成后发出，策略改变缓存后也改变到达顺序。不能仅凭这三次运行把同步/异步的命中率差归因为异步机制本身；结论限于这次固定配置的实测对比。

## 实现与口径

同步/异步使用同一个 seed_42 Unified 16→64→32→10 checkpoint、相同 20-event 条件复用概率评分、最多 16 个合法 LRU 候选。任何候选预测缺失或超过已定义 500-event 范围时，该次选择回退 LRU。
同步：request-end 构造变化且可淘汰节点的快照，批量 MLP，完成后返回。异步：同一快照入有界队列后返回，由一个 rank-0 CPU worker 推理。队列容量 4096、batch 上限 64，无凑批等待窗口。
Full/SWA 分开维护 episode。树结构变化、访问、加解锁使 ticket 失效；worker 只写旧 ticket，不覆盖新状态。request-end 使用变化节点集合，LRU rank 特征仍需扫描当时 frontier。
每次 eviction，rank 0 只读取已完成预测并广播 score map；八个 rank 使用相同冻结 map 完成本次淘汰。该操作等待 TP 通信，不等待正在运行的 MLP。保留原 SGLang allocator/free/tombstone 逻辑。
LRU 使用原始淘汰函数，不承担 MLP 和 score-map TP 广播成本；三组都有 timing 日志。表中 eviction 时间包括新策略的 score 计算与 TP 通信开销，是当前原型的真实额外成本。
cached/prompt 来自 API usage 的 cached_tokens；未命中 prompt tokens 包括首次访问的 compulsory miss，不能全部称为淘汰造成的重算。request-end 指 cache_finished_req 方法加预测 hook，不包含日志写入；按 replay meta.created_unix 过滤掉回放开始前的预热调用。
内部 finish 计数为 2002/2001/2007，比 workload 请求数多 2/1/7 次。日志没有记录 request id，无法进一步精确剔除回放期间的健康检查等额外调用；内部耗时分位数保留这些调用。API 命中率和延迟统计则严格来自相同的 2000 个 workload 请求。
TTFT 沿用 replay 脚本的首个可见 content/tool-call 时间；reasoning-only 输出可能不计首 token，解读时同时查看 E2E 和 token 命中率。吞吐是此受控到达率下的完成请求/总回放时长，不是饱和吞吐上限。

## 模型限制

当前 checkpoint 在此前 frozen eviction-frontier 数据上训练，单位是 cache-access event，而不是秒。应用到 request-end 存在观测时刻分布变化；在线 workload 与之前 frozen 实验使用相同请求集合，仅到达模式改变，不能作为独立 workload 泛化测试。三组实验回答该原型在这个固定 workload 下的实际差异。

## 文件

运行目录：`/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/async_exp/online_runs/20260912_three_arm_v1`。
每组包含 server.log、server_info.json、metrics/rank*.jsonl、replay/replay.jsonl、replay/summary.json 和 prometheus.txt。
comparison.json 为汇总；run_online.sh 为三组实验入口；test_serving_cache.py 验证真实 SWARadixCache 的 split、lock/unlock、强制非 LRU 淘汰和计数一致性。
