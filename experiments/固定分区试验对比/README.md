# 固定分区试验对比

本目录集中保存“统一 KV Cache 与固定容量分区”的快速验证数据、构造脚本、运行入口和结果。

完整 `data/` 和 `results/` 已保存到私有 Hugging Face 数据集 `1Keria/agentkv-runtime` 的同名路径。GitHub 只保留代码、冻结数据的小型 manifest、离线选择摘要和本文结论；恢复命令见 [`docs/数据与模型迁移.md`](../../docs/数据与模型迁移.md)。

## 试验目标

在同一份冻结混合流量上，只进行两次完整 GPU 回放：

1. 原始统一 RadixCache + LRU；
2. Agent/普通请求固定分区，使用离线选择出的 Agent 缓存容量比例，区域内仍使用 LRU。

当前数据只包含 OpenHands 和 WildChat。GLM 不参与比例选择，留作后续真实线上流量验证。

## 目录结构

```text
experiments/固定分区试验对比/
├── data/token_balanced_openhands_wildchat/  # 冻结 workload 与选择依据
├── scripts/                                 # 数据构造、启动和回放入口
└── results/                                 # 后续离线比例选择和两次 GPU 结果
```

## 数据构成

- OpenHands：7 个 Session、211 次调用；
- WildChat：548 个 Session、1,050 次调用；
- 两类 Session 最后一轮 prompt token 合计均为 385,107；
- 调用次数不做均衡，因为分区按 KV token 容量划分；
- 6 个混合波次覆盖 30 分钟，Session 内等待最多 30 秒；
- prompt 内容和 Session 边界保持不变。

详细选择依据和哈希见 `data/token_balanced_openhands_wildchat/spec.json` 与
`data/token_balanced_openhands_wildchat/manifest.json`。

## 使用入口

默认模型与服务端：

```text
MODEL_PATH=/inspire/hdd/global_public/public_models/deepseek-ai/deepSeek-V4-Flash
SGLANG_BIN=experiments/固定分区试验对比/scripts/sglang_venv.sh
```

该包装器固定使用共享虚拟环境
`/inspire/hdd/project/inference-chip/czxs25240022/.venvs/agentkv-v4flash`，避免执行
节点切换时全局 `/usr/local` Python 包发生变化。服务端、回放客户端、离线比例
选择器和结果比较器均使用同一个虚拟环境。

当前离线扫描使用实际启动后的 Full KV 容量 695,552 token、滑动窗口 KV
容量 69,376 token，在 `0.05`–`0.95` 之间以 `0.01` 步长搜索，得到当前最优
Agent 缓存容量比例 **0.61**。该比例表示 Full KV 与滑动窗口 KV 两个缓存池
都将 61% 容量固定分配给 Agent 请求，其余 39% 分配给普通请求。

比例选择优先最大化全部请求的页对齐 prompt 命中 token；若结果相同，再依次
比较两类流量中的最低命中率、Full/SWA 驱逐量和与 0.5 的距离。当前离线结果为：

- 总体页对齐 prompt 命中率：91.8813%；
- Agent 请求命中率：95.3417%；
- 普通请求命中率：48.8436%。

详细结果见：

```text
results/offline_ratio_selection.json
results/offline_ratio_selection.md
results/selected_ratio.env
```

重新构造数据：

```bash
bash experiments/固定分区试验对比/scripts/build_workload.sh --overwrite
```

启动统一缓存服务：

```bash
MODEL_PATH=/path/to/model \
  bash experiments/固定分区试验对比/scripts/start_unified_server.sh
```

启动固定分区服务：

```bash
MODEL_PATH=/path/to/model \
AGENT_CACHE_CAPACITY_RATIO=<离线选出的比例> \
  bash experiments/固定分区试验对比/scripts/start_partitioned_server.sh
```

回放冻结流量：

```bash
bash experiments/固定分区试验对比/scripts/replay_workload.sh
```

单独重新选择容量比例：

```bash
bash experiments/固定分区试验对比/scripts/select_agent_cache_capacity_ratio.sh
```

正式运行前只做环境预检：

```bash
bash experiments/固定分区试验对比/scripts/run_experiment.sh --preflight-only
```

一键运行两次配对 GPU 实验：

```bash
bash experiments/固定分区试验对比/scripts/run_experiment.sh
```

该入口按以下顺序执行：

1. 校验模型、分类器、workload 哈希、端口和 8 张 GPU；
2. 启动统一缓存 V4 Flash 服务，从实际服务提取 Full/SWA 双池容量；
3. 使用实际容量重新扫描并写入选中比例；
4. 回放统一缓存实验，保存回放结果和 `/server_info`；
5. 完全停止服务并等待 GPU 释放；
6. 使用相同模型、调度和容量参数启动固定分区服务；
7. 回放同一份冻结 workload，保存区域占用与驱逐统计；
8. 生成 `comparison.json` 和 `comparison.md`。

实验结果写入 `results/runs/<UTC 时间>/`，不覆盖已有运行。

两次正式回放必须保持模型、GPU、KV 总容量、请求顺序、到达时间和调度参数一致。

快速验证默认使用 `MEM_FRACTION_STATIC=0.45` 并设置 `DISABLE_CUDA_GRAPH=1`：
当前容量已经能产生明显缓存压力，禁用 CUDA Graph 可避免 V4 Flash 首次启动时
长时间的图捕获和 DeepGEMM JIT 预编译。该开关会同时作用于统一缓存和固定分区服务，
保证两次实验的推理启动参数一致。如需恢复 CUDA Graph，可显式设置
`DISABLE_CUDA_GRAPH=0`。

冻结 workload 的 prompt、Session 边界、请求顺序和到达时间不变，但每次生成上限
由 256 降为 208 token。原 256-token 版本的统一缓存预跑已完成 1,259/1,261 个请求，
仅最后一个 69 轮 OpenHands 会话的 2 个请求被 3,600 秒上限截断。
208-token 上限保留全部 1,261 个请求，同时为最长会话减少 2,223 个最大生成 token，
用于把单次回放控制在约 1 小时内。

两次服务固定使用 `SERVER_RANDOM_SEED=42`，回放开启固定生成长度：忽略 EOS
和 stop 条件，每个请求都生成 workload 中指定的 `max_tokens`。最终对比会强制校验
两轮的成功数、失败数、prompt token 总数和 completion token 总数完全一致；
任一字段不一致都不会生成有效结论。

`20260923_135408_paired_cap224` 虽然两轮都成功完成，但两次服务随机种子不同，
且自然停止导致 completion token 总数相差 664，因此只作为无效预跑保留，
不用于报告固定分区收益。

而缩小 KV Cache 不会缩短冻结流量的 30 分钟到达窗口。每次回放默认最多运行
3,600 秒；超时或其他失败时仍保留已有日志、服务信息和 `run_status.env`。
统一缓存实验结束后，脚本会等待 GPU 计算进程和服务端口完全释放，再重新启动
固定分区服务，并校验两次实际 Full/SWA KV 容量完全一致。

离线扫描使用历史真实 TTFT，并按 completion token 截断比例缩放历史 decode
时间来恢复 Session 闭环顺序；它不模拟新策略引起的排队变化和并发锁。正式启动时会从
统一缓存服务日志重新提取实际 Full/SWA 容量，并自动重新扫描一次比例。

## 2026-09-23 正式受控实验结论

有效运行目录：

```text
results/runs/20260923_162342_paired_controlled_cap208/
```

两轮均完成 1,261/1,261 个请求，0 错误；prompt token 总数均为
8,917,410，completion token 总数均为 217,095，服务随机种子均为 42。
因此该运行通过控制变量验收，可用于当前快速验证结论。

固定 61% Agent / 39% 普通请求容量分区相对于统一缓存的主要结果：

- 总体 token 加权命中率从 87.2347% 变为 87.0940%，降低 0.1407 个百分点；
- Agent token 加权命中率从 91.7174% 变为 91.7488%，提高 0.0314 个百分点；
- 普通请求 token 加权命中率从 39.2280% 变为 37.2448%，降低 1.9832 个百分点；
- 总体 TTFT p50 降低 1.08%，p90 降低 17.74%，但 p99 上升 0.19%；
- Agent TTFT p90 降低 3.72%，普通请求 TTFT p90 降低 51.70%；
- 墙钟时间上升 0.12%，请求吞吐下降 0.11%，可视为基本持平。

因此，当前实验支持的结论是：**固定分区已能正确实现两类流量的缓存隔离，
并且在这份压力流量上显著改善了 p90 TTFT；但它没有提高总体缓存命中率，
且牺牲了普通请求的命中率。** 因此这是“隔离与尾延迟优化”的正向快速验证，
不是“所有指标全面优于统一缓存”的证明。

当前若要继续接入固定分区，建议仍使用离线选出的 **0.61** 作为快速原型默认值，
但将目标明确定义为保护两类流量的 p90 尾延迟，而不是追求最高总命中率。
在进入动态分区前，下一步应先做 AB/BA 顺序交换和至少 3 组重复，判断 p90 改善是否稳定；
同时在 0.55–0.62 附近加密扫描，查找尾延迟收益与普通请求命中率损失之间的更好平衡点。

## 2026-09-24 CUDA Graph 完整实验结论

完整实验已经完成，结果目录为：

```text
results/full_runs/20260924_034634_cuda_graph_warm_balanced_4pairs/
```

机器可读汇总和表格汇总分别位于：

```text
results/full_runs/20260924_034634_cuda_graph_warm_balanced_4pairs/full_experiment.json
results/full_runs/20260924_034634_cuda_graph_warm_balanced_4pairs/full_experiment.md
```

本次按照 `AB / BA / BA / AB` 顺序完成 4 组配对、8 次正式回放，其中 A 为统一缓存，
B 为 61% Agent / 39% 普通请求固定分区。所有正式回放均满足以下控制变量：

- 每次均完成 1,261/1,261 个请求，错误数为 0；
- 每次 prompt token 总数均为 8,917,410，completion token 总数均为 217,095；
- 模型均为 `deepSeek-V4-Flash`，TP=8，随机种子为 42；
- `MEM_FRACTION_STATIC=0.45`，Full KV 容量为 695,552 token，SWA KV 容量为 69,376 token；
- Decode CUDA Graph 全部开启，最大 batch size 为 96；Prefill CUDA Graph 全部关闭；
- 每次策略切换均先完全停止旧服务，再启动新服务。

### 四组汇总结果

固定分区相对于统一缓存的主要均值变化如下：

| 指标 | 统一缓存均值 | 固定分区均值 | 相对变化均值 | 四组范围 | 95% Student t 区间 |
|---|---:|---:|---:|---:|---:|
| 总体 token 加权命中率 | 89.98% | 90.35% | +0.41% | +0.18% 至 +0.67% | -0.01% 至 +0.83% |
| Agent token 加权命中率 | 94.74% | 95.10% | +0.39% | 0.00% 至 +0.77% | -0.32% 至 +1.09% |
| 普通请求 token 加权命中率 | 39.06% | 39.46% | +1.18% | -3.39% 至 +5.20% | -6.00% 至 +8.36% |
| 总体 TTFT p50 | 158.90 ms | 159.91 ms | +0.62% | +0.05% 至 +1.50% | -0.40% 至 +1.64% |
| 总体 TTFT p90 | 376.96 ms | 372.84 ms | -0.44% | -7.55% 至 +3.31% | -8.23% 至 +7.35% |
| 总体 TTFT p99 | 3,138.90 ms | 3,163.79 ms | +1.21% | +0.25% 至 +3.54% | -1.27% 至 +3.70% |
| Agent TTFT p90 | 464.88 ms | 459.45 ms | -1.09% | -4.60% 至 +6.63% | -9.38% 至 +7.20% |
| 普通请求 TTFT p90 | 326.56 ms | 320.61 ms | -1.31% | -5.04% 至 +0.16% | -5.28% 至 +2.66% |

总体命中率的绝对提升为 **0.3674 个百分点**，并且四组实验全部为正向变化，
说明固定分区在当前 workload 上对总体缓存命中率具有较稳定、但幅度较小的收益。
Agent 命中率四组均未下降，但后两组几乎持平；普通请求命中率前两组下降、后两组上升，
因此不能认为固定分区会稳定改善或稳定损害普通请求命中率。

延迟结果不稳定。总体 TTFT p90 的四组相对变化分别为
`+0.34% / -7.55% / +3.31% / +2.13%`，只有一组显著改善，均值改善主要由这一组驱动；
Agent 与普通请求 TTFT p90 也存在相同的组间波动。总体 TTFT p50 四组均轻微变差，
总体 TTFT p99 四组均变差。因此，本次完整实验**不支持“固定分区能够稳定改善尾延迟”**的结论。

吞吐和墙钟时间基本完全一致：请求吞吐、输出 token 吞吐和墙钟时间的平均相对变化
都在 0.02% 以内，说明固定分区实现本身没有可观测的吞吐开销。

AB/BA 顺序对命中率结论影响很小：总体命中率在统一缓存先运行和固定分区先运行时的
平均相对提升分别为 0.43% 和 0.39%。延迟指标的顺序均值差较大，但同一种顺序内部也会
出现相反方向，说明主要问题是运行间尾延迟波动，而不是一个简单、可重复的先后顺序偏差。

### 当前建议

当前阶段可以继续采用 **61% Agent / 39% 普通请求** 的固定分区作为系统接入默认值，
但理由应调整为：

1. 已正确实现两类请求的缓存空间隔离；
2. 四组实验中总体缓存命中率均有小幅提升；
3. 吞吐和总运行时间没有明显损失。

不要再把“改善 p90 尾延迟”作为当前方案已经得到验证的收益。进入动态分区阶段后，
应优先优化并验证总体命中率、Agent 命中率和分区利用率；如果仍要把 TTFT 作为优化目标，
需要增加重复次数并单独分析排队、并发批次和运行噪声。上述完整实验结论应作为当前主要结论，
2026-09-23 的两次快速实验仅作为历史预跑参考。
