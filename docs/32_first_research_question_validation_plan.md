# 首个研究问题验证规划：先验证管理价值，再决定身份路线

> **历史文档 / 已被替代（2026-07-16）**：本文的 `RQ0 = anonymous Sessionization` 与 F0 identity-frontier 路线不再执行。当前研究直接采用显式 `session_id`，把 F0 改为 cross-session exact-prefix mass、相对 strongest session/prefix-aware baseline 的 residual utility、成本安全门及 restore-versus-recompute 门。唯一当前计划见 [`docs/33_explicit_session_prefix_family_plan.md`](33_explicit_session_prefix_family_plan.md)。
>
> **仍然有效并迁移到 doc 33 的方法学资产**：原始数据审计与不可变 manifest、tokenizer/serializer conformance、因果时间切分与泄漏防护、SESOI 与置信区间、Go/Pivot/Stop、radix DAG 去重、full-rollout cache utility、simulator–engine conformance、风险预算。本文保留作为这些 protocol 细节的历史来源，但不得继续执行其 anonymous linker、RQ0-A/RQ0-B 或把行为类 Family 当作主目标。
>
> 日期：2026-07-14  
> 定位：旧匿名身份路线的验证协议；已由 doc 33 重构。  
> 当前结论：**不再投入 anonymous linker。F0 先验证 Prefix Family 的物质基础与 residual utility；只有相对 strongest baseline 达到预注册 SESOI，才进入 SGLang shadow 和 bounded soft-priority 原型。**

## 迁移映射

| 本文旧阶段 | 当前处理 |
|---|---|
| F0.1 global forward-value | 并入新 F0.2 的 identity-free/prefix-aware baseline |
| F0.2 oracle-session residual utility | 改为 cross-session Prefix Family 相对 SessionRadix/RefAware 的 residual utility |
| F0.3 behavior-family objective | 替换为 exact-prefix Family value 与 exclusive-span 计费 |
| F0.4 identity frontier | 删除；显式 `session_id` 已冻结 |
| RQ0-A anonymous linker | 停止，移至 future work |
| RQ0-B inferred-session utility | 删除 |
| 数据审计/conformance/功效分析 | 保留并迁移至新 F0 |
| SGLang shadow prototype | 仍保留，但须在新 F0 全部通过后启动 |

---

## 一、最终判断

### 1.1 首个正式研究问题

现有框架的正式编号不应改动：

> **RQ0：Sessionization——在隐藏显式 session identity 的在线 Chat/Agent 请求流中，仅使用决策时刻 serving 已可见的模型、时间、消息结构、内容和工具信息，能否以可控的污染风险，把 request 关联到正确的持续 session？这种关联是否能改善未来返回、内容寻址 KV 复用预测或 cache 管理决策？**

RQ0 之所以排在 RQ1–RQ3 前，是因为在线体系的逻辑数据流是：

```text
request → session → family → state/value → policy
```

现有规划明确区分纵向 sessionization 与横向 family identification，并指出错误 session 边界会污染轮次、返回概率、工具等待时间和上下文增长等 family 特征（`docs/29_family_identification_framework_plan.md:53-94`）。Family 也被定义为建立在已知或概率 session 边界之上的管理型行为类别（`docs/29_family_identification_framework_plan.md:98-113`）。

### 1.2 第一个实际动作不是 RQ0 linker

逻辑依赖不等于工程执行必须串行。第一个实际阶段是 **Pre-RQ Feasibility Gate F0**：

1. **F0.1 Global forward-value gate**：内容寻址 block/prefix 的未来全局复用能否被当前可见信号预测，并改善管理决策？
2. **F0.2 Oracle-session residual utility**：在 strongest identity-free predictor 之上，正确归组的历史 session 状态是否还有实际增益？
3. **F0.3 Family-objective exploration**：在 oracle session 边界上，哪些跨 session 聚合目标可能有额外管理价值？
4. **F0.4 Identity frontier**：比较 anonymous、minimal/hybrid、explicit identity 的收益、错误风险和元数据成本。

只有 F0.2 显示 session 有残余价值，而且 F0.4 表明匿名推断值得投入，才进入 RQ0-A anonymous linker。否则转向 minimal/hybrid identity，或回到 identity-free forward reuse value。

### 1.3 为什么 F0 不叫 RQ0.5

- `RQ0` 已明确保留给 Sessionization，`RQ1` 已保留给 Family definition/identification（`docs/29_family_identification_framework_plan.md:77-82`）。
- F0 是进入正式问题前的 go/pivot/stop 门，不是独立贡献编号。
- F0 同时服务于 RQ0、RQ1 和早期“复用价值是根”的总假设，叫 RQ0.5 反而会把它错误地限定为 session 子问题。

### 1.4 修正后的统一揭示后判定图（不是执行或揭示顺序）

`T_F0` 中的 F0.1--F0.4 必须在同一次锁定运行中全部执行，且在四者全部完成前任何结果均不可见。下图只表示统一揭示后的 serial-gatekeeping 解释顺序，不表示逐门运行、查看结果或适配后续 artifact。

```text
F0.1  冻结的 forward-value candidate 是否比 strongest identity-free baseline 达到实用增益？
  ├─ 否，且置信上界低于 SESOI_F01 → Stop 当前 candidate advancement；本协议不 Go，但不否定 baseline 或全局 cache value
  ▼
F0.2  Oracle session linkage/state 是否有残余增益？
  ├─ 否，且置信上界低于 SESOI_F02 → Stop session-aware RQ0，走 identity-free 路线
  ├─ 数据不足 → Inconclusive，补真实时间线/样本
  ▼
F0.3  在 oracle session 边界上定义并探索 family objective
  │     只回答目标价值，不声称在线 family identification
  ▼
F0.4  Anonymous vs minimal/hybrid vs explicit identity 前沿
  ├─ frozen anonymous 失败，且 weak/explicit 有可行路线 → Pivot 到 hybrid identity
  ├─ 无路线可判定或可行 → Inconclusive
  ▼
RQ0-A  Anonymous calibrated selective linker
  ▼
RQ0-B  Inferred-session downstream utility
  ├─ 无增益 → Stop/Pivot，不修改引擎策略
  ▼
SGLang shadow-mode side-channel prototype
  ▼
RQ1     Family identification（目标函数已由 F0.3 预先定义）
```

---

## 二、与已有研究框架的关系

### 2.1 保留 RQ0→RQ1→RQ2→RQ3 的逻辑依赖

现有正式问题依赖为：

1. RQ0：request 关联为 session；
2. RQ1：在 session 上定义并识别 family；
3. RQ2：结合 session 个体证据和 family 聚合规律估计状态与未来 KV 价值；
4. RQ3：将带置信度的信号反馈给保留、淘汰、调度和路由。

证据见 `docs/29_family_identification_framework_plan.md:53-94`。本规划不改变论文编号，也不允许绕过 session 边界直接声称在线 family identification 成立。

### 2.2 但 family 目标函数不应等到 RQ0 系统完成后才定义

现有规划将“确定 session identity 假设”“定义 family 目标函数”“设计最小 `SessionTable` / `FamilyTable`”列在选择识别算法之前（`docs/29_family_identification_framework_plan.md:539-546`）。因此：

- **RQ1 的在线算法**后于 RQ0；
- **RQ1 的目标函数和 oracle-boundary utility**可在 F0 中并行定义；
- source/project/application label 只能称为 **proxy strata**，不能未经验证称为 oracle family；
- 数据驱动 family 若使用目标变量学习，必须只在 train 内学习，并在 held-out session/task 上评估。

### 2.3 F0.1 继承“复用价值是根”的最早实验

`docs/26_cache_management_framework.md:15-59` 把前看型复用价值列为关键分叉，并建议先离线比较历史频率、当前依赖结构与未来复用。因此本规划把全局内容寻址 block/prefix 的未来价值放在 session utility 之前。

Session 不是 KV 的排他 owner。一个 radix node 可被任意 session 复用，SGLang RFC 的 token-relative Pin 也不强制 session identity（`docs/31_sglang_27574_programmatic_kv_cache_zh.md:34-40`）。所以主目标必须是**全局 future access/value**，within-session reuse 只是其分解。

### 2.4 SGLang serving prototype 是通过门后的主线；隔离 conformance adapter 是 F0 管理收益结论的前置夹具

Phase 5 的 SGLang serving/shadow prototype 不是 F0 的前置条件；但凡 `T_F0` 结果要被称为 full-rollout cache-management utility 并触发 Go/Stop，对应 action/policy family 必须先通过 Phase 0 的隔离 simulator--engine conformance adapter。该 adapter 不接入真实 serving path，也不等同于 prototype。

SGLang 的结构化请求观测、分层 prefix hit、Prometheus 和请求级回采能力更完整，既有规划已指定其为主实验平台（`docs/29_family_identification_framework_plan.md:420-447`）。其 KvHints 也采用“外部表达策略、引擎执行且可裁剪/拒绝”的安全接口（`docs/31_sglang_27574_programmatic_kv_cache_zh.md:34-47`、`docs/31_sglang_27574_programmatic_kv_cache_zh.md:98-107`）。

但 RFC 自身也要求先度量 L3 restoration，再增加主动 Prefetch/Demote API（`docs/31_sglang_27574_programmatic_kv_cache_zh.md:61-74`）。本规划同样坚持：先完成离线价值验证与隔离 conformance，再在通过后开展真实 serving-path shadow 和策略改动。

---

## 三、研究主张与假设

### 3.1 首阶段成功后最多能声称什么

> 对本研究覆盖的 Chat/Agent trace 和明确声明的 workload model，决策时刻可见信号能够估计内容寻址 KV 的未来价值；正确 session linkage 在 strongest identity-free baseline 之上具有可测的残余价值；在可识别请求子集上，匿名 selective linker 可在明确风险预算内恢复一部分 oracle session 收益。

不能声称：

- 任意 agent/API/history policy 都可恢复 session；
- synthetic interleaving 等同生产真实全局到达流；
- exact message-prefix 近满分证明匿名识别已经解决；
- source/project/语义聚类天然是 management family；
- trace-level hit tokens 必然等于 SGLang 端到端吞吐收益；
- hint API 本身解决了匿名 sessionization。

### 3.2 可证伪假设

#### H-FV：当前可见信号能估计全局未来 KV 价值

对一个内容寻址 block/radix prefix，历史频率、recency、当前依赖和请求结构可预测其未来任意请求访问次数、下一次访问时间和 token savings。

#### H-SU：Oracle session linkage/state 有残余管理价值

在严格控制同一决策时刻可见的 request/block 特征后，仅把已经完成的历史正确归组为 session，并由过去记录因果计算 session summaries，能改善全局 future KV value、return hazard 或 cache action utility。

#### H-AL：匿名请求在可识别子集上可安全选择性链接

仅用当时可见信息，linker 在压力负载 held-out test 上的 `Coverage_eligible` 单侧置信下界达到预注册 `c_min`，同时主安全指标 `FMR_attach` 的单侧上界不超过 `r_attach`；不可识别时 abstain。若 linker 输出还将驱动 14.2 的具体 cache action，该 action 的预注册 `R_action <= r_action` 是独立的下游门，不能用较宽松的 attach 门替代。

#### H-DU：推断 session 有下游增益

相对 strongest identity-free baseline，inferred session state 在预注册主要 endpoint 上的单侧置信下界达到 `SESOI_DU`；只有 explicit/oracle-session 相对 identity-free gap 的下界达到预注册 `g_oracle > 0` 时，才定义并检验 recovered-gap fraction。

#### H-FU（RQ1 的前置探索）：跨 session 聚合可能有额外价值

在控制 session 个体状态后，使用不泄漏结果的 proxy strata 或 train-only family grouping，能在 held-out session/task 上改善目标。F0.3 只验证目标价值，不声称在线识别已解决。

---

## 四、数据、切分与 lineage

### 4.1 主数据

首阶段优先使用现有 LMCache agent trace 原始 Arrow，而不是聚合 JSON。当前初步审计为：

- 24,880 requests；
- 767 sessions；
- 24,113 个 session 内相邻 transition；
- 来源包括 SWE-bench、GAIA 和 WildClaw；
- 字段含 `session_id`、`model`、完整 message list、`output_length` 和 `pre_gap`；
- message 保留 role、content、tool name、tool arguments 和 call/result ID。

这些数字必须由正式只读审计脚本重新生成并写入 manifest，不能直接作为最终事实引用。

### 4.2 F0.0：数据资格门

正式建模前先按样本和 namespace 生成 eligibility matrix；任何一项失败都必须缩小 estimand，不能靠模拟器补成“已观测事实”：

| 结论层级 | 最低数据要求 | 不满足时允许的结论 |
|----------|--------------|--------------------|
| Session linking | 因果顺序、完整的当时可见 payload、可信 session/lineage ground truth | 仅 message-level linking；缺失 strata 单列 |
| KV future value | 冻结 serializer/tokenizer/block-hash 可复现，且存在声明 workload 下的全局事件顺序 | 不得报告真实 KV reuse；只能报告 message/token-prefix proxy 或条件化 synthetic result |
| Cache policy utility | 可重放的 admission/access/eviction 语义、容量与共享约束，且对应 action/policy family 的 simulator--engine conformance adapter 按 15.4 通过 | 只能称 trace-level reuse potential；不得触发 full-rollout Go/Stop |
| System utility | 真实引擎 shadow/A-B 或经验证的 hardware cost model，覆盖排队与调度反馈 | 不得声称 TTFT、吞吐或 GPU 成本改善 |

Manifest 必须报告每道门的纳入/排除数、缺失原因、source/model 分布和排除前后偏移。若 KV-eligible 样本不足或只覆盖单一 source/model，则 F0.1 为 Inconclusive，不得用 message-level 全量样本补充功效。

资格规则还必须在读 test 前固定到 request/session/lineage/namespace 四层：重复或损坏 request、缺失 payload、单请求 session、左右截断/未完整观测 session、provenance 冲突分别如何纳入，均写入 manifest，并逐条报告规则前后分母。Session-linking 的确认性样本必须有完整可信的 session partition；或者 predecessor 标注必须穷尽 eligible request、同时具有明确负例语义，并能唯一还原该 partition。零散正边或未知边不能证明 cluster 中“没有其他真实 session”，因此只能评估被标注边的局部检索，不能报告 strict contamination、final clustering 或 oracle equality retrieval。两类 truth 都没有时只能做无标签的可行性描述，不能报告 linking correctness。

### 4.3 Clean trace 的上界性质

初步审计显示 24,113 个相邻 transition 中有 24,105 个（99.9668%）满足后一请求 message list 严格以前一请求完整历史为前缀。因此：

- clean trace 只用于 pipeline sanity check 和 exact-prefix ceiling；
- 不能把该结果作为匿名 sessionization 的主要贡献；
- 主结果必须来自 history truncation、causal summary/rewrite、重复任务、clone session、高并发和临时字段漂移。

### 4.4 无真实跨 session 全局时间线

Arrow 行按 session 连续存储，`pre_gap` 只提供 session 内相对间隔。因此：

- **主要科学 endpoint 使用 request/event-count horizon，但仍条件化于合成的全局事件顺序**；
- wall-clock return/reuse 只作 workload-model sensitivity；
- session 启动/到达模型只能用具有真实全局时间线的独立外部 train/pilot trace 拟合，或作为 normative stress target 预先指定；当前 session-contiguous Arrow 的 train split 不具备这项资格；
- 至少报告 Poisson-like、bursty/heavy-tail 和 adversarial 三类启动模型；
- synthetic seed 是重复测量，不是新增独立样本；
- total/cross-session future value、cache contention 和 policy utility 全部写成 workload model `W` 下的条件 estimand；不存在脱离 `W` 的“全局”标签；
- 同一组 held-out lineage 必须在各 `W`、seed 和 policy 下配对重放，分别报告跨 workload 的方向一致性与效应范围，不得先挑最有利 `W` 再设为主结果；
- 基于 synthetic interleaving 的结论只能作为进入原型的筛选门，正式生产时间结论需真实全局 trace 或在线 shadow data；
- 在查看 test 前，scenario manifest 必须指定唯一 `W_primary`，以及只作 sensitivity 的其他 `W`。`W_primary` 要给出 session start、within-session gap、并发上限、结束/censoring、clone 注入和随机种子生成规则；若无外部流量证据，不能把它称为真实生产分布，只能称预注册参考 workload；
- `W_primary` 只能来自两种来源：外部真实全局 trace 在 train/dev 上校准，或事先声明的 normative stress target。前者冻结并报告 arrival rate、active concurrency、burstiness、idle-gap 和 namespace mix 的目标分布及拟合误差；后者冻结目标 occupancy/concurrency quantile 和选择理由。当前 session-contiguous Arrow 本身不能识别这些量。两者都没有时，F0.1 只能给出 synthetic sensitivity，不得触发生产 Go。

### 4.5 不可变 lineage-first 切分

先用可信 provenance 建立 `lineage_group`，再切分，再生成任何扰动：

1. 只依据原始数据已有的 source/task/run provenance 建立 lineage；
2. 同一 underlying task 的跨模型运行和全部派生样本归入同一 lineage；
3. 按 lineage 做 train/dev/test，例如 60/20/20；普通泛化分析可按 source/project/model 分层，但凡声称 held-out source/project 泛化，必须先在顶层冻结互斥的 source/project group，将整个 group 只分配到一个 split/pool，不能把同一 source/project 的 lineage 分散后仍称为 held-out；
4. clone、summary、rewrite、redaction、ID drift 只能在 split 后分别生成；
5. 同一原始 session/task 的全部派生样本继承原 split；
6. 归一化规则、词表、摘要器、阈值和模型只用 train/dev 确定并冻结。

若可信 provenance 不足、task grouping 必须依赖内容相似度，则不能在同一批待切分数据上先定义 `train` 再学习规则。应先在独立开发语料或外部 provenance 标注上冻结 grouping 规则，再将其一次性应用于全量原始数据建立 lineage；无法满足时宁可采用保守的超集 grouping，或将该部分标记为不可用于严格 held-out 结论。Test lineage 绝不能参与规则选择。

一次 60/20/20 不能支撑多阶段反复查看同一 test。Phase 0 必须在任何结果可见前，把可用 lineage 和具有跨 lineage 干扰的完整 workload streams 进一步封存为互斥的 stage-specific confirmatory pools：`T_F0`（F0.1--F0.4 的预注册 gate family）、`T_RQ0A`（完整 anonymous linker）、`T_frontier2`（learned-anonymous 第二阶段前沿）和 `T_RQ0B`（下游闭环）。`T_F0` 是一个原子 reveal family：F0.1--F0.4 的冻结 artifact 必须在同一次锁定运行中全部执行，所有 gate 的结果在运行结束前保持不可见，之后才按预注册 serial gatekeeping 和 simultaneous-confidence/多重比较规则解释。Serial gatekeeping 只控制检验顺序与错误率，不授权在 F0.1 结果可见后修改 F0.2--F0.4 的路线、特征、阈值、压力集、动作或样本；若工程上必须逐门查看并适配，则须在揭示前把 `T_F0` 再拆成互斥子池并分别做功效分析。任一 pool 的结果一旦可见，就不得再因任何适配而为后续阶段提供确认性区间。Simulator conformance workload 也与这些性能 pool 按 provenance 隔离。各 pool 的独立单位数须分别通过 14.1 的功效分析；当前数据不足时，保留 pool sealed 并补外部 streams/sessions，或把对应阶段判为 Inconclusive，不能靠复用已查看 test 补样本量。

### 4.6 Summary/rewrite 的因果约束

对时刻 `t` 的请求生成摘要时，只能读取 `t` 之前已经可见的消息前缀。禁止：

- 用完整 session 或最终答案生成早期摘要；
- 在摘要中编码 oracle session/task label；
- 根据未来分叉选择保留字段。

### 4.7 两类扰动必须分开

压力实验在生成前声明 channel，二者不得共用同一 endpoint 名称：

1. **Observer-only masking**：linker 看到截断、redaction 或 drift 后的视图，但 serving/cache 仍接收原请求。它只估计身份信号脆弱性；不能用于声称真实 avoided prefill work，因为观察者和引擎看到的 token stream 不一致。
2. **Serving-realistic transformation**：变换后的 payload 同时送入 linker、冻结 serializer/tokenizer 和 cache replay。必须重新计算 token IDs、radix keys、future-value labels、容量占用和下游 endpoint；只保留经人工或冻结判据确认语义仍有效的样本。

Clone/repeated-task 若作为新增请求进入 workload，必须在事件流冻结前插入，并参与容量竞争与全部 policy replay；不能先从原 trace 计算收益，再把 clone 仅加到 linker 评估中。主下游结论使用 serving-realistic channel，observer-only 结果只作诊断。

Serving-realistic 变换若改变可能影响后续模型/工具行为的语义，原 trace continuation 只是外生冻结的条件路径，不是该变换下真实生成的反事实结果。确认性 system/behavior endpoint 只能使用重新执行的 model/tool continuation，或预注册为 continuation-preserving 且通过冻结判据的变换；否则结论限于条件化 token/cache replay。人工判定时须冻结盲评流程、接受阈值、分歧处理，并按 channel/stratum 报告接受率和排除偏移。

---

## 五、冻结决策时刻与防泄漏协议

### 5.1 预注册四类决策事件

每个实验必须声明在哪个事件冻结 feature snapshot：

| 事件 | 此时允许的信息 | 典型任务 |
|------|----------------|----------|
| Request arrival | 当前 payload、之前已完成请求、cache 当前状态 | session linking、admission/routing |
| Decode completion | 当前输出、实际 cached tokens、timing | retention、tool-wait prediction |
| Tool/interception return | 已观察到的 tool result 与 gap | resume/retain decision |
| Eviction/admission event | 当时 radix/block/refcount/tier 状态 | cache policy |

5.2 的所有条件必须拥有同一时刻已产生输出的相同访问权限，不能让 oracle 组额外看到未来。

### 5.2 嵌套特征消融

#### A：Identity-free causal features

- 当前 request/model/prompt/token/message 结构；
- 内容寻址 prefix 的 age、frequency、共享深度、当前依赖；
- 已完成输出和工具信息，仅在对应事件之后；
- 当前 cache/tier/refcount 状态；
- 全局 recency/load/concurrency。

#### A+L：Oracle linkage + fixed raw-history retrieval

Oracle 只暴露“当前记录与哪些已完成记录同属一个 session”的 equality relation。模型可通过统一接口检索该 session 在冻结事件前已完成的原始记录，但不直接获得任何人工统计、最终轨迹或未来字段。为使对照可解释，A 也使用相同检索容量和相同原始字段，只是按 identity-free 相似度/recency 选择历史；A+L 仅把检索关系替换为真实 session 归组。

`L` 的 estimand 因而是：**在固定历史访问预算下，把历史检索从 identity-free 候选替换为正确 linkage 的增益**。Opaque ID 本身不作为可泛化类别特征，也不能在 held-out session 上做 lookup-table 记忆。

该“固定预算”必须可执行而非口头公平：在 manifest 中冻结每次决策最多检索的已完成 request 数 `R_max`、序列化输入 token 数 `T_max`、允许字段、排序/tie-break 和不足预算时的处理。A 从全部 compatible 过去记录中按冻结的 identity-free 规则取前 `R_max/T_max`；A+L 只把候选关系替换为真实 session 过去记录，使用同一上限且不以无关记录补齐。另报告两组实际读取记录数、token 数和与 oracle 历史的 overlap，防止把更大上下文窗口误记为 linkage 收益。

#### A+S_identity-free：Identity-free causal summaries

在 A 检索到的固定预算历史上运行与 A+L+S 完全相同的冻结在线聚合器。该条件控制 summary 特征工程、状态容量和更新计算本身；除历史记录由 identity-free 检索外，字段、聚合公式、模型容量和资源预算均与 A+L+S 相同。

#### A+L+S：Causal session summaries

在 A+L 可检索的同一批过去原始记录上，用上述同一预先冻结的在线聚合器计算：

- observed turn count；
- 历史 gap；
- context growth；
- 已观察 tool transitions；
- return cadence；
- last-seen state。

禁止使用最终 session 长度、真实最后一轮、未来 gap、未来终止、完整轨迹统计。显式 `close` 只能从真实到达该信号之后使用。

#### A+L+S+P：Proxy/family summaries

只使用外部 provenance proxy，或 train-only 学得且固定的 grouping，在 held-out session/task 上聚合过去记录。

记 `B_IF` 为 test sealed 时在 dev 上从 `A` 与 `A+S_identity-free` 中按冻结规则选出的唯一 strongest identity-free condition。这组消融分别回答：`A+L - A` 是固定 raw-history 预算下 linkage 本身的价值；`A+L+S - B_IF` 是配平 summary 工程与状态成本后，正确归组带来的身份条件状态价值；`A+L+S - A+L` 只作为 summary 表示的增量；A+L+S+P 再回答跨 session aggregation 的残余价值。

### 5.3 在线 linker 禁用字段

禁止使用：

- `session_id` 及其可解析部分；
- source/project/task/provenance label；
- 当前请求尚未产生的输出；
- 未来 request、gap、结束状态；
- 全 test set 预计算的 task identity；
- test set 调参、调阈值或学习 normalization。

---

## 六、F0.1：Global Forward-Value Gate

### 6.1 目标对象、支持集与 estimand

KV 以 token/block/radix content 寻址，不以 session 排他归属，但“全局”只在同一 **KV-compatible 且允许共享的 namespace** 内成立。Manifest 必须冻结并记录：model architecture/weights revision、adapter/LoRA、tokenizer revision、chat template/请求序列化、rope/KV layout、dtype/quantization、block size/hash 规则，以及 tenant/security isolation domain。任一不兼容维度不同，或安全策略禁止共享，就禁止合并 future-reuse label、构造 cross-session 正例或共享 cache；多 namespace 结果先分层，只有预注册的加权规则才可汇总。

实现上必须用冻结的 `namespace_key(request_metadata) -> KVNamespace | DENY` 映射，而不是人工事后分组。缺失、冲突或未知 revision 一律 fail closed 为 `DENY`；tenant/security domain 是不可跨越的硬边界，不能靠相同 token hash 覆盖。审计需保存原始 metadata、规范化结果和拒绝原因，并用跨 adapter/tokenizer/template/tenant 的负例测试证明不会误合并。

原始 message 必须通过冻结的 serving serializer 和 tokenizer 确定性地产生 token IDs，再按目标引擎的 block boundary/hash 规则形成 block/radix key。无法复现序列化或 tokenizer revision 的样本，只能用于 message-level sessionization，不得进入 KV reuse/avoided-prefill 主结论。Hash collision 必须通过完整 token span 校验，而不是把 hash 相同直接当作命中。

基本单位不是可任意相加的孤立 block，而是 radix 节点 `v` 的 exclusive token span `Δ(v)` 及其从根到 `v` 的 ancestor closure `P(v)`：

1. 请求访问事件是 token path；future demand 可记录为未来 `N` 个事件中 path 穿过 `v` 的次数与下一次距离；
2. retained cache state 必须满足 prefix closure，或显式计入引擎为保留 descendant 所需的 ancestor/storage metadata；
3. 一次请求的 reusable tokens 定义为 cache 中与请求 path 匹配的**最长连续前缀**，不能把多个 ancestor/descendant 的长度重复相加；
4. `avoided prefill work` 按请求级最长命中前缀与冻结 cost function 计算，再跨请求求和；token 数和 estimated work 分开报告；
5. 节点 `v` 的 policy-conditional one-step marginal utility 是在相同历史状态和未来请求流下，比较焦点事件执行合法保留动作与合法替代/淘汰动作：两条分支除焦点动作外使用同一个冻结 continuation policy `pi_cont`，运行恰好 `N` 个后续 eligible events，并计入容量代价、ancestor 级联和 tie-break。替代动作、`pi_cont`、horizon 和终止规则必须冻结，因此它不是与 policy 无关的固有标签，也不等同于完整 rollout policy utility。

在冻结 workload model `W`、event horizon `N`、namespace、容量 `C` 和 action semantics 下，分别估计：

- within-session demand/utility：未来消费请求与产生 focal admission/retention decision 的请求属于同一 oracle session；
- cross-session demand/utility：二者属于不同 oracle session，但处于允许共享的同一 namespace；
- total policy utility：在请求级去重后的实际总 avoided work，不通过简单相加两个独立模拟结果获得。

Oracle `lineage_group` 只用于防泄漏和统计聚类，不能代替 oracle session；同 task 的不同 session 仍属于 cross-session。共享 radix node 没有排他 owner，因此每个 marginal-utility 样本必须绑定唯一 focal decision request。对完整 rollout 中的实际 hit，则按消费前最后一次使该 exclusive span resident 或刷新其保留决策的 request 归因，事件同刻时使用冻结的 request/event tie-break；若实现无法恢复该事件链，只报告 total，不报告 within/cross。另以“历史访问 session 集合”为 set-valued sensitivity，避免把多 session 共同维护的节点伪装成唯一归属。

`total policy utility` 是主要管理 estimand；within/cross 只是在同一次 replay 中按上述规则对贡献请求做互斥归因。所有符号在预注册表中绑定到明确的 `W/N/C/policy/cost function`，不得将某一 synthetic workload 下的结果简称为无条件的“global value”。

### 6.2 Baselines

- LRU/recency；
- historical frequency/LFU；
- prefix-depth/shared-count；
- current dependency count；
- recency + frequency；
- 可解释的 logistic/Poisson/GBDT/survival 模型。

预测标签分两层，禁止混称：

- **policy-independent demand label**：未来 path access、next-distance、请求级最长可复用前缀等，适合评估预测能力；
- **policy-conditional one-step utility target**：按 6.1 冻结焦点替代动作、`pi_cont`、容量和 `N` 后得到的 incremental avoided work，适合训练/评估局部 cache action；
- **full-rollout policy utility**：各候选 policy 从共同初始状态独立演化，在冻结 scored window 上计算请求级 miss work，作为 6.3 的确认性管理 endpoint。不得用 one-step target 替代它。

同一 lineage 的高度相关 node 可以作为训练样本，但 fold、bootstrap 和显著性检验的最外层单位必须遵循 13.5：无跨 lineage 干扰时按 lineage 整体分组，有共享 cache/global index 等干扰时按独立 workload stream 整体重采样，不能把 node、session 或 source 内重复观测当作独立样本量。

“Strongest baseline” 的选择也必须冻结：候选集合、超参数预算、训练数据、early stopping、随机种子数和 dev 选择指标在运行前登记，只能在 train/dev 选出一个 winner 后一次性用于 test。所有 policy 使用同一到达流、容量、block size、scheduler、合法 action set 和 admission 时点；模型推理延迟、索引内存和元数据字节单独计费并报告。不得在 test 后按容量、source 或指标切换不同 baseline 组成事后包络线。

### 6.3 主要 endpoint

正式跑 test 前必须在注册表中指定且只指定一个主要 endpoint。本计划的默认确认性 endpoint 固定为：

\[
\Delta_{work}=\frac{\sum_{r\in test} [Work^{baseline}_{miss}(r)-Work^{candidate}_{miss}(r)]}{\#\{test\ requests\}},
\]

其中 candidate 是 train/dev 冻结的 forward-value cache policy，baseline 是 6.2 按 dev 规则选出的单一 strongest identity-free baseline；两者在同一 `W_primary/C_primary/namespace/action semantics` 和完整 rollout scored window `E_primary` 上配对 replay。`E_primary` 明确给出从共同初始 cache state 开始的 warm-up events、计分 events、stream 结束/drain 规则及纳入分母的请求；`N_primary` 只约束 fixed-horizon demand/one-step action-value 标签，不进入完整 rollout endpoint。`Work_miss(r)` 由该请求未命中的最长前缀 token 区间和冻结的 `cost_primary(model, hardware, prefix_length)` 计算，单位为 estimated prefill work/request；同时报告未加权 token/request 版本。主要聚合对 `E_primary` 内实际 request 等权，不能改成 node-weighted 或只对有 reuse 的请求求平均。区间和重采样单位遵循 13.5：若 rollout 含共享 cache 或跨 lineage 干扰，必须以独立 workload stream 为最外层单位；只有无跨 lineage 干扰的分析才能以 lineage 为独立簇。

若研究问题改为其他 endpoint，必须在任何 test label、test replay 或 test aggregate 可见前替换上述默认项，并同时冻结 main contrast、方向、单位、聚合权重、`SESOI_F01`、置信水平和区间算法；test 后不得在候选 endpoint 间切换。

确认性 registry 至少包含：数据快照 hash、eligibility 规则、split/grouping hash、`W_primary/C_primary/N_primary/E_primary`、namespace 映射版本、serializer/tokenizer/block 规则、candidate 与 baseline artifact、one-step target 的焦点/替代动作和 `pi_cont`、`cost_primary`、`SESOI_F01`、样本量目标、缺失/删失处理、随机种子、唯一 main contrast、成对单侧 95% 上下置信界算法、次要 family 及多重比较方法。任一字段未冻结，test 保持 sealed，结果只能标为 exploratory。

任何把 full-rollout avoided work 称为 cache-management utility 的 F0 endpoint，都必须在打开 `T_F0` 前让进入该 contrast 的 action/policy family 通过 15.4 的独立 simulator--engine conformance。Conformance 只使用 train/dev 后冻结的 artifact 与独立 validation workload，不得查看 `T_F0`。若预注册 main candidate 或 comparator 未通过，则该管理 contrast 为 Inconclusive；此时可以报告 policy-independent demand label 或 trace-level token-reuse potential，但不能据此触发 F0 Go 或 Stop。

辅助指标：

- future-access AUPRC；
- absolute/relative AUPRC change；
- integrated Brier score；
- calibration/reliability；
- censoring-aware concordance；
- hit tokens、miss tokens、weighted hit rate。

Event-count 标签同样执行 cutoff：fixed-`N` count/binary 与 one-step utility 只纳入在冻结 stream cutoff 前完整观测到 `N` 个后续 eligible events 的 focal decision；不足 `N` 的尾部样本标为 right-censored，不得缩短 horizon 或当作“无返回”。Next-distance/survival 可保留这些样本并使用 censoring-aware 方法。Wall-clock survival 还需明确 observation cutoff、right censoring 和 termination/close competing event；MAE 只能在固定窗口内实际观察到 return 的条件子集上作辅助指标。

---

## 七、F0.2：Oracle-Session Residual Utility

### 7.1 核心比较

在完全相同决策事件和输入权限下比较：

1. `A`：5.2 定义的 identity-free causal features + fixed raw-history retrieval；
2. `A+S_identity-free`：在 `A` 的固定预算历史上加入 identity-free causal summaries；
3. `A+L`：只把 `A` 的历史候选关系替换为 oracle linkage；
4. `A+L+S`：oracle linkage + 与 identity-free 条件同构的 causal session summaries。

在 test sealed 时，用预注册 dev metric 在 `A` 与 `A+S_identity-free` 中选出唯一 `B_IF`（strongest identity-free condition），并冻结其 artifact。默认确认性 contrast 为 `A+L+S - B_IF`；若 dev 选中 `A`，不得仍以较弱的 `A+S_identity-free` 作 test 对照。`A+L - A`、`A+L+S - A+L` 和未被选中的 identity-free 条件仅作预注册次要诊断。

这避免把“知道 session ID”和“拥有人工丰富 oracle 状态”混为一谈。A+L 的模型与 policy 不得直接读取 oracle lineage label、最终 session 大小或按 ID 预计算的 future utility；oracle 只控制 5.2 定义的过去原始记录检索关系。所有组必须共享同一训练 procedure、模型容量、决策时刻、外生请求流和初始 cache state，只有预注册消融字段可以不同。完整 rollout 中每个 policy 的后续 cache state 由其自身动作内生演化，不能强行共享；比较使用同一外生流上的 paired policy difference。若另做 fixed logged-state 的单步 action-value 分析，必须单独命名 estimand，且不能用它替代完整 rollout 的 cache-management 结论。

### 7.2 主要问题

- session linkage 是否改善 total future block value，而不只是 session-specific reuse？
- 增益主要来自 within-session reuse，还是也改善 cross-session/global decisions？
- 增益是否被 prefix-aware baseline 覆盖？
- session summaries 是否只重复编码 prompt length/turn index？
- 增益能否转成预注册 cache endpoint，而非只提高分类指标？

### 7.3 Go / Stop / Inconclusive 使用区间而非“未显著即无效”

正式实验前定义 F0.2 的 smallest effect size of interest `SESOI_F02`，例如：

- avoided prefill work 相对提升至少 `δ_cache`；或
- 端到端验证后对应 TTFT/GPU work 至少提升 `δ_system`。

默认确认性 main contrast 固定为 `A+L+S - B_IF`，endpoint、单位、`W_primary/C_primary/E_primary`、cost function、聚合权重和 paired interval 算法与 6.3 的 `Delta_work` 相同。`A+L - A` 与 `A+L+S - A+L` 为预注册次要 contrast；不得在看到 test 后三者择优。若要把 linkage-only 设为主问题，必须在 test sealed 时替换 registry 中唯一 main contrast。

`SESOI_F02` 默认以 `estimated prefill work/request` 的绝对差给出，并与 main contrast 同尺度。若业务依据最初是相对提升，必须在 train/pilot 上用冻结 reference workload 转换成绝对 `delta_cache`，同时把相对版本降为次要指标。具体数值必须由独立 pilot 或外部硬件成本在读取 confirmatory test 前写入 registry；当前数据本身若同时用于估计方差，只能使用 train/pilot split，且该 split 永不进入最终区间。没有写入数值时自动判为 Inconclusive，不允许用“方向为正”替代 `SESOI_F02`。

对预注册方向为“越大越好”的 main contrast，冻结同一估计器对应的单侧 95% 下界和单侧 95% 上界（等价地，可冻结一个双侧 90% 区间）作机械决策，不得看结果后改置信水平：

- **Go**：单侧置信下界不低于 `SESOI_F02`；
- **Stop session-aware RQ0**：单侧置信上界低于 `SESOI_F02`，即可排除实际有用增益；
- **Inconclusive**：其余情况，包括上下界跨越 `SESOI_F02`；补样本、真实时间线或更可靠 simulator，不能把“未拒绝零假设”写成“没有价值”。

多 horizon、多容量和多个预测指标属于次要分析，应控制多重比较；不能以“任一指标显著”作为 Go。

---

## 八、F0.3：Family Objective Exploration

### 8.1 目的

在不等待 anonymous RQ0 完成的情况下，先回答 RQ1 的目标定义：什么跨 session 聚合能改善 total future KV value、return hazard 或 policy utility？

### 8.2 不存在天然 oracle family

- source/project/application label 称为 **proxy strata**；
- 语义相似、模板相似、工具相似不自动等价于 management family；
- 不能用完整数据的未来结果构造 family，再在同一数据上证明 family 有用。

### 8.3 合法探索方式

1. 用不含结果标签的外部 provenance proxy 作参照；
2. 用 train-only 历史特征学习 grouping；
3. 在 held-out session/task 上评估 A+L+S+P 相对 A+L+S 的残余增益；
4. grouping 超参数做 nested validation；
5. 报告不同目标下 family 是否一致，防止“为每个指标重定义 family”。

F0.3 只决定 RQ1 值不值得做、family 应优化什么，不声称 serving 已能在线识别 family。

---

## 九、F0.4：Identity Benefit–Metadata Cost Frontier

### 9.1 比较条件

在同一 trace、feature snapshot、外生请求流、初始 cache state、合法 action set、policy family 和 full-rollout endpoint 上比较。主前沿估计“部署每种身份接口后允许按该接口训练”的联合效应：每个 identity condition 可训练自己的 policy artifact，但模型族/容量、训练数据、超参数搜索预算、seed 数、dev-selection metric 与停止规则必须配平并预先冻结，test 上不能重选。另保留一个冻结共享 artifact 的诊断，用于分离纯信息效应与重训练收益，但不得与主前沿数值混用。

| 条件 | 可用身份 | 元数据成本 | 角色 |
|------|----------|------------|------|
| Identity-free | 无跨轮 ID | 0 | 下界/替代路线 |
| Frozen anonymous baseline | payload/time 推断 | 0 client bits，但有错误和计算成本 | F0 frontier 的低成本基线 |
| Learned anonymous inferred | payload/time 推断 | 0 client bits，但有错误和计算成本 | RQ0-A 完成后的候选 |
| Weak ephemeral tag | tenant-local nonce/短 handle | 少量 client/router bits | hybrid 候选 |
| Explicit session ID | 稳定 opaque ID + optional close | 完整协作 | oracle/工业基线 |

### 9.2 选择规则

F0.4 的前置门只评估 `Frozen anonymous baseline`，其 artifact 在 F0 train/dev 上冻结；不得提前使用完整 RQ0-A 的压力集/`T_RQ0A` 结果调 linker。16.1 中未加限定的 `anonymous` 均指该 frozen baseline。前置前沿只在 `T_F0` 上作预注册检验。RQ0-A 完成后，可在互斥的 `T_frontier2` 上加入 `Learned anonymous inferred` 并形成第二阶段前沿，但不能覆盖、重用或反向解释 `T_F0`；第二阶段结果只决定后续 prototype/部署，不作为当初进入 RQ0-A 的依据。

该 frozen baseline 不是事后挑出的匿名方法。Registry 必须在读取 F0.4 test 前冻结候选算法集合（默认只含 10.3 的 B1--B5，不含完整联合模型 B6）、各自超参数预算、特征版本、candidate retrieval/TTL/tie-break、训练与校准程序、唯一 dev 选择指标和确定性并列规则。F0 train、calibration、dev 与 F0.4 test 按 4.5 的 lineage 规则隔离：模型只在 train 拟合；每个候选只在 calibration 上选择一个满足预注册 `R_action` 与资源预算的阈值（默认在满足约束者中最大化 automatic-action coverage）；再在 dev 上以 6.3 同尺度的 full-rollout utility 选唯一 winner，并依次用更低 `R_action`、更低资源成本和固定算法序号打破并列。最终 artifact 必须封存 feature/normalization、模型参数、检索索引构造、阈值、TTL 和 serializer/tokenizer hash。某候选在 calibration 上无可行阈值即退出 dev 竞争；所有候选均退出则 frozen baseline 判为不可行，而不是改用 RQ0-A test 调参。

前沿比较不能只写 client bits。每个条件必须在相同请求流、policy family、训练预算和 endpoint 下计量其冻结 artifact 的：wire bytes/request、router/engine state bytes per active session、TTL/close/control messages、linker CPU/GPU 时间与 P95 延迟、错误恢复成本及目标动作下的污染损失。Weak tag 的 nonce 长度、作用域、TTL、碰撞/缺失/复用模型与 close 可靠性在 test 前冻结；explicit ID 的“optional close”必须拆成有/无可靠 close 两个条件。可比较的 summary 表至少同时给出 utility、风险上界和资源成本，不能把这些异质量未经价值函数直接压成单一分数。

对 anonymous/weak 条件 `x`，utility recovery 预定义为同一 paired stream 上

\[
rho_x=\frac{U_x-U_{IF}}{U_{EXP}-U_{IF}},
\]

其中 `U` 是 6.3 同尺度的 full-rollout avoided-work utility。这里的 `IF` 机械地定义为 7.1 在 test sealed 时选出的 `B_IF` 完整 artifact，而不是泛指 6.2 的某个 strongest baseline：它必须连同 feature/state 表示、训练参数、candidate retrieval、action threshold、policy wrapper、资源预算、serializer/tokenizer 和 hash 一起封存；除非两者 artifact hash 相同，不得用 F0.1 baseline 替换。`EXP` 则是在相同模型族、训练数据、搜索预算、dev metric 和 tie-break 下选出的唯一 explicit-ID 完整 artifact。Registry 同时记录二者候选集合、组合方式、选择 metric、tie-break 和 hash，因此 `U_EXP-U_IF` 不能在 test 后重组。Registry 必须冻结 ratio interval 算法和 denominator floor `g_frontier>0`；只有 `U_EXP-U_IF` 的单侧下界达到 `g_frontier` 才解释 `rho_x`，否则前沿 utility recovery 为 Inconclusive。

Registry 必须分别冻结 linkage 安全统计量 `FMR_attach` 与目标 cache action 的主风险统计量 `R_action`。纯 linker 或只读 shadow telemetry 可只以 `FMR_attach` 为主安全门；但只要 identity 输出驱动 retain、routing、prefetch、share、pin、free 或其他 cache action，`R_action` 就必须另行定义为 stream-level action contamination 或使用冻结损失权重的 action-weighted loss，不能取 `FMR_attach` 本身，也不能用 attach 门替代。两者的分母、独立单位、零机会处理和区间算法分别冻结；其他风险只作分解。

前沿的预算与选择规则也必须在 test 前数值化：为目标动作冻结最低 utility recovery `rho_min`、`R_action` 上界 `r_frontier`、wire/state/latency/compute 上限和 client-change feasibility 判据。条件 `x` 只有在 `rho_x` 的单侧置信下界达到 `rho_min`、`R_action` 单侧上界不超过 `r_frontier`，且所有资源成本上界不超预算时才算 feasible。反向的确定失败也必须机械化：`rho_x` 的单侧上界低于 `rho_min`、`R_action` 的单侧下界高于 `r_frontier`，或任一资源成本的单侧下界高于预算，均表示对应维度确定失败；上下界跨门槛只表示 Inconclusive。

置信支配必须基于同一 paired stream 上的**差值区间**，不能比较两个条件各自的边际区间。Registry 为 utility、风险和每项资源成本冻结方向、non-inferiority margin `m_j`、严格改善门槛 `s_j>0` 及 simultaneous-confidence/多重比较方法；统一把差值写成“正值有利于 `x`”（例如 `D_U=U_x-U_y`、`D_R=R_y-R_x`、`D_cost=Cost_y-Cost_x`）。只有所有维度的同时单侧下界均不低于 `-m_j`，且至少一个预注册维度的下界达到 `s_j`，才称 `x` 置信支配 `y`。价值维度不可约、任一必要差值跨越 margin 或没有条件同时过门时，结论必须是 Inconclusive，不得事后用主观“明显支配”排序。

纯匿名不是默认正确路线。只有当它相对 minimal/hybrid identity 同时满足上述冻结的 utility、风险、client feasibility 和资源预算，且处于非支配前沿，才进入完整 anonymous RQ0。若 1–2 bits 或短时 opaque handle 就能稳定恢复大部分收益，研究问题应转为：

> **多少协作信息、何种生命周期和可信边界，足以恢复 agentic KV 管理收益？**

这与现有工业路线依赖 `session_id`、`program_id`、`agent_hints` 或 router knowledge 的事实一致（`docs/30_agentic_serving_request_surface_survey.md:21-30`、`docs/30_agentic_serving_request_surface_survey.md:63-77`）。

---

## 十、RQ0-A：Anonymous Calibrated Selective Linker

### 10.1 在线算法框架

不做强制全量聚类，而采用 retrieve–score–calibrate–abstain：

1. 从按在线规则维护的 active candidate index 检索候选；
2. 计算当前 request 与候选 cluster 的 pair score；
3. 比较第一/第二候选及 score margin；
4. 只有校准风险低于目标动作预算时才接受；
5. 否则创建新 cluster/abstain。

Candidate 只能按在线可见 idle timeout、容量或显式 close 过期；不得使用真实最后一轮或未来 return 移除。

### 10.2 信号消融

#### S1：时间

- candidate last-seen gap；
- candidate age；
- active candidate 数；
- 只由已观察记录形成的 return cadence。

#### S2：精确/归一化历史连续性

- exact message/token prefix；
- longest common prefix；
- suffix containment；
- 去除 whitespace、JSON key order、timestamp、UUID、临时路径后的 normalized continuity。

#### S3：结构

- role sequence；
- tool-name sequence；
- call/result pairing；
- message 类型和数量变化；
- message/token growth。

#### S4：内容

- text shingles/Jaccard；
- normalized edit distance；
- 最近 user/tool 内容相似度；
- 可选 embedding。

#### S5：候选 cluster 的因果历史状态

- observed turn count；
- 已观察工具模式；
- context growth；
- return cadence。

必须报告 time-only、prefix-only、structure-only、content-only、state-only、联合模型，以及去掉 exact-prefix 后的结果。

### 10.3 Baselines

- **B0 All-singleton**：每个 request 新建 cluster；
- **B1 Most-recent/time-only**；
- **B2 Exact-prefix trie**：clean ceiling；
- **B3 Normalized-prefix**；
- **B4 Structure-only**；
- **B5 Content similarity**；
- **B6 Joint calibrated selective linker**；
- **B7 Weak ephemeral tag**：hybrid frontier；
- **B8 Explicit/oracle session ID**：上界。

---

## 十一、压力负载

### 11.1 Synthetic interleaving

保留 session 内顺序和原始相对 `pre_gap`，对 session 启动时间应用预注册 workload model。至少包含：

- active concurrency `K ∈ {1,4,16,64}`；
- Poisson-like、bursty/heavy-tail、adversarial；
- 每配置多个 seeds，但 seed 只作重复测量；
- same-project、same-model、相似 tool flow 的对抗性交错；
- candidate idle timeout sensitivity。

### 11.2 必测压力集

#### P0 Clean ceiling

完整历史、不扰动，只检查 pipeline 和 exact-prefix 上界。

#### P0b Idle-gap and resume sweep

对每个 continuation stratum 预先分桶真实 idle gap（建议 `<5m`、`5–30m`、`30m–2h`、`2–24h`、`>24h`），并做 counterfactual gap multiplier `×0.1/×1/×10`。TTL、active-window 和 time feature 只允许用 train/validation 选择；test 上冻结。所有主指标必须按 idle-gap bucket 分层，防止只证明短时连续请求可链接。

#### P1 Same-proxy/same-project concurrency

混合同 project/system/tool strata，防止将工具集合或 system prompt 当身份。

#### P2 Same-model repeated task / clone

- 首请求完全相同；
- 前若干轮可完全相同；
- 之后由 tool result 或用户反馈分叉。

分叉前 latent sessions 信息论上不可区分，不允许要求匿名模型猜出唯一 ID。

#### P3 Causal history truncation

只保留最近 2/4/8 turns，或删除最老 25%/50%/75%，并分别保留/缩短 system prompt。

#### P4 Causal summary/rewrite

只基于当时可见历史生成 task summary、当前计划和最近 tool result；禁止读取未来。

#### P5 Ephemeral-field drift

重编号 tool call ID，改变 whitespace/JSON key order，替换 timestamp、UUID、PID、临时路径和 nonce。

#### P6 Lexical redaction

屏蔽 repo、issue/task ID、绝对路径和唯一日志 hash。原文与 redacted 分别报告。

#### P7 Combined core stress

至少组合 same proxy + same model + concurrency 64 + 50% truncation + tool-ID drift + repeated/clone task。

### 11.3 确认性 robustness gate

Robustness 不能用“各分层方向大致一致”判定。Registry 必须在 test 前指定：一个 serving-realistic non-clean-prefix channel、一个 held-out source/project 泛化分层、各自的 reference stratum、唯一主 utility/risk contrast、方向、non-inferiority margin、独立单位、置信水平和 simultaneous-confidence/多重比较方法。Non-clean-prefix 默认在同一冻结 stream 上成对比较；held-out source/project 无法成对时，必须使用按 13.5 独立单位构造的分层差值区间，不能把 request 当独立样本。

这些门按阶段分别注册和判定，不能跨 pool 借证据：`T_F0` 中只评估 9.2 的 Frozen anonymous baseline 及 F0.1--F0.4 contrast，其 non-clean-prefix 与 held-out source/project strata 是 16.1 的前置 Go 门；`T_RQ0A` 中另行评估冻结后的完整 learned linker、P0--P7 与 attach/coverage 风险，其 robustness 只服务于完整 RQ0-A 和 16.2 prototype 决策；`T_RQ0B` 中再对 downstream policy 的闭环 utility/risk 注册对应 robustness。`T_frontier2` 只承担第二阶段 identity frontier，除非在揭示前为它另行注册并供给独立 strata，否则不得补做前三者任一 robustness 门。前一 pool 的通过不能替代后一 pool，后一 pool 的结果也不能反向授权 16.1。

所谓 held-out source/project，要求该 source/project 顶层 group 完全未参与模型、特征、归一化、阈值、generator 或规则选择，并按 4.5 整组只进入对应 stage pool。其 confirmatory reference 也必须在 registry 中指定为该 stage pool 内另一组预先冻结、同样未参与拟合的 source/project groups；这估计的是预注册 unseen-group 间的稳健性。若 reference 的同一 source/project 曾进入 train/dev，则只能称为 in-domain reference，不能同时声称该 group held out；两种 estimand 必须分开报告。

对每个 mandatory robustness stratum `q`，必须同时执行 **stratum 内绝对门** 和 **相对 reference 的 non-inferiority 门**。绝对门沿用该 stage/gate 已预注册的确认性判据：F0.1 要求 candidate--baseline 的下界达到 `SESOI_F01`；F0.2 要求 `(A+L+S)-B_IF` 的下界达到 `SESOI_F02`；F0.4 要求该 stratum 内 `U_EXP-U_IF` 的下界达到 `g_frontier`、`rho_ANON` 的下界达到 `rho_min`、`R_action` 与各资源成本的上界不超过预算，且 anonymous 未被 weak/explicit 置信支配；RQ0-A 要求 `Coverage_eligible` 下界达到 `c_min`、`FMR_attach` 上界不超过 `r_attach`，若驱动具体动作还要求独立的 `R_action` 上界不超过 `r_action`；RQ0-B 要求 downstream main contrast 下界达到 `SESOI_DU` 并通过其动作风险门。F0.3 若注册为确认性门，则使用 `(A+L+S+P)-(A+L+S)` 的预注册绝对判据。

另令 `C_{q,j}` 表示该 stage/gate 在 registry 中预注册的唯一主 contrast，并定义 `D_{q,j}=C_{q,j}-C_{ref,j}`，统一使正值表示相对 reference 更好。不同 gate 不得共用未经重新定义的 contrast。风险用反向编码保持“正值更好”，例如 F0.4 可写为 `D_{q,R}=(R_{IF}-R_{ANON})_q-(R_{IF}-R_{ANON})_{ref}`；若 coverage 是该阶段的决策门，则另注册同方向的 coverage contrast。每个维度 `j` 冻结允许退化量 `m_{q,j}`：

- **Pass**：该 stratum 的全部绝对门通过，且所有 mandatory `D_{q,j}` 的同时单侧下界均不低于 `-m_{q,j}`；
- **Fail/Pivot evidence**：任一绝对门达到其预注册的确定失败界，或任一 mandatory `D_{q,j}` 的同时单侧上界低于 `-m_{q,j}`；
- **Inconclusive**：其余情况，包括绝对门或相对门的区间跨越判定边界。

Reference-relative non-inferiority 不能替代 stratum 自身的 SESOI、coverage、risk、resource 或 frontier 判据。Clean、单一 source 或 observer-only channel 的通过也不能替代上述 mandatory robustness。只有 Pass 才允许外推相应 stage 的 Go；确定 Fail 可作为 16.3 的 Pivot 证据；区间重叠只能补独立样本或改进 workload/measurement。

---

## 十二、Observational Equivalence 与正确性定义

### 12.1 集合值 ground truth

若两个 latent session 在当前时刻的全部可见 payload/history 完全相同，则单靠匿名输入无法区分。Workload generator 必须标记 `observational_equivalence_set`。用于主 coverage endpoint 的 `eligible_identifiable` 必须由冻结的 canonicalization、candidate-availability 规则和 equivalence-set 生成器在看 linker 输出前机械计算；主定义为：真实 predecessor 在当时 active candidate set 中，且该事件不属于大小大于 1 的 observational-equivalence set。pilot 后不得按某个模型的错误、confidence 或事后人工判断删减 eligible denominator，其他近似定义只作 sensitivity。

对这类事件：

- 不能把随机猜中真实 ID 当作可复现能力；
- 不能安全合并 latent clusters；
- 正确安全动作是 abstain/new cluster，或要求 weak identity；
- coverage 门槛只作用于预先定义的 identifiable subset。

### 12.2 三层正确性

1. **Predecessor-edge correctness**：是否选择真实直接前驱；
2. **Strict contamination correctness**：接受链接前后，目标 cluster 是否含任意其他 ground-truth session；
3. **Final clustering correctness**：最终 cluster 的 fragmentation/impurity。

一次早期误合并后，即使后续 request 的真实 session 已存在于污染 cluster 中，也不能把后续写入计为安全正确。

---

## 十三、RQ0 指标与统计

### 13.1 冻结 online 原子决策

每个新请求到达时，在读取该请求 payload 并冻结当时的 active history 后，先记录一个不可事后改写的原子动作：

\[
D_t \in \{\text{attach-to-existing } c,\; \text{new-cluster},\; \text{abstain}\}.
\]

每个 `attach-to-existing c` 在动作前可输出两个不同分数。`p_predecessor` 是“cluster 中存在当前请求真实 session 的合法 predecessor”的概率，只作 linkage 诊断；用于自动动作阈值、calibration 和 risk--coverage 的 operational confidence 必须是

\[
p_{safe}=P(c\text{ 在执行该 attach 后仍只含当前请求的真实 session}\mid\text{冻结 snapshot}).
\]

因此，一个同时含正确 predecessor 和其他 session 的污染 cluster 可以有高 `p_predecessor`，但必须有低 `p_safe`。两个概率都只能由当时可见信息计算，不得用最终 cluster 或未来请求重算；registry 冻结其 calibration set、loss、阈值和 fallback。`new-cluster` 和 `abstain` 不是 accepted link。

### 13.2 主安全指标：Strict Contamination FMR

Primary denominator 固定为所有自动 `attach-to-existing` 决策，污染状态在执行该动作并写入当前请求后判定：

\[
FMR_{attach}=
\frac{\#\{t:D_t=attach,\; c_t^{post}\text{ 含当前请求所属真 session 之外的任一真 session}\}}
{\#\{t:D_t=attach\}}.
\]

一次早期误合并后，对污染 cluster 的后续 attach 继续计为不安全；另报告“首次污染事件”以避免重复计数掩盖 root cause。同时报告：

- lineage-level `P(any false attach)`；
- predecessor-edge error；
- 每 1,000 request 的首次污染事件；
- 污染后受影响 request/state write 数；
- first-request false merge；
- 按 source/project/model/concurrency/扰动分层结果。

### 13.3 Risk–coverage 与 abstention

对 identifiable subset：

\[
Coverage_{eligible}=
\frac{\text{post-attach pure 且目标 cluster 含真实直接 predecessor 的 automatic attaches}}
{\text{all identifiable requests with an available predecessor}}
\]

另行报告：

- all-request auto-action coverage；
- `new-cluster` false-split rate，不混入 false-merge denominator；
- unidentifiable event 比例及 abstention/new-cluster rate；
- 对 observationally unidentifiable clone，将 abstain 或保守 new-cluster 视为安全动作，强制 parent match 仅作诊断；
- final-cluster contamination、B-cubed、pairwise F1、fragmentation 和完整 session 恢复率。

### 13.4 Calibration 与成本

- reliability、Brier、ECE；
- threshold 下的 contamination-risk/coverage curve；
- candidate retrieval/scoring P50/P95；
- active-session scaling；
- candidate index 内存和每 session state；
- 不允许扫描全部历史 request。

工程目标先在 dev/pilot 上根据目标部署确定，不把未经功效分析的 `<5 ms` 写成科学门槛。

### 13.5 统计独立单位

- 对不共享 cache、也不发生跨 lineage 候选竞争的 linker 指标，原始 task/clone lineage 可作为最外层重采样簇；同 lineage 的模型运行、seeds、扰动和派生 stream 必须整体重采样；
- 对共享 cache、全局 candidate index、false merge 传播或任何跨 lineage 干扰，单个 lineage 不是独立单位。必须先冻结若干彼此独立采集或生成的完整 workload streams；每个 bootstrap replicate 整体抽取 stream，在 stream 内保留原 interleaving、共享状态和污染传播，并从初始状态重放所有被比较 policy；
- 同一 held-out stream 在各 policy 下配对。若只有一条真实 stream，则 block/bootstrap 只能作时间相关 sensitivity，确认性 CI 以独立外部 streams/采集日/隔离 shard 为单位；没有这些单位时 utility 与污染上界均标为 Inconclusive；
- 使用与上述干扰结构一致的 paired hierarchical/bootstrap；不得仅用 lineage-clustered interval 包装共享状态 rollout；
- decision-level binomial interval 仅作描述，不能用来证明安全上界；synthetic seed 只传播 workload-model 不确定性，不增加经验独立样本量。

---

## 十四、样本功效与风险预算

### 14.1 不预注册当前数据无法证明的 0.1% 结论

现有 767 sessions 若 test 约 20%，只有约 153 个独立首请求。即使零错误，一侧 95% 二项上界仍约 1.9%，不足以证明 0.1%。把同一 session 重排 20 次不能变成 20 倍独立证据。

因此正式实验前必须：

1. 按与 estimand 干扰结构匹配的独立单位做 power analysis：无共享状态指标用 lineage/session，共享 cache/global index 指标用独立 workload streams/采集日/隔离 shard；
2. 为主要 endpoint 用独立 train/pilot 单位上的 paired policy difference 估计方差，冻结最小所需 test 单位数、目标 power、alpha、预期失访/排除率和停止规则；
3. 安全率 endpoint 按目标上界反推所需独立 workload units 与污染机会，并与 utility endpoint 分开计算；
4. 样本不足时报告数据支持的上界，或收集新的独立 sessions；
5. 不因无法达到任意阈值而伪造确定结论，也不得在未登记的 interim look 后提前停止。

### 14.2 风险预算必须按动作分层

不同动作不能共用一个 FMR 门槛：

| 动作 | 风险 | 初始证据要求 |
|------|------|--------------|
| Shadow telemetry/label | 低 | calibration + 描述性上界 |
| Soft priority/routing affinity | 中 | lineage-level 风险上界 + 可回退 |
| Bounded TTL/retain | 中 | 资源上限 + contamination 分解 |
| Cross-session share/prefetch/strong pin/bulk free | 高 | 更低污染预算、更多独立样本、引擎保护与回滚 |

具体预算必须结合动作代价、样本功效和系统保护在 pilot 后、test 前冻结。

---

## 十五、RQ0-B：下游闭环

### 15.1 身份条件

对相同到达流、容量、block size 和决策事件比较：

1. identity-free；
2. anonymous inferred；
3. weak/minimal identity；
4. explicit/oracle session。

### 15.2 预测闭环

重复 F0 的 total future value/return 任务，报告：

- inferred 相对 identity-free 的绝对和相对增益；
- oracle gap 及其置信区间；
- 只有 oracle gap 的单侧置信下界达到预注册 `g_oracle > 0` 时，才报告 recovered oracle-gap fraction；denominator、区间算法与最低恢复比例 `rho_DU` 必须随 main contrast 一并冻结；
- false merge、污染、false split 和 abstention 的成本分解；
- clean 与压力集差异。

### 15.3 Cache simulation 闭环

比较：

- LRU；
- prefix-frequency；
- strongest identity-free forward-value policy；
- anonymous inferred-session-aware；
- weak-ID-aware；
- oracle-session-aware。

模拟器至少显式实现：

- content-addressed radix/shared nodes；
- block refcount 和 in-flight 不可淘汰约束；
- prefill/decode 分配时点；
- admission/eviction 时点；
- tier restoration/offload（若作分层结论）；
- scheduler 与 residency 的必要反馈。

### 15.4 Simulator 先验证，再谈管理收益

#### 15.4.1 可执行 shadow/replay contract

Validation harness 必须固定并归档：SGLang commit/container digest、model/tokenizer/serializer hash、block size、GPU/并行配置、scheduler flags、cache capacity/tier、random seed、policy artifact hash、request payload 与 arrival timestamp。每个 policy × workload × capacity × concurrency cell 都从空 cache、空 request table 和相同 RNG state 重启；先完整 replay `E_primary` 的 warm-up events，再对 scored events 计分，禁止从另一 policy 的末态继续。

这里的 instrumented SGLang adapter 是 **Phase 0 的隔离验证夹具**：只暴露冻结 observation、执行/拒绝 action、导出 canonical state/event，并在专用 validation workload 上运行；它不得接收匿名 linker 输出、改变生产请求路由，或作为 serving 收益实验。第十七节/Phase 5 的 SGLang shadow prototype 则是在 RQ0-A/RQ0-B 通过后接入真实 serving path 的 observer/soft-action 系统。两者可复用只读 schema 和事件编码，但 artifact、workload、部署权限与决策目的必须分别 version/hash；conformance adapter 通过不等于 prototype 通过，也不授权任何在线动作。

同一 canonical request stream 运行两种互补模式：

1. **Action-tape conformance**：冻结 policy 在 5.1 合法 observation 上输出带全序号的 action tape；simulator 与 instrumented SGLang adapter 分别从相同初态执行该 tape，用于验证 action legality 和状态转移；
2. **Closed-loop conformance**：同一冻结 policy artifact 分别读取 simulator/engine 当时的合法 observation 并独立决策，用于发现 observation、ordering 或反馈差异。主结果对应的 family 必须两种模式都通过；只通过 action tape 不能证明 closed-loop policy 正确。

每条 engine/simulator 事件写入同一 versioned schema：`stream_id, seq_no, arrival_time, request_id, decision_point, policy_hash, namespace, canonical_node_key, action, accepted/rejected_reason, cache_state_digest_before/after, refcount, in_flight_pin, tier, cached_tokens, miss_tokens, prefill_work`。`canonical_node_key` 由 namespace、parent key、token block IDs 和 block length 定义；并列候选按 registry 中固定的 total-order tie-break。Harness 先校验输入/action-tape hash 和事件序号无缺失，再从首个分歧输出最小 counterexample；人工对齐日志不是验证。

Handcrafted microtraces 必须分别触发 shared-prefix refcount、in-flight pin、ancestor cascade、simultaneous admission/eviction tie-break、tier restore 和非法 action rejection。独立 validation workloads 必须覆盖每个将进入确认性结果的 action/policy family，以及至少两个容量和两个并发 strata；它们与 train/dev 调参 workload、confirmatory test 都按 provenance 分组隔离。

#### 15.4.2 通过标准与 fail-closed 规则

逐 family 同时计算：

- per-request `cached_tokens/miss_tokens` 的绝对差总和除以 engine 总 prompt tokens，记为 `Err_token`；
- canonical admission/retention/eviction/cascade/restore/reject 事件的 ordered-key exact-match rate，记为 `Match_event`；
- scored window 累积 prefill work 相对误差，记为 `Err_work`；
- action legality、in-flight protection、refcount 和 cache-state digest 的首个分歧位置。

通过要求固定为：所有 mandatory microtrace 字段 exact match；独立 validation workload 上 `Err_token <= epsilon_token`、`Match_event >= tau_event`、`Err_work <= epsilon_work`，且每个预注册容量/并发 stratum 分别通过。Registry 在运行 validation 前冻结 `epsilon_token/tau_event/epsilon_work`、允许差异白名单及理由；白名单只能覆盖不进入 policy observation、action legality、residency、token/work accounting 或主 endpoint 的 telemetry。任何影响这些字段的差异、未解释的首个分歧、缺失事件或 hash 不一致均直接判该 family 失败，不能用总体平均抵消。

除 microtrace 外，每个 action/policy family 都在独立 workload 上单独判定；只验证 LRU 不能授权 forward-value 或 session-aware 结论。未通过的 family 从 confirmatory candidate set 中删除并保持 test sealed；若删除对象是预注册 main candidate，结果为 Inconclusive，不能临时换成次优 candidate。若所有候选均未完成或未通过，结论只能写成 **trace-level token-reuse potential**，不能写成真实 cache management/TTFT/throughput gain。若 closed-loop simulator 未建模并验证 scheduler/residency feedback，结果也不能外推到 TTFT/throughput；avoided tokens 只能经冻结的模型/硬件 cost model 报为 estimated prefill work，并另行做系统实测。

---

## 十六、Go / Pivot / Stop / Inconclusive

### 16.1 Go 到 anonymous RQ0-A

`T_F0` 遵守 4.5 的原子 reveal 约束：F0.1--F0.4 的冻结 artifact 必须先全部运行完毕，以下规则只用于揭示后的 serial gatekeeping 解释，不允许根据前一道门的可见结果改动后续 gate。

必须同时满足：

1. 支撑以下各门的每个 action/policy family 均在打开 `T_F0` 前通过 15.4 的独立 conformance；未通过或未验证即为 Inconclusive，不能以 simulator 数值触发 Go/Stop；
2. F0.1 的预注册 candidate 相对单一 strongest baseline 的 `Delta_work` 单侧置信下界达到 registry 中的 `SESOI_F01`；若上界低于 `SESOI_F01`，则当前 F0.1 candidate advancement 确定失败且本协议整体不得 Go 到 RQ0-A，但结论仅限于“该 candidate 未超过 strongest baseline 达到 SESOI”，不得写成 cache value 不存在、不可预测或 strongest baseline 无效；其余情况为 Inconclusive；
3. F0.2 唯一 main contrast `A+L+S - B_IF` 的单侧置信下界达到 registry 中的 `SESOI_F02`；
4. 按 9.2 的冻结规则，anonymous 条件通过 `rho_min/r_frontier` 与资源预算，且未被 weak/explicit 条件置信支配；
5. 功效分析达到预注册 test 独立单位数，且前沿目标动作风险的单侧上界可与 `r_frontier` 比较；
6. 在 `T_F0` 内按 11.3 预注册的 non-clean-prefix 与 held-out source/project robustness contrast 通过各自 non-inferiority margin；`T_RQ0A` 的后续 robustness 不能反向补门，否则不得把 clean/single-source 结果外推为 RQ0 Go。

### 16.2 Go 到 SGLang shadow prototype

在 identifiable core stress subset 上：

- `T_RQ0A` 内为 learned linker 预注册的 non-clean-prefix、P0--P7 与 held-out source/project robustness 全部通过 11.3；不得沿用 `T_F0` frozen baseline 的通过结果；
- anonymous linker 的 `FMR_attach` 单侧上界不超过预注册 `r_attach`，且 shadow/soft-action 的唯一主风险统计量 `R_action` 单侧上界不超过其动作专属 `r_action`；与干扰结构匹配的 lineage/stream contamination-risk 作为预注册安全分解报告；
- dev 冻结阈值在 held-out test 上同时满足 `Coverage_eligible` 下界 `c_min`、`FMR_attach <= r_attach` 与 `R_action <= r_action`；
- `T_RQ0B` 内 inferred 相对 identity-free 的预注册 downstream main contrast 下界达到 `SESOI_DU`，且该 downstream policy 在 `T_RQ0B` 内按 11.3 注册的 non-clean-prefix 与 held-out source/project utility/risk robustness 全部通过；`T_RQ0A` 的 linker robustness 不得替代该门。若 recovered-gap fraction 是决策门，还须其下界达到 `rho_DU`；
- simulator 已通过必要的 SGLang shadow 对齐，或论文明确只声称 token-reuse potential；
- 对 unidentifiable clones 自动 abstain，不假装识别。

### 16.3 Pivot 到 hybrid/minimal identity

满足以下任一预注册条件时 Pivot，不依赖事后定性判断：

- oracle main contrast 通过 `SESOI_F02`，但 anonymous 未同时通过 9.2 的 `rho_min/r_frontier`、资源预算或 `c_min`；
- 对当前决策对应的 stage pool，11.3 任一 mandatory truncation/summary/clone 或 held-out project/source robustness contrast 的同时单侧上界低于其 `-m_{q,j}`，形成确定 Fail/Pivot evidence；其他 pool 的结果不得替代或反向改写该判断，区间跨门槛仍为 Inconclusive；
- weak/minimal identity 通过全部预算并按 9.2 置信支配 anonymous；
- 所有条件均未形成可判定前沿时为 Inconclusive，而不是强行 Pivot。

### 16.4 Stop RQ0，保留 identity-free 路线

仅当 F0.2 main candidate 与 `B_IF` 的 action/policy family 已通过 15.4 conformance，且唯一 main contrast `A+L+S - B_IF` 的单侧置信上界低于 `SESOI_F02` 时停止。Conformance 未通过或未完成时只能判为 Inconclusive，不能把 simulator 不可信造成的低收益解释为 session state 无价值。`A+L - A`、预测标签、linkage accuracy 与其他 cache 指标只作预注册诊断，不能单独触发 Stop；若 main contrast 区间跨越 `SESOI_F02`，即使次要指标无显著差异也必须判为 Inconclusive。

可转向：global forward reuse value、eager prefix registration、prefix-aware scheduling、identity-free eviction 或 programmatic hint。

### 16.5 Inconclusive

- 样本不足以证明所需风险上界；
- F0.2 唯一 main contrast 或其 oracle-gap denominator 跨越预注册判定边界；
- synthetic workload model 对结论影响过大；
- simulator 尚未与真实引擎对齐。

此时应补数据/验证，不能强行 Go 或 Stop。

---

## 十七、通过后接入 SGLang

### 17.1 第一版只做 side-channel observer

结构化 tools/system/role 在 tokenize 后会被压平，现有规划建议在 API server tokenize 前提取结构信号，在 scheduler 旁路采集 prefix hit、cached tokens、retraction 和 timing（`docs/29_family_identification_framework_plan.md:440-450`）。

第一版应：

- 不改 prompt/token IDs；
- 不改 RadixCache correctness；
- 不直接接管 scheduler/cache manager；
- 维护最小 `RequestTable` / `SessionTable`、confidence 和 provenance；
- 记录冻结事件的 feature、decision、outcome；
- shadow mode 验证 simulator 和 calibration。

### 17.2 动作逐级升级

1. shadow telemetry；
2. soft priority/routing affinity；
3. bounded TTL/retain；
4. 只有获得足够证据后才测试 cross-session share、prefetch、strong pin、bulk free。

SGLang KvHints 的软、有界、可拒绝原则适合作为后续接口，而非让 inferred identity 直接操纵 cache internals（`docs/31_sglang_27574_programmatic_kv_cache_zh.md:98-107`）。

### 17.3 显式机制的正确位置

- explicit session ID 是 oracle/工业基线；
- weak tag 是必须正面比较的路线，不只是匿名失败后的补丁；
- inferred session 可选地输出等价 hint；
- `routing_key`/`extra_key` 不能直接当 family 相似度；
- hint API 不是自动 sessionization。

---

## 十八、阶段产物

### Phase 0：协议、审计与功效分析

- `trace_manifest.json`、lineage/split manifest 与互斥的 `T_F0/T_RQ0A/T_frontier2/T_RQ0B` pool hash；
- causal feature/event audit、clean-prefix/collision audit 和 workload-model manifest；
- online evaluator、strict contamination/risk--coverage/calibration 定义；
- P0--P7 generator、serving-realistic stream 和 observational-equivalence annotations；
- SESOI、主要 endpoint、样本功效、serial gatekeeping 和动作风险预算；
- simulator--engine conformance harness、mandatory microtraces，以及进入 `T_F0` 的 policy family 验证。

Phase 0 的 evaluator、generator、annotation rule、registry 与 stream hash 全部冻结后，才能打开任何确认性 pool。

### Phase 1：F0.1 Global forward value（`T_F0`）

- total/within/cross future value labels；
- strongest identity-free baseline；
- 仅对已通过 conformance 的 policy 报 full-rollout cache utility；
- Go/Stop/Inconclusive gate 结果。

### Phase 2：F0.2/F0.3/F0.4 前置门（`T_F0`）

- A、A+S_identity-free、A+L、A+L+S 配平消融；
- proxy-family held-out utility；
- frozen-anonymous/weak/explicit identity frontier；
- 按预注册 serial gatekeeping 作 RQ0 路线决策。

### Phase 3：完整 RQ0-A 与第二阶段前沿

- 在 `T_RQ0A` 上评估冻结的 learned anonymous linker；
- strict contamination、risk--coverage、calibration 与 hierarchical statistical report；
- unidentifiable-clone abstention 和 P0--P7 robustness；
- RQ0-A 结果冻结后，才在 `T_frontier2` 上与 weak/explicit 条件形成第二阶段前沿。

### Phase 4：下游闭环（`T_RQ0B`）

- identity-free/inferred/weak/oracle 对照；
- 新增 action/policy family 先做独立 simulator--SGLang conformance；
- prediction/cache utility 与 error-cost decomposition；
- Go/Pivot/Stop/Inconclusive。

### Phase 5：SGLang shadow prototype（仅通过后）

- tokenize 前 observer；
- scheduler side-channel outcome collector；
- minimal `SessionTable`；
- shadow telemetry；
- bounded soft-action experiment。

---

## 十九、最小下一步

在写复杂 linker 或修改 SGLang serving 策略之前，按以下顺序工作：

1. 用只读脚本重新生成数据/schema/prefix/collision 审计；
2. 建立 provenance-based lineage，冻结 train/dev/calibration 与互斥的 stage-specific confirmatory pools；
3. 定义冻结决策事件、causal feature matrix、online evaluator 和 observational-equivalence rule；
4. 在不拟合完整 linker 的前提下先实现并冻结 P0--P7 generator 与 serving-realistic stream；
5. 定义 total/within/cross future block value、SESOI、power、serial gatekeeping 和 synthetic workload sensitivity；
6. 跑 LRU、frequency、recency、dependency、简单可校准模型及 A/A+S_identity-free/A+L/A+L+S 配平消融；
7. 建立 simulator--engine conformance harness，并让将进入 `T_F0` 的每个 action/policy family 在独立 workload 上通过；
8. 全部 artifact/registry/hash 冻结后，才按 Phase 1--2 打开 `T_F0`；proxy-family objective 可并行探索，但不训练在线 family classifier；
9. 只有 F0 gate 支持后，才训练完整 anonymous selective linker，并依次使用 `T_RQ0A`、`T_frontier2` 和 `T_RQ0B`；
10. 只有下游闭环与 shadow 对齐通过后，才进入 SGLang serving 策略原型。

---

## 二十、一句话结论

> **形式上，第一个研究问题是 RQ0 Sessionization；执行上，第一个实验是 F0：先证明全局前看型 KV 价值可预测，再证明正确 session linkage 有独立管理价值，同时定义 family 的目标并比较 anonymous、weak 与 explicit identity。只有匿名推断位于收益—元数据成本前沿，才值得继续做完整 RQ0 和 SGLang 集成。**
