# 显式 Session 与 Prefix Family：Agentic KV Cache 研究重规划

> 日期：2026-07-16  
> 状态：当前唯一主计划  
> 替代：`docs/29_family_identification_framework_plan.md` 的匿名行为聚类路线，以及 `docs/32_first_research_question_validation_plan.md` 的匿名 Sessionization 主线  
> 平台：SGLang；固定正式基线从 `v0.5.15.post1` 开始  

---

## 一、一句话定位

> 假设 Router/Client 显式提供可靠 `session_id`；将共享同一 KV-compatible 精确 token 前缀的 Session 组织为动态、重叠的 Prefix Family，估计每个共享前缀的未来跨 Session 复用价值，并用该价值安全地偏置现有 KV 淘汰与分层管理机制。

本工作不再把“恢复匿名 Session 身份”或“语义聚类应用类型”作为首篇论文的核心。工业系统已经选择显式 Session，SGLang 也已正式发布一等公民 `session_id` 与 SessionRadixCache。新的核心问题是：

> **在默认 Radix prefix sharing、SessionRadix close 回收以及 strongest session/prefix-aware baseline 之上，Prefix Family 状态是否仍有可测的残余管理价值？**

这是一个必须先证伪的问题。若答案是否定的，说明 Radix 节点、holder/refcount 和 Session 生命周期已经足够，不应人为增加 Family 抽象。

---

## 二、已冻结的研究边界

### 2.1 身份假设

- `session_id` 由可信 Client/Router 显式提供。
- Session 表示一个可持续多轮的 agent/subagent 执行实例。
- Session 首次请求隐式创建，显式 `close` 结束生命周期。
- 缺失或不可信 `session_id` 的请求仍由普通 Radix 策略处理，不进入强 Family 动作。
- 匿名 Sessionization 只保留为 future work，不进入当前确认性主张。

### 2.2 Prefix Family 定义

在同一 KV-compatible namespace 内，给定一个 canonical radix prefix `p`：

\[
Family(p,t)=\{s\mid s \text{ 在时刻 } t \text{ 的请求路径经过 } p\}
\]

Family 的 key 为：

```text
PrefixFamilyKey = (
    kv_namespace,
    parent_prefix_key,
    canonical_token_block_ids,
    valid_block_length
)
```

其中 namespace 至少冻结：

- model architecture 与 weights revision；
- tokenizer revision；
- chat template / serializer；
- adapter / LoRA；
- KV layout、dtype/quantization、block size；
- tenant/security isolation domain。

任一不兼容或安全域不允许共享时必须 fail closed，不得仅因 token hash 相同就组成 Family。

### 2.3 Family 不是互斥聚类

一个 Session 的 radix path 通常经过多个祖先节点，因此同时属于多个嵌套 Prefix Family：

```text
root
└── system_prompt_family
    └── tool_schema_family
        ├── session_A_unique_tail
        └── session_B_unique_tail
```

因此旧设计：

```text
SessionTable[session_id] -> family_id
```

被废弃。正确关系是：

```text
SessionTable[session_id] -> current_radix_path
PrefixFamilyTable[prefix_key] -> set[session_id]
```

Family 可以重叠、嵌套并随 Session 到达、扩展和关闭动态变化。

### 2.4 首篇工作明确不做

- 行为相似或语义相似 Session 聚类；
- 非完全相同 token 的 KV 共享；
- position-independent KV reuse；
- 自定义强 pin；
- Router 直接控制 cache internals；
- 首阶段同时实现 Share、Prefetch、Demote、Retain、Routing 全套动作。

---

## 三、与 SGLang 当前能力的切割

截至 2026-07-16：

### 3.1 已进入正式版本，可直接作为机制或基线

- `#19171`：StreamingSession；已发布，但 pinned-slot 生命周期复杂，不作为新设计底座。
- `#21875`：StreamingSession race/leak/lifecycle 修复。
- `#27058`：SessionRadixCache；Session KV 是普通可淘汰 radix KV，支持按 Session close 回收。
- `#29436`：一等公民 top-level `session_id`。
- 普通 radix priority eviction/scheduling。

### 3.2 未进入正式版本，只能作为研究基线或未来接口

- `#21045`：priority + retention duration；关闭且未合并。
- `#29173`：session/ref-aware eviction；仍为开放 PR。
- `#29532`：session-level eviction framework；开放 Draft。
- `#30796`：`KvHintEnvelope` 到 Mooncake L3 retain；开放 Draft。
- `#24656`、`#27574`、`#29099`、`#29709`：仍为开放 RFC/Issue。

### 3.3 本工作的残余空间

现有正式能力已经覆盖：

```text
显式 Session 身份
  + Session ownership
  + close 时确定性回收
  + content-addressed prefix sharing
  + 普通 priority eviction
```

现有开放工作正在覆盖：

```text
session reference-aware protection
  + router-initiated KV hints
  + L3 retain/events
```

因此本工作不能把“支持 Session”“发现共享前缀”或“加 priority”作为贡献。候选贡献必须是：

1. 将 radix 上分散的共享关系提升为动态 Prefix Family 状态；
2. 证明 Family 历史对未来跨 Session 复用有 residual predictive utility；
3. 用统一价值函数协调 soft retention/eviction，并量化相对 strongest baseline 的系统收益。

---

## 四、系统架构

```text
Request(session_id)
        │
        ▼
SessionTable
  - active/closed
  - current radix path
  - latest request/turn/gap
        │
        ▼
PrefixFamilyIndex
  - prefix -> current/history sessions
  - overlapping/nested membership
        │
        ▼
Family Value Estimator
  - reuse probability / next distance
  - avoided prefill work
  - tier restore and capacity cost
        │
        ▼
Bounded Soft Policy
  - first: eviction priority only
  - later: L2/L3 placement, routing, prefetch
        │
        ▼
SGLang SessionRadix + HiCache
```

策略层表达意图，引擎保留执行权。任何动作均应：

- 可拒绝、可裁剪、可推迟；
- 有资源预算与 TTL；
- fail-open，不影响正常推理；
- 不改变 token IDs、RadixKey 与 prefix correctness。

---

## 五、最小数据结构

### 5.1 SessionTable

```text
SessionState {
    session_id
    namespace
    status: active | closed | expired
    current_radix_path
    latest_request_id
    observed_turn_count
    last_seen_time
    observed_gap_history
    current_priority
    close_time
}
```

SessionTable 只记录因果可见历史。禁止使用未来最终轮数、未来 gap 或 test 时的最终 session 统计。

### 5.2 PrefixFamilyTable

```text
PrefixFamilyState {
    prefix_key
    parent_prefix_key
    exclusive_token_span
    current_session_holders
    historical_session_holders
    active_session_count
    access_event_count
    last_access_time
    session_arrival_and_close_events
    residency_by_tier
    restore_cost_by_tier
    recompute_cost
    predicted_reuse_probability
    confidence
}
```

`current_session_holders` 与 RadixCache 的 in-flight ref/lock 必须区分：

- holder：Session 的历史/当前路径经过该 prefix；
- in-flight ref/lock：当前正在执行的请求对节点有不可淘汰约束；
- residency：节点的 KV 当前是否实际驻留 L1/L2/L3。

三者不能混用。

### 5.3 Session close 语义

Session close 时：

1. 从相关 Family 的 active holder 集移除该 Session；
2. 更新 Family 的未来需求估计；
3. 该 Session 独占 tail 可按 SessionRadix 规则释放；
4. 被其他 Session 共享的 prefix 不得因本次 close 被释放；
5. Family value 降低只影响后续 soft priority，不覆盖 refcount/in-flight correctness。

---

## 六、统一价值函数

### 6.1 基本目标

对 prefix family `f`、tier `k` 和决策时刻 `t`：

\[
V(f,k,t)=P(\text{reuse within }H\mid X_t)\cdot W_{\text{avoided}}
-C_{\text{restore}}(k)-C_{\text{capacity}}(f,k,t)-C_{\text{metadata}}
\]

其中：

- `P(reuse within H)`：未来固定 event horizon 内任意 Session 再访问该 prefix 的概率；
- `W_avoided`：命中该 prefix 可避免的 prefill work；
- `C_restore`：从目标 tier 恢复的时间/带宽/排队成本；
- `C_capacity`：占用容量导致其他 KV 被驱逐的机会成本；
- `C_metadata`：FamilyIndex、模型推理和更新开销。

### 6.2 必须区分的标签

1. **Demand label**：未来访问次数、next-distance、是否在 horizon 内复用。
2. **One-step marginal utility**：一次保留与一次合法淘汰动作的增量价值。
3. **Full-rollout policy utility**：策略在共同请求流上独立演化后的总 miss work。

预测准确率不能替代完整 cache rollout 收益。

### 6.3 Radix 去重

价值按节点 exclusive token span `Δ(v)` 计算；请求收益按最长连续命中前缀计算。不得把同一路径上祖先和后代 token 重复相加。

---

## 七、重构后的研究问题

### RQ0：Prefix-Family Residual Utility

在 default Radix、SessionRadix close、prefix recency/frequency/depth/refcount 和 session-aware/ref-aware baseline 之上，Family 状态是否仍改善 cache utility？

### RQ1：Family Value Estimation

哪些因果可见特征能预测共享前缀未来会被多少个 Session、在多远的未来再次使用？

候选特征：

- prefix recency/frequency/depth；
- current/historical holder 数；
- active Session 数与关闭率；
- Session 到达和返回间隔；
- prefix 的共享/独占比例；
- 当前系统负载、容量和 tier；
- 已观察到的工具等待与 Session 生命周期事件。

### RQ2：Bounded Soft Action

如何把价值与置信度映射为 bounded eviction priority，使低价值 Family 优先淘汰，同时保持所有 KV 可在极端压力下释放？

### RQ3：Multi-tier Extension

只有前述 RQ 通过后，再比较：

- 留在 L1；
- 备份/保留在 L2；
- 下沉/租约保留在 L3；
- 直接丢弃并在未来重算。

---

## 八、F0 可证伪验证门

### F0.0 数据与复现资格

进入 KV 结论的数据必须满足：

- 有可靠显式 `session_id`；
- 可复现 serializer/tokenizer；
- 可确定 KV namespace；
- 可按目标 SGLang block/radix 规则重建 prefix；
- 有因果请求顺序，或明确声明的 synthetic workload model；
- hash 命中可由完整 token span 校验。

不满足时只能用于 message/token-prefix proxy，不得声称真实 KV reuse。

### F0.1 Cross-session Exact-prefix Mass

量化：

- total reusable tokens/work；
- within-session 与 cross-session 的互斥贡献；
- 一个 prefix 被多少独立 Session 使用；
- Family 深度、大小和生命周期；
- 不同容量、并发和 workload 下的有效复用质量；
- Session close 后共享 prefix 的剩余价值。

**Stop 条件**：跨 Session exact-prefix 可避免 work 的置信上界低于预注册 SESOI，停止 Prefix Family 主线。

### F0.2 Residual Utility

冻结并依次比较：

```text
B0  LRU
B1  recency/frequency
B2  prefix depth/shared count/current refcount
B3  strongest identity-free forward-value
B4  default Radix full-rollout
B5  SessionRadix + deterministic close
B6  session-aware/ref-aware eviction
B7  oracle Prefix-Family value
```

主比较为：

```text
B7 - strongest(B0...B6)
```

**Go 条件**：Family 的 full-rollout avoided-prefill-work 增益下界达到 SESOI。  
**Stop 条件**：增益上界低于 SESOI，承认现有 radix/session/ref-aware 状态已经足够。  
**Inconclusive**：区间跨越门槛、样本不足或 simulator 未通过 conformance。

### F0.3 Cost and Safety

必须计量：

- PrefixFamilyIndex bytes/node、bytes/active Session；
- update/query P50/P95；
- value model 推理成本；
- stale holder/late close 成本；
- soft action 的错误保护损失；
- Family label/metrics cardinality。

### F0.4 Restore-versus-Recompute

对 L1/L2/L3 分别实测：

- restore latency/bandwidth；
- recompute prefill work；
- worker 间移动成本；
- cache hit token 增加是否真的转化为 TTFT/吞吐收益。

若 L3 restore 在目标拓扑上慢于重算，则 L3 retain 只能报告机制正确性，不得作为性能收益。

---

## 九、离线评测与 Simulator

### 9.1 数据起点

优先从 LMCache/agent trace 原始 Arrow 重建：

- request/session 顺序；
- 完整 messages/tool 信息；
- 显式 session ground truth；
- tokenizer 后 token path；
- radix prefix DAG；
- synthetic global interleaving。

现有数据审计数字必须由只读脚本重新生成 manifest 后才可引用。

### 9.2 PrefixFamilyIndex 离线接口

```text
on_request_arrival(request, session_id, namespace)
on_prefix_match(request_id, radix_path, tier_hits)
on_request_complete(request_id, output/timing)
on_session_close(session_id)
snapshot(decision_event)
query_family(prefix_key)
```

### 9.3 Replay 纪律

- 所有 policy 使用相同外生请求流、容量、block size 和初始状态；
- 每个 policy 从空 cache 独立运行；
- shared prefix 使用 set-valued holder，不伪造唯一 owner；
- in-flight 节点不可非法淘汰；
- Session close 与 cache pressure 的事件顺序固定；
- 多个 synthetic seed 只作 workload sensitivity，不充当新增独立样本。

### 9.4 RefAware baseline

虽然 `#29173` 尚未正式合并，其核心思想代表 strongest research baseline：

```text
UNUSED -> LOW_REF -> HIGH_REF
```

本研究必须实现等价离线 baseline，比较 Family 状态究竟提供了什么超出 active reference 的信息，不能只和 LRU 比。

---

## 十、通过门后的 SGLang 原型

### 10.1 固定基线

- 固定 SGLang `v0.5.15.post1` 或明确 commit/container digest；
- 启用 top-level `session_id` 与 SessionRadixCache；
- 固定 model/tokenizer/serializer、block size、capacity、scheduler flags；
- 不直接依赖尚未合并的 RFC/PR 作为正式能力。

### 10.2 第一阶段：Shadow Observer

仅旁路采集：

- `session_id` 与 close；
- radix prefix path / match length；
- device/host/storage hit；
- node holder/reference/residency；
- request timing、retraction、cache pressure；
- Family value prediction 与实际未来 outcome。

不修改：

- prompt/token IDs；
- RadixKey；
- prefix insertion/match；
- refcount/lock correctness；
- scheduler action。

### 10.3 第二阶段：Bounded Soft Priority

F0 与 shadow calibration 通过后，仅加入：

```text
family_value + confidence
        -> bounded priority bucket
        -> existing eviction ordering
```

约束：

- 所有 KV 最终仍可淘汰；
- priority 有范围、预算和可选衰减；
- engine 可拒绝；
- 失败时回退原策略；
- 不做 bulk free、strong pin 或跨 worker move。

### 10.4 后续升级

按证据逐级扩展：

1. L2/L3 placement/retain；
2. routing affinity；
3. prefetch/demote；
4. cross-worker share。

每增加一种 action，都必须单独做 simulator–engine conformance、风险预算和收益验证。

---

## 十一、Simulator–Engine Conformance

Simulator 与 instrumented SGLang 对同一 canonical stream 运行：

1. action-tape conformance；
2. closed-loop conformance。

至少覆盖：

- 多 Session 共享 prefix；
- 一个 Session close、共享 prefix 保留；
- 最后 holder close；
- in-flight lock；
- ancestor cascade；
- 同时 admission/eviction；
- L2/L3 restore；
- 非法 action 拒绝。

若 `cached_tokens/miss_tokens`、事件顺序、refcount、residency 或累积 prefill work 未达到预注册一致性门槛，则只能报告 trace-level reuse potential，不得报告 cache-management/system utility。

---

## 十二、成功、转向与停止

### Go

- cross-session exact-prefix mass 达到实用阈值；
- Family 相对 strongest session/prefix-aware baseline 有 residual utility；
- 开销与 soft-action 风险受限；
- simulator 与 SGLang 对齐；
- 至少一个高并发或非 clean-prefix workload 保持收益。

### Pivot

- Family value 有收益，但现有 `session_id + ref-aware` 已恢复大部分收益：转向 RefAware/SessionRadix 工程增强；
- L3 restore 慢于重算：保留 L1/L2 eviction 主线；
- exact-prefix cross-session mass 小，但 identity-free global forward value有效：转向全局 content value。

### Stop

- Family 相对 strongest baseline 的增益上界低于 SESOI；
- FamilyIndex/预测成本抵消收益；
- 收益只来自与 prefix depth/refcount 等价的重复特征。

停止时不得继续把 Family 包装成论文贡献。

---

## 十三、阶段产物

### Phase 0：定义、状态核实与审计

- 本文档；
- SGLang merged/released/open 状态矩阵；
- trace/namespace/tokenizer/radix manifest；
- PrefixFamily DAG 审计。

### Phase 1：F0.1 Cross-session Mass

- within/cross exact-prefix reuse 分解；
- Family size/depth/lifetime 分布；
- workload/capacity sensitivity；
- Go/Stop/Inconclusive。

### Phase 2：F0.2–F0.4

- strongest baseline suite；
- full-rollout cache utility；
- FamilyIndex 成本；
- L1/L2/L3 restore-versus-recompute。

### Phase 3：SGLang Shadow

- PrefixFamily observer；
- prediction calibration；
- simulator–engine conformance。

### Phase 4：Bounded Soft Priority

- family-value eviction policy；
- A/B 与风险/开销报告；
- 是否进入 multi-tier/hints 的决策。

---

## 十四、最小下一步

1. 只读重审 LMCache Arrow，生成显式 Session、serializer/tokenizer、namespace 资格 manifest。
2. 用固定 SGLang tokenizer/block 规则重建 radix prefix DAG。
3. 统计 cross-session exact-prefix mass，先回答 Family 是否有足够“物质基础”。
4. 实现 PrefixFamilyIndex 与 B0–B7 离线 baseline。
5. 冻结 SESOI、workload、capacity、主要 endpoint 和独立统计单位。
6. F0 全部通过后，才实现 SGLang shadow observer。

---

## 十五、一句话结论

> **Session 身份采用工业界已经落地的显式方案；Family 不再是行为聚类，而是 radix 上共享精确 KV 前缀的动态 Session 集合。论文的成败不取决于能否定义这个集合，而取决于它在 SessionRadix、RefAware 和 prefix-aware baseline 之上是否仍能提供可测、可转化、成本受限的未来复用价值。**
