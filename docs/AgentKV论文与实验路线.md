# AgentKV 论文与实验路线


## 2. 当前研究状态

目前已经完成：

1. 构造可复现的 Agent/Request 混合负载。
2. 实现 uniform、staggered 和 waves 到达模式。
3. 在 `mem-fraction-static=0.45`、6 个 waves 的条件下建立 LRU 压力基线。
4. 观察到压力条件下：
   - 全局 token-weighted hit 约为 24.4%；
   - GLM 会话内命中约为 3.7%；
   - OpenHands 会话内命中约为 49.7%；
   - TTFT p50 约为 11.8 秒。
5. 已确认论文方向应从“识别并保护 Agent”收敛为“无标签地估计 KV 未来复用价值”。

当前仍处于 D2 到 D3 的过渡阶段：问题已能稳定复现，但服务端错误驱逐证据、策略原型和主实验尚未完成。

## 3. 第一阶段：补齐 LRU 错误驱逐证据

先在相同压力基线上开启服务端 KV 诊断，记录 radix 节点的：

- 插入与访问；
- 驱逐时间；
- 节点 token 数和前缀深度；
- 驱逐后的再次访问；
- reuse time 和 request distance。

重点产出：

- `evicted_then_reused_tokens`；
- eviction miss 占全部 miss 的比例；
- 驱逐到再次复用的时间与请求距离；
- 错误驱逐导致的额外 prefill token 和时间；
- 离线 Belady 策略上界。

目标是形成完整证据链：

```text
LRU 驱逐可复用前缀
  → 前缀在较短距离内再次访问
  → 发生额外 prefill
  → TTFT 与整体 goodput 恶化
```

分析结果同步更新到 [`GLM_vanilla基线与研究问题收敛.md`](./GLM_vanilla基线与研究问题收敛.md)。

## 4. 第二阶段：离线策略回放

在修改在线引擎前，使用同一访问轨迹实现离线 cache 回放。

对照策略：

- LRU；
- LFU；
- SLRU；
- SGLang 现有 Agentic 策略；
- 本文候选策略；
- Belady 离线上界。

本文策略的候选 value-density 为：

```text
在线复用置信度 × 重算成本 × 时间衰减
──────────────────────────────────
             占用 token 数
```

其中在线复用置信度只使用服务端可观测信息：

- 节点命中次数；
- 连续前缀增长证据；
- 历史复用间隔；
- 最近访问时间；
- radix 前缀深度。

不读取流量来源、Agent/Request 类别或 session ID。具体公式和阈值由离线回放结果决定，不预先固定。

只有候选策略同时满足以下条件，才进入在线原型：

1. 减少驱逐后短期复用；
2. 减少额外 prefill；
3. 改善 TTFT；
4. Request 指标没有明显退化。

## 5. 第三阶段：三个协同改进点与在线原型

本文不应只有一个新的 eviction score，而应包含三个可以独立消融、共同形成闭环的改进点。

### 5.1 改进一：估值器（Value Estimator）

5.1 是估值器，只负责回答“这个节点值得保留到什么程度”，不直接执行准入、晋升或驱逐。价值不能只计算“保留下来可能带来的收益”，还必须描述它持续占用 KV 的成本。为每个 radix 节点分别估算：

```text
ExpectedBenefit
  = P(在时间窗 H 内复用 | 在线历史) × AvoidedPrefillCost

RetentionDemand
  = KVSize × ExpectedHoldingTime

NetValue(λ)
  = ExpectedBenefit
    - λ × RetentionDemand
    - MetadataAndMigrationCost
```

其中：

- `P(未来复用)` 来自节点命中次数、前缀连续增长、历史复用间隔和最近访问时间；
- `AvoidedPrefillCost` 表示保留后能够避免的重算成本，当前固定使用需要重新 prefill 的 token 数；
- `KVSize` 是节点实际占用的 token/page 数；
- `ExpectedHoldingTime` 是从现在到预测复用或过期所需的占用时间；
- `RetentionDemand` 表示节点预计需要消耗多少 KV token-time；
- `λ` 是单位 KV token-time 的动态机会价格，由 5.2 根据当前 KV 水位提供，而不是由估值器自行决定；
- `MetadataAndMigrationCost` 包括策略计算、ghost metadata，以及未来分层 cache 中可能产生的迁移成本。

估值器输出 `ExpectedBenefit`、`RetentionDemand`、预测置信度以及参数化的 `NetValue(λ)`，但不决定节点处于哪个状态，也不决定何时驱逐。它能够描述：

- 复用概率高但占用巨大、需要等待很久的节点；
- 复用概率中等但重算极昂贵、即将再次访问的节点；
- 占用很小且频繁复用的共享前缀；
- 最近访问但几乎不会再用的一次性 suffix。

该模块解决的是“如何给 KV 报价”：LRU 只知道过去多久没访问，却不知道未来收益、重算代价和保留成本。

### 5.2 改进二：控制器（Resource-aware Controller）

5.2 是控制器，负责回答“在当前资源状态下，应该如何使用 5.1 的报价”。它读取 5.1 输出的收益、成本需求和置信度，再根据 KV 水位设置 `λ`、状态阈值和实际动作。

同一个节点的 5.1 统计没有变化时，5.2 仍可能因系统状态不同而采取不同动作：

- KV 水位为 50%：`λ` 较低，容量充足，不必为了微小价值差异提前驱逐；
- KV 水位为 95%：`λ` 较高，长时间占用大量空间的节点净价值下降，控制器开始严格区分保护顺序；
- 水位回落后：降低 `λ`，避免持续使用高压时期的激进策略。

价值信号不只在 cache 满时被动参与一次驱逐，而应从节点进入 cache 开始控制其完整生命周期：

1. **Probationary admission**：新节点先进入观察状态，使用成本先验和较低置信度初始化；不直接 hard bypass，避免错误预测破坏可复用性。
2. **Evidence-based promotion**：节点出现真实前缀续写、重复命中或稳定复用间隔后，提升到 protected 状态。
3. **Value-aware eviction**：需要释放空间时，优先淘汰低 value-density 的 evictable leaf，而非最旧 leaf。
4. **Pressure-aware aging**：KV 水位较低时接近 LRU、减少额外干预；水位升高时增强价值差异和衰减控制，避免高压下所有节点获得同等保护。

该模块使用 `NetValue(λ)` 完成具体决策：准入和晋升根据净价值与置信度判断，驱逐时比较单位空间净价值并优先淘汰最低者。它解决的是“价值信号何时、以多大强度发挥作用”的问题。

两者的边界可以概括为：

```text
5.1 估值器：访问历史 → 收益、成本需求、置信度
5.2 控制器：估值结果 + 当前 KV 水位 → probation / promotion / aging / eviction
```

第一版仍不 hard pin KV，也不拒绝正常插入；生命周期状态只产生 soft priority，保证预测错误时能够安全退化。

一个具体例子：

```text
KV 容量：100k tokens，当前即将满载

A：40k-token GLM 长前缀
   40 秒前访问，但已观察到多次约 20–60 秒的前缀续写
   → 重算成本高、复用证据强，进入 protected

B：50k-token 单次 Request suffix
   5 秒前刚访问，但没有任何重复使用证据
   → 虽然比 A 更新，仍停留在 probation

C：10k-token 共享 scaffold
   体积小且频繁命中
   → 单位空间净价值高，进入 protected
```

此时新请求需要 30k tokens：

- 普通 LRU 可能因为 A 更旧而先驱逐 A；A 下一轮到达时需要重新 prefill 40k tokens。
- 本策略会综合判断 A、B、C 的预期收益和持有成本，优先从低净价值的 B 中释放空间。
- 如果 A 长时间没有按预测再次访问，其复用概率随 aging 下降，之后也会退出 protected 并正常被驱逐。
- 如果 B 随后意外再次访问，5.3 的 ghost regret 会记录这次错误，修正后续相似在线证据的初始价值。

因此，5.2 不是“永远保护某类 KV”，而是让节点经历：

```text
新插入 probation
  → 获得复用证据后 promotion
  → 随 idle 时间和 KV 压力动态 aging
  → 净价值不足时 eviction
```

### 5.3 改进三：反馈器（Regret Feedback）

5.3 是反馈器，负责回答“此前的估值与控制动作是否正确，以及应该如何修正”。系统维护一个有界的 ghost metadata 表，只保存已驱逐前缀的 hash、大小、驱逐时间、驱逐时价值及过期时间，不保存物理 KV。

当后续 prefix miss 命中 ghost 记录时，系统得到一次明确的 eviction regret：

```text
被驱逐前缀再次访问
  → 计算实际 reuse distance 与额外重算成本
  → 修正该前缀路径的复用置信度和衰减参数
  → 调整后续同类在线证据对应的保护强度
```

反之，ghost 记录长期未被访问并过期，则构成“驱逐正确”的负反馈。ghost 表采用固定容量和 TTL，避免元数据无限增长。

反馈器产生两类更新：

- 更新估值器：校正复用概率、复用时间窗和重算成本估计；
- 更新控制器：校正水位价格 `λ`、promotion threshold 和 aging 强度。

该模块解决的是“估值或控制错误后如何学习”的问题，使策略从开环启发式变成可观测结果驱动的闭环控制。反馈只使用已经发生的 ghost hit、正常 hit 和 ghost expiry，不读取未来信息。

### 5.4 三个改进点如何协同

```text
节点访问与前缀增长
  → 5.1 估值器：输出收益、成本需求和置信度
  → 5.2 控制器：执行 probation / promotion / aging / eviction
  → 5.3 反馈器：判断估值与控制动作是否产生 regret
  → 分别修正估值模型和控制参数
```

三个模块对应独立消融：

- 只有价值估算 + 固定驱逐；
- 去掉压力感知，始终使用相同参数；
- 去掉 ghost regret 反馈，只使用静态在线统计；
- 三个模块全部启用。

### 5.5 SGLang 最小侵入实现

- 在 [`evict_policy.py`](../Engine/sglang/python/sglang/srt/mem_cache/evict_policy.py) 增加 value-aware `EvictionStrategy`；
- 复用当前 `evictable_leaves + min-heap + get_priority(node)` 驱逐路径；
- 在 [`radix_cache.py`](../Engine/sglang/python/sglang/srt/mem_cache/radix_cache.py) 和 [`unified_radix_cache.py`](../Engine/sglang/python/sglang/srt/mem_cache/unified_radix_cache.py) 中维护价值、生命周期状态及有界 ghost metadata；
- 在 [`utils.py`](../Engine/sglang/python/sglang/srt/mem_cache/utils.py) 和 server 参数中注册策略；
- 不 hard pin cache、不修改 KV allocator、不改变请求到达顺序。

实现时需要保证：

- 节点 split、merge 和父节点提升后的元数据语义正确；
- ghost 表只保存 hash 与统计信息，不持有 KV tensor；
- TP 各 rank 的驱逐决策及反馈更新一致；
- 经典 RadixCache 与实际 V4Flash 启动路径行为一致；
- 元数据内存和驱逐排序开销可控。

## 6. 第四阶段：主实验

### 6.1 主对照

在固定压力 workload 上比较：

- LRU；
- LFU；
- SLRU；
- Agentic；
- 本文方法。

Belady 只作为离线上界，不作为可部署在线基线。

### 6.2 容量敏感性

围绕 `mem-fraction-static=0.45` 选择 4–5 个可启动水位，绘制：

- hit–capacity；
- eviction regret–capacity；
- prefill–capacity；
- TTFT–capacity。

该实验用于说明策略的生效区间，避免结论只建立在单个受限容量点上。

### 6.3 到达模式敏感性

比较：

- uniform；
- waves；
- 不同 wave 数量；
- 不同 wave 宽度。

用于证明收益不是特定“6 waves、10 秒宽度”配方的偶然结果。





### 6.6 消融实验

分别移除：

- 复用证据；
- 重算成本；
- 时间衰减；
- size normalization；
- 压力或水位感知。

解释每个组件对命中、重算、TTFT 和公平性的贡献。

## 7. 评价指标与成功标准

主要指标：

- 驱逐后短期再次复用的 token 数；
- eviction miss 比例；
- 额外 prefill token；
- token-weighted hit；
- TTFT p50、p95、p99。

守门指标：

- Request TTFT 和尾延迟不显著恶化；
- Request 吞吐不显著下降；
- 全局 goodput 提升；
- OpenHands 与 GLM 都能获得可解释收益；
- 策略计算与元数据开销可接受。

论文只在实验证明的容量和突发度区间内声明优于 LRU，不宣称所有负载上都占优。



## 9. 推荐执行顺序

```text
P0 复现压力基线并开启 kv_diag
  → P0 完成 mix eviction-regret 分析
  → P1 离线比较 LRU/LFU/SLRU/Agentic/候选策略
  → P1 实现最小在线策略原型
  → P1 主对照与低压力无退化实验
  → P2 容量、到达和流量比例扫描
  → P2 真实 GLM trace 验证
  → P2 消融、多种子和系统开销
  → P3 整理论文主表、机制图与 claim
```


