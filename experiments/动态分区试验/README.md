# 动态分区试验

本目录用于验证请求区域动态分区方案。当前推荐的动态方法是固定保障份额 + 空闲容量借用：一侧空闲时另一侧可以使用容量，只有共享 KV 池全局超额时才归还 borrowed 页，主动高低水位回收默认为关闭（`high=0`、`low=0`）。两区 LRU 和 Full/SWA 共用同一容量规则；归一化淘汰压力驱动的直接比例控制器保留为对照模式。

最新三基线与未修改官方引擎复核见 [2026-10-01 实验结论](results/three_way_validation_20261001/结论.md)。1,277 请求的受控压力构造中，借用相对官方原生命中率提升 3.33 个百分点、墙钟缩短 8.1%；普通热前缀回访均未命中，双向保护检查尚未通过。数据与复现命令见 [双向复用构造](data/bidirectional_reuse_calibrated/README.md)。

完整实验结论见：

```text
experiments/动态分区试验/动态分区实验结论.md
```

当前代码的最终无水位复核结果位于：

```text
experiments/动态分区试验/results/validation_20261001_current_nowatermark/
```

候选策略搜索、Agent 高压复核和 borrowed-only allocator fallback 修复记录见：

```text
experiments/动态分区试验/reports/dynamic_partition_strategy_search_20261003.md
```

当前准入结论是：`borrow` 保持正式默认；`borrow_global`、`borrow_reclass`、
`borrow_request_reclass` 和 `elastic` 只用于研究对照。它们在已有扫描或高压 workload
中没有同时超过 `borrow` 的总体、Agent 命中率和驱逐指标。

最新的 elastic 长程候选在活动窗口内增加了同类连续运行保护：窗口 32 在 mixed 压力
回放中总体命中率 90.4815%、Agent 95.0917%、普通请求 41.1104%，shadow 额外重算
22,016 token；阶段切换回放总体 90.1198%、Agent 95.1922%、普通请求 35.7994%，
shadow 额外重算 54,016 token。窗口 16、stale-tail-first 和压力反馈软线均未超过它，
因此当前研究候选固定为 `soft_step=0.10`、`activity_window=32`、`request_first`；
正式默认仍是 `borrow`。

2026-10-04 的后续复核还否定了两个直觉方向：只在真实前缀命中后刷新活动会把冷启动普通
请求误判为空闲，`scan_mixed_256` 总体命中率从同参数原始活动判定的 60.1883% 降至 48.2109%；一侧硬返回保障和
`activity_first` 回收顺序也没有在阶段与持续混合 workload 中同时超过上述候选。对应原始
日志和表格见 `reports/dynamic_partition_longrun_20261004.md`，hit-only 参数仅用于诊断，
默认保持关闭。

2026-10-04 新增的 `borrow_dynamic` 将淘汰反馈比例控制器与 borrowed-only 回收合并，
仅作为失败对照保留。旧反馈口径在 `scan_mixed_256` 上曾单次高 0.60 个百分点，但
完整阶段 workload 低 0.18 个百分点且 TTFT 均值明显升高；提高反馈累计阈值后仍未
超过 `borrow`。进一步只使用真实 borrowed-only 回收作为反馈后，最新扫描总体仍低
0.41 个百分点。它不改变正式默认，也不应作为稳定策略使用。

该目录使用 `mem_fraction_static=0.45`、固定 61/39 保障份额、`high=0`、`low=0`，
覆盖完整 mixed 和普通请求 → Agent → 普通请求两个 1,261 请求 workload。

此前使用固定请求数窗口的连续比例控制器已废弃。直接比例模式目前改为淘汰反馈驱动，但长程复核显示它在阶段切换中会因收缩比例而不可逆地驱逐 Agent 前缀；正式默认应使用 `borrow`，直接比例用于对照和后续研究。

直接比例与借用的长程并排结果见 `results/direct_ratio_validation_20261002/最终结论.md`。

最新修复补充了保障边界跨页处理：新节点插入后跨过本区保障份额时，整页标记为 borrowed，保证共享池超额时可以优先归还该页。最终完整复核见 `results/latest_20260930/mixed_scaled_boundary_fix/`。

阶段切换复核见 `results/latest_20260930/request_agent_request_boundary_fix/`，重点验证需求回到原所有者时只回收 borrowed 页。

设计说明见：

```text
docs/动态分区初步设计.md
```

## 启动动态分区服务

```bash
bash experiments/动态分区试验/scripts/start_dynamic_server.sh
```

启动固定保障 + 借用服务：

```bash
bash experiments/动态分区试验/scripts/start_borrow_server.sh
```

若要显式测试主动水位回收，可设置 `REQUEST_CACHE_BORROW_HIGH_WATERMARK_TOKENS` 和 `REQUEST_CACHE_BORROW_LOW_WATERMARK_TOKENS` 为正数；默认的 `0/0` 只在共享池全局超额时回收 borrowed 前缀。

默认实验参数：

```text
初始 Agent 比例：0.61
淘汰反馈阈值：0（每个安全反馈边界都可更新）
平滑系数：0.20
Agent 最低比例：0.20
Agent 最高比例：0.80

动态更新使用实际淘汰反馈：在安全边界统计 Agent/request 两区最近累积的淘汰 token，令
`eviction_share = agent_evicted / (agent_evicted + request_evicted)`，再按
`new_ratio = clamp((1-alpha) * old_ratio + alpha * eviction_share, min, max)` 更新。
因此全命中阶段不会因为完成请求数量达到某个窗口而调整；只有发生淘汰才会产生控制信号。
比例更新引起的配额重平衡淘汰会被单独丢弃，避免把控制动作自身产生的代价再次当成外部压力，造成比例振荡。
```

可以通过环境变量覆盖：

```bash
REQUEST_AGENT_CACHE_RATIO=0.61 \
REQUEST_CACHE_RATIO_ALPHA=0.2 \
REQUEST_CACHE_FEEDBACK_MIN_EVICTED_TOKENS=0 \
REQUEST_CACHE_AGENT_MIN_RATIO=0.2 \
REQUEST_CACHE_AGENT_MAX_RATIO=0.8 \
  bash experiments/动态分区试验/scripts/start_dynamic_server.sh
```

服务的 internal state 中会额外返回：

```text
request_cache_region_controller
```

其中包含当前比例、待消费的淘汰 token、最近一次淘汰反馈的区域占比和更新次数。每个区域的统计还包含当前超额 token。

在 allocator 发现区域范围内可驱逐页不足时，当前借用策略先从两区的
`borrowed_only` 候选中回收，再保留无区域 fallback 作为所有合法页都被锁定时的进度保障；
这类最后 fallback 会记录 `REGION_EVICT_FALLBACK`，用于后续 admission/backpressure 诊断。

## 正式受控实验

生成压缩时间线和“普通请求 → Agent → 普通请求”阶段负载：

```bash
python experiments/动态分区试验/scripts/build_experiment_workloads.py \
  --source-dir experiments/固定分区试验对比/data/token_balanced_openhands_wildchat \
  --output-root experiments/动态分区试验/data
```

运行统一缓存、固定 61/39 和动态分区对照：

```bash
python experiments/动态分区试验/scripts/run_controlled_experiment.py \
  --scenario mixed_scaled \
  --workload-dir experiments/动态分区试验/data/mixed_scaled \
  --modes unified fixed dynamic \
  --max-output-tokens 16 \
  --gap-scale 0.1
```

运行阶段切换对照：

```bash
python experiments/动态分区试验/scripts/run_controlled_experiment.py \
  --scenario request_agent_request \
  --workload-dir experiments/动态分区试验/data/request_agent_request \
  --modes fixed dynamic \
  --max-output-tokens 16 \
  --gap-scale 0.1
```

每个策略保存服务前后状态、完整回放、服务日志和每 5 秒一次的 controller/region 轨迹。汇总命令：

```bash
python experiments/动态分区试验/scripts/analyze_controlled_experiments.py \
  --run-root experiments/动态分区试验/results/formal_20260929
```

## Elastic tail-first 实验参数

在共享池 elastic 模式下，推荐使用 `REQUEST_CACHE_ELASTIC_SOFT_STEP=0.1` 和
`REQUEST_CACHE_ELASTIC_ACTIVITY_WINDOW=32`。后者要求最低保障不足的一侧在最近 32 次
分类请求内仍有访问，才优先回收另一侧较新的尾部节点；它只使用服务端已经观察到的请求
活动，不依赖工具返回时间或离线比例预测。该配置用于研究对照，正式默认仍为 `borrow`。

连续运行保护会在一侧连续访问超过窗口时恢复原始 61/39 返回保障；两侧近期交错时才
使用 20/20 最低保障和共享池。这是在线状态判定，不需要离线统计流量比例。
