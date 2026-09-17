# 完整 frontier MLP serving 实验结论

已完成训练及三组各三次 TP=8 实验。两种 MLP 策略都减少了未命中 prompt tokens；
当前原型中 on-demand 的完成请求/秒和中位延迟更好，预计算的 eviction 中位耗时
和 E2E 尾延迟更好。不能把预计算更低的 eviction 开销直接当成整体服务更快。

## 核心结果

每格为三次运行的指标均值；延迟格是各次分位数的均值，不是合并请求后的分位数。

| 指标 | LRU | On-demand | 预计算并等待 |
|---|---:|---:|---:|
| Token 命中率 | 91.817% | 94.084% | 94.202% |
| 未命中 prompt tokens | 3,317,924 | 2,398,713 | 2,350,841 |
| TTFT p50 | 503 ms | 481 ms | 521 ms |
| TTFT p99 | 5,969 ms | 3,590 ms | 4,018 ms |
| E2E p50 | 1,305 ms | 1,232 ms | 1,300 ms |
| E2E p99 | 10,499 ms | 9,039 ms | 8,092 ms |
| 完成请求/秒 | 4.752 | 5.137 | 5.016 |
| Eviction p50 | 4.155 ms | 9.616 ms | 5.757 ms |
| Request-end p50 | 0.189 ms | 0.178 ms | 0.688 ms |

相对 LRU，on-demand 的未命中 prompt tokens 减少 **27.7%**，预计算减少 **29.1%**。
未命中包含首次访问，不能全部叫作 eviction 引起的重算。

预计算相对 on-demand 的 eviction p50 降低 **40.1%**，但完成请求/秒低 **2.4%**。
两者命中率均值仅差 **0.118 个百分点**，且第一轮预计算略低于 on-demand，不能声称
预计算稳定地提高了命中率。三轮 on-demand 的完成请求/秒均高于预计算。

## 预计算覆盖验证与额外工作

- 三轮 on-demand 共执行 4,814 次模型决策，预计算共执行 4,828 次。
- 最大合法 frontier 分别达到 161 和 147，完全移除了旧的 16 个候选限制。
- 淘汰后新暴露的父节点继续参与完整 frontier 的选择。
- 预计算三轮的 eviction 内新预测数均为 **0**；没有缺失 ticket 或 LRU fallback。
- 每轮平均遇到未完成任务 195 次，通过等待已有 future 取得结果；读取及等待合计约 0.210 秒。
- MLP 两组的逐次候选选择签名、释放量在 8 个 TP rank 上一致。原生 LRU 核验释放量，
  没有记录逐 victim 身份，不能把空的 LRU 决策摘要当作逐 victim 一致性证据。

**当前预计算实现较保守，并非只在 request-end 提交。** 每轮约提交 303,475 个
node-side 预测，其中 request-end 为 52,580 个，仅 **17.3%**；其他 82.7% 来自
match、unfinished cache、inc/dec lock 边界。完整按来源统计见 `report_zh.md`。

On-demand 每轮约预测 49,135 个 node-side，预计算约为其 **6.18 倍**。预测计数
包含同一节点多次刷新及 Full/SWA 两侧，不代表独立节点数。

预计算额外边界一方面覆盖了请求结束前的 split 与 SWA 可淘汰状态变化，另一方面
也保守刷新了不一定改变模型输入的锁操作。**因此，本结果只能说明这个广泛刷新
原型的取舍，不能据此判定用户提出的精简请求结束预计算一定更差。** 后续若优化，
应先收紧 dirty 判定、合并重复任务，再用相同 workload 重测，而不是删掉完整
frontier 或恢复 LRU fallback。

## 模型及实验口径

新模型保存于 `training/model.pt`：联合 16 个特征、固定 24 维输入宽度、两个
128-unit hidden layer、9 个有限 hazard logits，加剩余尾部共 10 桶。包含 cold
和右删失训练样本。按验证 NLL 选 seed 42，未按 serving 结果选模型。
单模型测试 Censor NLL 为 **0.942261**。详见 `training_report_zh.md`。

DeepSeek-V4-Flash，TP=8，FP8 KV，mem-fraction-static=0.45，Full token capacity
705,280，page size 256，chunked prefill 8192，max-running-requests 256。
每轮 1,970 个请求、572 个 session，decode 上限 32，9 waves/300s，gap scale 0.02。
三轮分别按预计算→on-demand→LRU、on-demand→LRU→预计算、LRU→预计算→on-demand 运行。

所有 9 次回放均成功完成 1,970 个请求，共 **17,730 次成功请求、零 API 错误**。
模型与 workload 哈希、有效配置、请求身份和 prompt token 数一致。GPU 占用记录
未发现正式测量期间的外部 GPU 进程。此前预跑及显存冲突导致的失败启动均未计入。

测试 workload 已过滤与训练 replay 重叠的 session、来源轨迹及首条 user message；
公共 system prefix 仍可能重叠。训练标签是旧 frozen frontier 到下一次 demand 的
wall-clock 间隔，并非无压力服务耗时，应用到 request-end 还存在观测时刻分布偏移。

同 session 下一轮等待上一轮完成，所以不同策略也会改变实际到达时刻。本实验
衡量闭环 serving 效果，而非固定时间线下的单一推理开销因果实验。三次重复可检查
方向是否一致，但未给出统计显著性或跨 workload 泛化结论。

## 产物

- `report_zh.md`：完整指标、逐轮结果和提交来源。
- `training_report_zh.md`：模型训练与预测指标。
- `shift_report_zh.md`：新 checkpoint 的条件更新评估。
- `completed_runs.json`：三轮正式运行目录。
- `online_runs/*/comparison.json`：机器可读汇总。
- `online_runs/*/{lru,on_demand,precompute}/`：API 回放、TP 日志、配置与 GPU 占用审计。

远端目录：`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/evict_position`。
