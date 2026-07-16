# Prefix Family 的 Session-start 价值重定位

> 日期：2026-07-17  
> 关联报告：`docs/34_prefix_family_ttft_value_validation_report.md`、`docs/35_oracle_family_retention_experiment_report.md`

## 一、核心认识

Prefix Family 的跨 Session 复用主要发生在一个新 Session 的第一个请求：

```text
Session A Request 1：跨 Session Family prefix 复用
Session A Request 2...N：主要复用 Session A 自身已经产生的 KV
```

因此，跨 Session 和 Session 内复用承担的是两个不同阶段：

```text
Prefix Family
  → 优化新 Session cold start
  → 降低第一个请求 TTFT

Session
  → 优化同一 Session 的后续多轮请求
  → 保持纵向 KV 连续性
```

Prefix Family 不应该被定位为所有请求的主要 KV 优化机制，而应该被定位为：

> Session cold-start accelerator 与首请求 SLO insurance。

---

## 二、为什么全局 token 收益不高仍然合理

离线首请求 replay 中：

```text
Oracle next-use 相对 LFU：
+0.235 至 +0.544 个百分点 avoided-prefill ratio
```

这个结果表示：平均到整个工作负载后，Oracle 未来信息比 LFU 额外避免的 prefill token 不多。

但这不等于单次 Family 命中没有价值。真实 SGLang 实验中：

```text
共享 prefix：7,823 tokens
LRU 压力后 TTFT P50：307.3 ms
Oracle Family TTFT P50：94.2 ms
单次节省：213.0 ms
```

两组结果可以同时成立：

- Family 只优化每个 Session 的入口请求，因此在全部请求中占比有限；
- 但每次入口命中的单次收益很大；
- 全局 token 平均会稀释这种首请求收益；
- 首请求 TTFT/SLO 指标不会稀释这种收益。

因此不能只用全局 avoided-prefill ratio 判断 Prefix Family 的价值。

---

## 三、避免收益重复记账

总收益应拆分为：

```text
总 KV 收益
= 跨 Session 首请求收益
+ Session 内后续请求收益
```

### 3.1 跨 Session 首请求收益

只计算新 Session 的第一个请求从既有 Family prefix 获得的命中：

```text
cross_session_saved_tokens(session)
= first_request_family_prefix_hit_tokens
```

### 3.2 Session 内收益

从第二个请求开始，复用当前 Session 已经产生的上下文：

```text
within_session_saved_tokens(session)
= sum(request_2_to_n_session_prefix_hit_tokens)
```

同一段 KV 不能同时记为 cross-session 和 within-session 收益。

对于第一个请求：

- 请求到达前已经由其他 Session 建立的 prefix，属于 cross-session；
- 第一个请求执行后新增的 suffix，从第二个请求开始属于 within-session。

---

## 四、收益预期

### 4.1 对 Session 首请求

当前实测表明收益较高：

| 指标 | LRU pressure | Oracle Family |
|---|---:|---:|
| Cached tokens | 3 | 7,823 |
| TTFT P50 | 307.3 ms | 94.2 ms |
| TTFT 节省 | — | 213.0 ms |
| TTFT 降幅 | — | 69.3% |
| 200ms SLO 违约率 | 100% | 0% |

在当前模型、GPU 和 7.8K prefix 下，可以把每次有效 Family cold-start hit 的收益预期设为：

```text
约 150–215 ms TTFT
```

具体收益取决于：

- shared prefix 长度；
- probe 剩余 uncached suffix；
- 并发与队列压力；
- scheduler；
- KV 所在层级；
- restore 与 recompute 成本。

### 4.2 对全局平均请求

全局平均收益可近似为：

```text
AverageRequestSaving
≈ SessionStartFraction
× ExtraFamilyHitProbability
× SavingPerFamilyHit
```

例如：

```text
平均每个 Session 有 20 个请求
Session 首请求占比 = 5%

Family 相比基线额外提高 50% cold-start hit
每次命中节省 213 ms

全局平均 TTFT 收益
≈ 5% × 50% × 213 ms
≈ 5.3 ms/request
```

因此：

- 单个 Session 首请求可能节省约 200 ms；
- 摊到全部请求后可能只剩几毫秒；
- 全局平均 TTFT 不是最能体现 Family 价值的指标。

### 4.3 对全局吞吐

Family 对吞吐的影响取决于单位时间内新建 Session 的数量：

```text
SavedPrefillTokensPerSecond
≈ NewSessionsPerSecond
× ExtraFamilyHitProbability
× SharedPrefixTokens
```

如果 Session 很长、创建率很低，Family 对整体吞吐的贡献有限。

如果 Session 很短、创建频繁，Family 可以显著减少重复 system prompt 和 tool schema prefill。

---

## 五、哪些场景收益高

### 5.1 短 Session、高创建率

如果一个 Session 只有少量请求，首请求在全部请求中的比例较高，Family 收益不容易被稀释。

### 5.2 公共 prefix 很长

典型来源：

- agent system prompt；
- 工具定义；
- repository/runtime 描述；
- 安全策略；
- workflow scaffold；
- 相同模型和 tokenizer 下的固定消息模板。

4K–8K 以上 prefix 更容易产生明显 TTFT 收益。

### 5.3 缓存容量压力大

容量充足时，默认 LRU/LFU 也可能保住公共 prefix。

容量压力较大时：

- LRU 可能因为长时间未访问而淘汰 Family；
- Family retention 能充当 SLO insurance；
- 优化价值主要表现为避免 cold-start miss。

### 5.4 首请求有严格 SLO

例如要求新 Session 第一个 token 在 100ms 或 200ms 内返回。

即使全局平均收益不高，只要 Family 能显著降低 session-start SLO violation rate，仍然具有线上价值。

### 5.5 Session 跨 worker 路由或迁移

如果新 Session 被路由到已有 Family KV 的 worker，可以避免重新 prefill。

因此 Family signal 还可以反馈给：

- routing affinity；
- worker selection；
- prefetch；
- L2/L3 placement；
- session admission。

---

## 六、哪些场景收益低

### 6.1 Session 很长

如果每个 Session 有几十或上百个请求，第一个请求占比很低，Family 收益会被大量 Session 内请求稀释。

### 6.2 公共 prefix 已经非常高频

当前 trace 中的 7.8K prefix 被大量 Session 使用，LFU 很容易发现并保护它。

这解释了为什么：

```text
Oracle next-use - LFU
= 0.235 至 0.544 percentage points
```

Family identification 仍然正确，但复杂未来预测未必比频率提供更多信息。

### 6.3 KV 容量充足

没有驱逐时，默认 Radix Cache 已经能够完成内容寻址复用，Family retention 没有额外作用。

### 6.4 共享 prefix 很短

如果只共享几百 tokens，priority、索引和路由成本可能抵消 prefill 收益。

### 6.5 首请求不是关键路径

如果应用允许长时间 warm-up，或用户更关心完整任务执行时间而非首 token，200ms TTFT 改善的产品价值可能有限。

---

## 七、Oracle、LFU 与 Family 的关系

Oracle 代表提前知道未来：

```text
知道哪个 prefix 很快会再次使用
→ 保留它
→ 淘汰最晚或永远不会再使用的 prefix
```

LFU 不知道未来，只观察历史频率：

```text
过去被多次使用
→ 推测未来仍有价值
→ 提高保留概率
```

当前 clean-prefix trace 中，7.8K 公共 prefix 的历史频率已经很高，因此 LFU 接近 Oracle。

真正需要 Family 信号的场景是 LFU 不容易判断、但 Session 语义可以判断的场景：

- 两次复用之间间隔很长；
- Family 当前频率不高，但即将有新 Session 到达；
- 新 workflow burst 尚未形成历史频率；
- 多租户隔离导致频率不能直接合并；
- prefix 分散在不同 worker；
- Session close 后仍有其他 Family holder；
- 需要提前 routing/prefetch，而不是等命中后再统计频率。

因此下一阶段不应继续证明“高频公共 prefix 值得保留”，而应寻找：

> 频率信号失效、但显式 Session/Family 信号仍能提前识别价值的 workload。

---

## 八、系统职责重新划分

### 8.1 SessionTable

负责纵向、多轮生命周期：

- request 属于哪个 Session；
- 当前 Session 的 radix path；
- 后续 turn 继续增长；
- active/inactive/close；
- Session 内 KV 保留与释放；
- Session migration/recovery。

### 8.2 PrefixFamilyTable

负责横向、Session 启动阶段：

- 哪些 Session 共享 exact prefix；
- Family prefix 当前驻留在哪个 worker/tier；
- 新 Session 是否能够复用；
- Family holder count；
- 最近 Session-start 到达率；
- cold-start SLO value；
- retention/routing/prefetch priority。

### 8.3 执行边界

```text
新 Session Request 1
    → PrefixFamilyTable
    → 找到跨 Session 公共 KV
    → cold-start acceleration

Session Request 2...N
    → SessionTable
    → 复用该 Session 自身上下文
    → within-session acceleration
```

Family 不替代 Session，Session 也不能表达跨 Session 的 shared prefix residual value。

---

## 九、评价指标调整

### 9.1 Prefix Family 主指标

后续应优先报告：

- Session-start TTFT P50/P95/P99；
- Session-start 100/200/500ms SLO violation rate；
- Family cold-start hit rate；
- first-request avoided-prefill tokens；
- 每 1K retained Family KV 加速的新 Session 数；
- 每 byte retained 的 session-start TTFT saving；
- Family routing affinity 命中率；
- Family prefix 在 Session gap 内的 survival probability。

### 9.2 Session 主指标

- 后续 turn TTFT；
- Session 内 cached-token ratio；
- Session lifetime avoided-prefill tokens；
- active Session KV footprint；
- close 后释放速度；
- migration/recovery cost。

### 9.3 次要全局指标

- 全局 average TTFT；
- 总 avoided-prefill ratio；
- throughput/goodput；
- GPU utilization；
- eviction fairness。

这些指标仍然需要报告，但不应单独决定 Family Go/Stop。

---

## 十、建议的成功标准

Prefix Family 可以采用如下分层 Gate。

### Gate A：单次价值

```text
Session-start TTFT P50/P95 saving ≥ 100 ms
```

当前 7.8K 实验已经达到。

### Gate B：SLO 价值

```text
Session-start SLO violation rate 显著下降
```

当前受控实验中：

```text
200ms violation：100% → 0%
```

但仍需更大样本和真实到达流验证。

### Gate C：额外命中概率

Family 必须在 LFU/LRU 已经 miss 的情况下提高 session-start hit rate。

如果 Family 与 LFU 命中完全相同，则 Family 只提供可解释性，不提供 retention residual utility。

### Gate D：空间效率

需要测量：

```text
Session-start TTFT saved
÷ retained Family KV bytes
```

并与保留 Session KV、普通高频 prefix 的机会成本比较。

### Gate E：复杂度必要性

如果：

```text
observed frequency/shared-count
≥ 90% Oracle Family benefit
```

则停止复杂 predictor，使用轻量 metadata + bounded priority。

---

## 十一、当前收益判断

综合当前证据：

| 维度 | 判断 |
|---|---|
| 单个 Session cold-start | 高收益 |
| Session-start TTFT/SLO | 高价值 |
| 全局 average request TTFT | 中低收益 |
| 全局 token/throughput | 取决于 Session 创建率 |
| 相比 LRU 的定向保护 | 高收益 |
| 相比 LFU 的额外收益 | 当前较小 |
| 复杂 Family predictor | 暂无充分必要性 |
| 轻量 prefix metadata + priority | 值得继续 |

最终定位：

> Session 是主要的纵向 KV 管理单元；Prefix Family 是横向的 Session-start 加速与 SLO 保护单元。

下一阶段应围绕“新 Session 首请求”重新构造 workload 和指标，而不是继续用所有请求的平均 token 命中率稀释 Family 价值。
