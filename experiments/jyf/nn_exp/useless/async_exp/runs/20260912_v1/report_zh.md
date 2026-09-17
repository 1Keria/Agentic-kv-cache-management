# 异步 Prediction Worker 实验报告

实验目录：`/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/async_exp`。

## 结论与实验范围

这轮 CPU 机制实验支持 request-end → enqueue → return：32 node/request、每 1ms 注入一批时，同步主线程 p50 为 286.84µs，异步为 59.71µs，下降 79.2%。
预测变慢或队列满时主线程继续返回，代价是预测未就绪和 LRU 回退；它并不保证 worker 永远跟得上。
排序收益不一致：Full 的 shadow regret 改善，SWA 的 token regret 变差，不能据此宣布 NN eviction 整体优于 LRU。

**这不是在线 SGLang A/B，也不是 stateful KV cache replay。没有运行真实 decode，没有测 TTFT、吞吐或 KV hit rate。** 主线程延迟是 Python 原型的 episode 快照/入队路径开销，不包含真实 radix 状态维护与 feature 原始元数据采集。
现有 trace 只有 eviction frontier 快照，没有完整 unlock lifecycle；所以这里的入队时刻和间隔是受控构造，不冒充真实 request-end。

## 沿用的历史成果

参考项目任务《mlp探讨与初步设计》《feature选取》，使用 Frozen frontier 和已有 Unified K=10 模型。

- checkpoint：`/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/uniform_mlp_exp/k10/checkpoints/seed_42.pt`，单个 seed=42，16→64→32→10，共 3,498 参数。
- trace：`/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/cold_predictor_exp/runs/20260911_cold_frontier_agent050_frozen_v1/frontier_trace/frontier_pid3797866_140187773175760.jsonl`。只选一个 TP rank，避免重复统计。
- 692 次 frontier，29,885 个候选 exposure，最后 cache-access event=2057。
- 10 桶单位仍是 cache-access events：(0,1]、(1,2]、(2,5]、(5,10]、(10,20]、(20,50]、(50,100]、(100,200]、(200,500]、(500,+∞)。
- checkpoint 输出 softmax 概率；转成前 9 个有限桶的条件 hazard，以分段常数 hazard 计算复用概率 1−S(age+H)/S(age)。超过 500 events 没有尾部 rate 定义，直接 LRU，不臆造尾部。
- 这验证了插值实现，没有新增证据证明 eviction-snapshot 模型可直接用于 unlock 时刻。秒级模型仍需秒级 lifecycle 标签。

## 原型行为

`predictor.py` 提供 Node、episode Ticket、有界 Queue、Prediction Worker 与 choose_candidate。主线程复制平坦原始元数据快照，worker 构造 16 维 feature、标准化、批量推理并发布不可变 Result。
node 每次重新进入 episode、被重新引用、删除或结构变化时，由 serving owner 替换/失效 ticket；worker 只发布到收到的 ticket，因此旧计算不会覆盖新 episode。此接口尚未接到真实 SGLang lifecycle hook。
队列使用 put_nowait；其短 mutex 只保护队列操作，不包住 feature 构造或 MLP。worker 不等待凑满 batch，只取当时可用项；最大 batch 默认 64。队列满则丢弃该次预测。
eviction 输入是已经合法、按 LRU 排列的 shortlist；全部结果有效时向量化插值并选择最低概率，否则选第一个 LRU。没有 queue.join、worker.join 或 MLP 调用。join 只发生在测量结束后的清理。
CPU Python/GIL、对象分配与 OS 调度仍会带来干扰，因此这是不等待推理的控制流保证，不是主线程硬实时延迟保证。

## 实验 A：正常负载主线程开销

每个配置 300 个合成 request-end，3 次重复（41/42/43 控制 feature 采样，模型固定 seed=42）。每次重复打乱策略执行顺序；表中 p50/p99 是三次对应分位数的中位数，并非合并后的分位数。OMP/MKL/OpenBLAS/PyTorch 都限制为单计算线程。

| node/request | 同步 p50 µs | 异步 p50 µs | 同步 p99 µs | 异步 p99 µs | 异步 1ms 就绪率 | 丢弃率 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 57.45 | 7.44 | 98.62 | 12.01 | 100.00% | 0.00% |
| 8 | 116.47 | 21.44 | 231.48 | 28.43 | 100.00% | 0.00% |
| 32 | 286.84 | 59.71 | 579.01 | 147.94 | 97.00% | 0.00% |
| 128 | 1146.96 | 221.67 | 1498.41 | 445.20 | 0.24% | 36.83% |

就绪率分母包含被丢弃的 node；时间从该次 request-end 返回之后算，不在 serving 内等待。128 node/ms 已超过这个 Python worker 的处理能力，不能把低入队延迟理解成高预测覆盖率。
LRU 计时基线只是没有预测工作的空路径，不是实际 LRU eviction 端到端延迟。

## 实验 B：慢推理与队列过载

32 node/request、1ms 间隔；有延迟时 queue capacity=256，无额外延迟时 capacity=4096。延迟为每个 inference batch 的 sleep 注入，不模拟 CPU 忙算。

| 额外 batch 延迟 | 同步 p50 µs | 异步 p50 µs | 异步 p99 µs | 5ms 就绪率 | 丢弃率 |
|---:|---:|---:|---:|---:|---:|
| 0ms | 286.84 | 59.71 | 147.94 | 99.78% | 0.00% |
| 1ms | 1338.45 | 52.68 | 154.83 | 89.40% | 6.56% |
| 10ms | 10353.53 | 52.79 | 299.73 | 0.00% | 79.22% |

无间隔 burst、capacity=256 时，异步 p50=50.95µs，丢弃率=96.67%。此测试证明队列过载时返回，不证明 burst 中仍能获得预测收益。

## 实验 C：batch 上限

32 node/request、1ms 间隔。这里是可用项即时合批，不设置额外 batch 等待窗口。

| 最大 batch | 主线程 p50 µs | 1ms node 就绪率 | 5ms node 就绪率 | 丢弃率 |
|---:|---:|---:|---:|---:|
| 1 | 57.20 | 0.16% | 1.53% | 9.90% |
| 16 | 58.22 | 93.17% | 94.72% | 0.00% |
| 64 | 59.71 | 97.00% | 99.78% | 0.00% |
| 128 | 56.60 | 94.67% | 96.62% | 0.00% |

batch=1 明显容易积压；16/64/128 在此负载下更合适。这不是最优 batch 的普适结论，结果受快照 Python 开销和任务调度影响。

## 实验 D：eviction 读取与插值

预先构造合法 shortlist，无并发 worker；每项 3,000 次调用。包含有效性检查、NumPy 插值和 argmin，不含候选枚举、释放 KV 或 TP 通信。

| 候选数 | pending/LRU p50 µs | ready/插值 p50 µs | ready p99 µs |
|---:|---:|---:|---:|
| 1 | 0.60 | 24.40 | 27.08 |
| 8 | 0.77 | 29.44 | 32.62 |
| 16 | 0.84 | 34.99 | 38.48 |
| 32 | 1.06 | 44.16 | 48.28 |
| 64 | 1.58 | 62.58 | 67.34 |
| 128 | 2.48 | 98.55 | 104.52 |

现场插值无需后台更新，但也不是零成本。若一个 eviction 连续释放很多 node，应避免每选一个 victim 都重复转换整个 shortlist。

## 实验 E：真实 frontier 的 held-out shadow 排序

沿用训练代码的 digest test split（hash bucket≥85），各 Full/SWA snapshot 取最老的最多 16 个 test candidate，至少两个才评估；只保留距 trace 末尾至少 100 events 的时刻。不是独立 workload，也不按 exposure 做独立显著性检验。
每个 snapshot 只假设选一个 victim，评分为未来 20 events reuse probability。node regret 是选中 node 后 20 events 内出现 demand 的比例；token regret 是这些 node 的 token 占全部选中 token 的比例。它们不是实测 cache hit rate。

| Frontier | 决策数 | LRU node regret | MLP node regret | LRU token regret | MLP token regret |
|---|---:|---:|---:|---:|---:|
| full | 211 | 19.91% | 8.06% | 19.50% | 8.93% |
| swa | 634 | 38.17% | 30.91% | 48.99% | 51.91% |

异步另开实际 worker，用 1ms 的受控 snapshot 间隔提交，记录完成时间，回溯在指定 deadline 是否可用。deadline 不是主动 sleep 等待预测，也不是从原始 trace 测得的 unlock-to-eviction 时间。异步排序读取 worker 实际输出，并与同步输出做数值一致性检查。

| 返回后的假设 eviction 时刻 | Full 整组就绪 | SWA 整组就绪 |
|---:|---:|---:|
| 0ms | 0.00% | 0.00% |
| 0.1ms | 72.04% | 23.03% |
| 0.5ms | 100.00% | 99.68% |
| 1ms | 100.00% | 100.00% |
| 5ms | 100.00% | 100.00% |

## 补充：相同最小释放 token 预算

每组以 LRU 首个 node 的 token 数为最小目标。MLP 按分数依次选，直到达到这个相同目标；node 不可拆分，允许超额，完整报告超额量。仍然只在固定 frontier 上选，不模拟树变化和后续缓存轨迹。

| Frontier | LRU regret tokens | MLP regret tokens | LRU regret/释放 | MLP regret/释放 | MLP 超额释放 |
|---|---:|---:|---:|---:|---:|
| full | 25,856 | 20,992 | 19.50% | 13.14% | 20.46% |
| swa | 625,664 | 856,064 | 48.99% | 50.13% | 33.71% |

Full 仍改善，SWA 仍未改善，并有更多超额释放。当前简单 P(reuse) 排序不能保证 token/byte 成本收益，尤其不能从 node regret 的下降直接推导 KV 命中率提升。

## 正确性与下一步边界

并发测试用事件屏障将 worker 卡在 inference 内，确认入队、队列满返回、eviction/LRU 读取均已返回；随后重新创建同一 node episode，释放屏障，确认旧预测不会被读取。另验证 feature 快照不可被外部原字典修改、失效后不可读，以及条件 hazard 插值和未定义尾部回退。

在线接入仍需：完整的 add/split/re-lock/unlock/delete 生命周期维护；Full/SWA 分开的合法性与 episode；秒级 unlock 数据；TP rank 一致的 victim 选择。现有部署 TP=8，如果各 rank 按自己的异步完成时刻独立决策，可能选出不同 victim，不能直接把当前单进程原型挂上去。
可行方向是在既有调度通信中分发统一决策或统一可用预测版本，并测这部分额外开销；本轮未实现或验证。

原型验证的是异步机制与静态排序效果。要回答真正的命中率/TTFT收益，仍需后续在线 A/B 或完整 stateful replay。

## 复现与原始结果

在目标目录运行 `bash run_all.sh <新的run目录名>`。脚本只使用 CPU，不改共享 SGLang 安装。
- `predictor.py`：原型实现。
- `test_predictor.py`：确定性并发与插值测试。
- `run_experiment.py`：三次重复 timing 与 shadow 排序。
- `additional_experiment.py`：eviction 开销与最小预算对照。
- `runs/20260912_v1/results.json`、`additional_results.json`：完整测量。
- `shadow_decisions.jsonl`、`equal_minimum_tokens_decisions.jsonl`：逐决策记录。
- `source_sha256.json`：最终源文件 hashes；模型/trace hashes 和运行环境已记录在 results.json。
