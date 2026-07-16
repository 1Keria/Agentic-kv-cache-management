# Agentic Serving：请求面改动与身份获取方式调研

> **研究决策更新（2026-07-16）**：本调研确认工业主流采用显式身份后，当前研究已选择显式 `session_id`，不再以匿名 Sessionization 为首篇工作的主线。新的 Family 是共享 exact token prefix 的 `Prefix Family`，不是应用/行为类别；见 [`docs/33_explicit_session_prefix_family_plan.md`](33_explicit_session_prefix_family_plan.md)。匿名身份恢复仅作为 future work。本文下文对“我们/当前设定”的匿名表述均保留为历史调研语境。
>
> 日期：2026-07-14  
> 背景：配合 `docs/29_family_identification_framework_plan.md` 回答——遇到「多 agent / 多轮 / 需要知道是哪次执行」时，现有工作会不会改 agent 请求面？怎么拿 session / program / 应用身份？  
> 范围：系统论文（Autellix、Continuum、InferCept、Parrot、PBKV/KVFlow 等）+ 引擎侧 RFC（SGLang / vLLM agentic-api）+ 编排层（NVIDIA Dynamo）  
> 结论先行：**主流靠显式声明或离线先验；因此当前研究直接采用显式 Session，把贡献空间收窄为 Prefix Family 的 residual cache-management utility。**

---

## 一、问题与调研目标

本调研最初检验 doc 29 的匿名设定：真实 serving 端点同时收到多种匿名、异构 agent 应用时，能否不依赖声明而做 sessionization + family identification。调研后的正式选择是：**不再要求引擎猜 Session 边界；由 client/router 显式提供 `session_id`，只研究 KV-compatible exact-prefix Family 的构建、价值估计与软策略反馈。**

本调研只回答两件事：

1. 现有 agentic serving 工作**会不会改 agent 请求面**（加 `session_id` / `program_id` / `agent_hints` / Semantic Variable 等）？  
2. 遇到和我们类似的「需要身份才能做跨轮 KV / 调度」时，他们选了哪条路？

---

## 二、总览：三条路径

| 路径 | 要不要改请求面 | 身份从哪来 | 代表 | 相对我们的位置 |
|------|---------------|-----------|------|---------------|
| **A. 显式声明** | 要（库包装 / 扩展 API / 可选 hints） | client / orchestrator 塞 id | Autellix、Continuum（program id）、Parrot、SGLang `agent_hints`、vLLM agentic-api、Dynamo | 实现简单，但**不能声称零配合** |
| **B. 不做跨轮身份** | 基本不要 | 无；单 request 启发式 | InferCept；默认 prefix cache | 零配合，但**管不到 session/family** |
| **C. 离线 / 已知应用** | 通常不要（评测侧假定） | 图 / 训练器 / 类型标注 | PBKV、KVFlow、Tempo 类 | 回避「匿名异构并发」设定 |

**目前的主流是 A**；工业 RFC（2025–2026）仍在把 `session_id` / `agent_hints` 往 API 里塞。  
从匿名流量恢复身份仍近乎空白，但“空白”本身不足以证明其投入产出比。当前主线接受显式身份，并首先验证 Prefix Family 在 Radix/SessionRadix/RefAware 之上的残余收益。

---

## 三、路径 A：显式改请求面 / 要求配合（主流）

### 3.1 Autellix（2025）——库包装 + session/program/thread ID

- **论文**：[Autellix: An Efficient Serving Engine for LLM Agents as General Programs](https://arxiv.org/html/2502.13965v1)（arXiv:2502.13965）
- **要什么身份**：session / program / thread 作为一等公民，做 program-aware 调度（PLAS 等），减少 HoL。
- **怎么改请求面**：
  - 扩展 OpenAI Chat Completion / vLLM Python API，提供 **stateful 接口**。
  - 用户 `import` Autellix 库；程序启动时自动 `start_session`，拿到 session id；后续 LLM 调用**透明标注** session / program / thread ID；结束时 `end_session`。
- **服务端**：全局 process table 记累计服务时间、等待等；调度与 load balancer 用这些元数据，并考虑 KV 亲和。
- **点评**：典型「用 frontend 换身份」——真实匿名 Chat agent（mini-swe-agent 等）不装这个库就没有 id。明确**不管 KV 淘汰策略细节作为主贡献**时，也仍依赖声明边界。

### 3.2 Continuum（2025）——program id + 输出里解析 tool

- **论文**：[Continuum: Efficient and Robust Multi-Turn LLM Agent Scheduling with KV Cache Time-to-Live](https://arxiv.org/html/2511.02230)（arXiv:2511.02230）
- **要什么身份**：**program id** 串起多轮；按同 id 观察 tool-call 间隔，估 TTL，pin KV；再配合 program-level FCFS。
- **请求面**：
  - 跨轮归属明确依赖 **same program id**（文中反复出现 “within the same program id”）。
  - **tool 名称**从 LLM **输出**的 OpenAI-style function call schema 解析——这一步**不必** agent 多塞字段。
  - 但「属于哪个 program」不是从匿名流量推断出来的。
- **点评**：比 Autellix 更贴近 KV（TTL pin），但身份模型仍是声明式 program；与我们「零先验」不重合。可作为「有 program id 时 TTL 上界」对照。

### 3.3 Parrot（OSDI'24）——扩展 OpenAI API（Semantic Variable）

- **论文 / 代码**：[Parrot PDF](https://www.usenix.org/system/files/osdi24-lin-chaofan.pdf)；[microsoft/ParrotServe](https://github.com/microsoft/ParrotServe)
- **要什么身份**：应用级 DAG / prompt 结构（Semantic Variable），做前缀共享、并行与 DAG-aware 调度。
- **怎么改请求面**：**在 OpenAI-style API 上增加 Semantic Variable 抽象**；应用用其 frontend（`pfunc`）提交，manager 才能看到图。
- **点评**：文档 29 的「Parrot/Teola 靠声明」结论成立；静态/已知 workflow，不覆盖动态匿名多 agent。

### 3.4 SGLang：`agent_hints` + `session_id` tag（引擎 RFC，2025–2026）

| 机制 | 链接 | 请求面改动 | 用途 |
|------|------|-----------|------|
| Agent-Aware KV Phase 1 | [#24656](https://github.com/sgl-project/sglang/issues/24656) | 可选字段 `agent_hints`：`workflow_id` / `agent_id` / `step_id` / `cache_ttl_ms` / `reuse_hint` 等 | 标 radix、实验性 `agent_aware` 淘汰 |
| Session radix cache | [#27058](https://github.com/sgl-project/sglang/pull/27058) | 请求带 `session_id` 给 KV 打 tag；`close` 批量释放 | 按 session 分组释放，KV 仍普通 LRU |
| Programmatic KvHints | [#27574](https://github.com/sgl-project/sglang/issues/27574) | router/orchestrator 下发 Pin/Retain/Share 等 hint | 多引擎策略；与 #24656 互补 |

官方表述：`agent_hints` **optional**，旧 client 不改则行为不变——这是**向后兼容**，不是「不需要配合也能智能」。要 agent-aware 策略，**仍得有人填 hints**（client 或 router）。

### 3.5 vLLM agentic-api：请求加 `session_id`

- **链接**：[vllm-project/agentic-api#18](https://github.com/vllm-project/agentic-api/issues/18)
- **思路**：agentic-api 持有 Responses / session 语义；请求参数增加 `session_id`，写入 `KVCacheBlock`；引擎只管机制，策略在 orchestration 层。
- **点评**：再次确认工业共识——**session 语义由上层声明，引擎不猜。**

### 3.6 NVIDIA Dynamo —— `nvext.agent_hints` / `cache_control`

- **链接**：[Dynamo SGLang agents 文档](https://github.com/ai-dynamo/dynamo/blob/main/docs/backends/sglang/agents.md)
- **做法**：OpenAI 请求经 `extra_body` / `nvext` 传 `priority`、`speculative_prefill`、`cache_control`（pin TTL）等；router 消费后转发 worker。
- **点评**：编排层声明意图，与 Autellix/SGLang hints 同一条谱系。

---

## 四、路径 B：基本不改请求面（但也不做身份识别）

### 4.1 InferCept（2024）——拦截级 preserve / swap / discard

- **论文**：[InferCept](https://doi.org/10.48550/arxiv.2402.01869)（arXiv:2402.01869）
- **是否改 API**：面向「augmentation / interception」语义（tool / 人 / 环境暂停解码）；**不依赖「是哪个 application」的 program_id**。
- **决策**：比较 discard / swap-to-CPU / preserve-in-GPU 的内存浪费，按单次拦截做贪心。
- **局限（Continuum 等后续工作已指出）**：
  - 局部优化下一跳 reload，**忽略多轮排队延迟累积**；
  - **没有 program 连续性**，返回请求可能排到别人后面 → 调度 bubble；
  - 有快速 offload 时 preserve 更少触发，问题更尖锐。
- **对我们**：最接近「零配合」的前辈之一，但是 **RQ 粒度停在 request/intercept**，不是 session/family。最坏情况下我们的方案退化为 InferCept 类仍有增量（P(return) / family 统计），见 doc 29 §八。

### 4.2 默认 Prefix Caching（vLLM / SGLang）

- **身份**：无。只做 content hash / radix 匹配。
- **请求面**：无需改。
- **局限**：无生命周期（死 session 垃圾仍占坑）；无 family 级预算/公平；盲匹配不等于应用感知复用。

---

## 五、路径 C：离线先验 / 已知应用（评测常换设定）

| 工作 / 类工作 | 身份来源 | 遇到「匿名多应用」时 |
|--------------|---------|-------------------|
| **PBKV / KVFlow** | 开发者给的 workflow 图 或 训练好的预测器；评测多为同应用多实例 | 换设定：不测「不知道是哪个应用」 |
| **Tempo 类** | 历史图库匹配 + 应用类型常靠声明/标注 | 在线建图，但类型/身份不靠匿名推断 |
| **Ayo / Alto 等**（Continuum 相关工作提及） | 静态 workflow 假设 | Continuum 明确说不适用于动态 agent |

共同点：**用先验消掉身份不确定性**，而不是在 serving 端从匿名流里恢复。

---

## 六、他们遇到「和我们类似情况」时的实际选择

我们的困难：**端点混部、无 `session_id`、无 `program_id`、无图。**

现有工作的惯用解法：

1. **换问题** — 评测只跑一种 agent（如 SWE-Bench 多实例）→「全是同一类」或「已知是谁」。  
2. **加 frontend** — Autellix 库、Parrot Semantic Variable、Dynamo `nvext`。  
3. **责任上推到 router** — SGLang KvHints、vLLM agentic-api：假定编排层知道 session，把 hint 打进引擎。  
4. **退化到 request 级** — InferCept：不猜 app，也就做不好「同一 program 下一轮立刻回来」。

**几乎没有工作做：仅从匿名 Chat 的 `messages` / `tools` / prefix 做 sessionization + family identification，再反馈到 KV 决策。**

补充：Continuum 证明「从**输出**解析 tool」可零字段成本完成；但**跨轮归属**仍要 program id——说明「看得见 tool」≠「看得见是哪次 session」。

---

## 七、与我们（doc 29）的对照

| 维度 | 现有主流（本调研） | 我们的主张 |
|------|-------------------|-----------|
| 身份来源 | client / 库 / router 声明，或离线图 | **serving 从 S1–S5 推断**（tools / system / 增长 / prefix） |
| 是否改 agent | 通常要，或包一层 | **主路径不要**；显式 id 仅作上界 / 校准（路线 C 混合可选） |
| 管理对象 | program（声明）或 request | request → **session** → **family** |
| 负载 | 常单应用或多实例同应用 | **多应用异构匿名并发** |
| 工业趋势 | 继续加 `session_id` / `agent_hints` | 承认 hints 作可选退化；论文卖点仍是零先验识别 |

**可声称**：没有任何一篇占据「多 agent 异构并发 + 零先验实时感知 + 单/跨 session KV」组合（与 doc 29 §1.4 一致；本调研强化该判断至 2026 引擎 RFC）。

**不可声称**：InferCept「完全零配合搞定 agentic KV」——它零配合是因为**问题被缩小到 intercept**；也不可声称工业界「正在做匿名识别」——RFC 方向仍是声明。

---

## 八、对实现与论文叙述的建议

1. **动机实验**用真实 Chat agent（mini-swe-agent 等）匿名 replay；不要先假设人人装 Autellix。  
2. **上界对照**：同一 trace 人为加上 `session_id` / 走 Responses `previous_response_id` / 或 Autellix 式标注，量化「零配合 vs 显式」gap。  
3. **工程插桩**：优先 tokenize 前抓 `tools`/system（不要求 client 加字段）；不要把实现绑死在 `agent_hints` 上，以免论文变成「又一个声明式 hints」。  
4. **相关工作写法**：按「身份获取方式」三路径（声明 / 无身份 / 离线）组织，比按「调度 vs KV」切分更尖锐。  
5. **与 SGLang #24656 的差异化一句话**：他们假设 hints 已在请求里；我们研究 **hints 不存在时如何从 payload 推断，并可选地写出等价 hint 供策略层消费**。

---

## 九、来源列表

**论文**

- Autellix — https://arxiv.org/html/2502.13965v1 （2025）  
- Continuum — https://arxiv.org/html/2511.02230 （2025）  
- InferCept — https://doi.org/10.48550/arxiv.2402.01869 （2024）  
- Parrot — https://www.usenix.org/system/files/osdi24-lin-chaofan.pdf （OSDI'24）；https://github.com/microsoft/ParrotServe  

**引擎 / 编排 RFC 与文档**

- SGLang Agent-Aware KV — https://github.com/sgl-project/sglang/issues/24656  
- SGLang session radix — https://github.com/sgl-project/sglang/pull/27058  
- SGLang Programmatic KV / KvHints — https://github.com/sgl-project/sglang/issues/27574  
- vLLM agentic-api session RFC — https://github.com/vllm-project/agentic-api/issues/18  
- NVIDIA Dynamo SGLang agents — https://github.com/ai-dynamo/dynamo/blob/main/docs/backends/sglang/agents.md  

**关联文档**

- `docs/29_family_identification_framework_plan.md` — family 识别框架；本报告是其「前人如何拿身份」的专门调查  
- `docs/25_research_directions.md` — 价值标记显式 vs 隐式的早期讨论  
- `docs/26_cache_management_framework.md` — cache 管理全链  
- `docs/31_sglang_27574_programmatic_kv_cache_zh.md` — SGLang #27574 完整中文翻译（本调研「路径 A / router hints」的代表 RFC）

---

## 十、修订记录

| 日期 | 内容 |
|------|------|
| 2026-07-14 | 初稿：三路径分类 + Autellix/Continuum/InferCept/Parrot/SGLang/vLLM/Dynamo 对照及对 doc 29 的含义 |
