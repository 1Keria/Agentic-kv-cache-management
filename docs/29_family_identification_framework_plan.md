# Family 识别 + 信号反馈：多层 KV 管理框架规划

> **历史文档 / 已被替代（2026-07-16）**：本文的“匿名 Sessionization + 行为聚类 Family”不再是当前主线。当前研究采用 client/router 显式提供的 `session_id`，并把 Family 严格定义为同一 KV-compatible namespace 中共享 exact token prefix 的重叠 Session 集。规范定义、F0、离线评测与 SGLang 原型门见 [`docs/33_explicit_session_prefix_family_plan.md`](33_explicit_session_prefix_family_plan.md)。本文保留作为早期问题形成过程与请求面调查的历史材料，以下结论不得再作为当前实施计划引用。
>
> 日期：2026-07-13（2026-07-14 重构为 SGLang 主线）
> 背景：在 `docs/25_research_directions.md`、`docs/26_cache_management_framework.md` 基础上明确论文方向
> 状态：历史路线；已由 doc 33 替代
> 所有源码结论均带 file:line，不含推断
> **分析重心已转向 SGLang**：后续主要在 SGLang 上做；§五以 SGLang 为主线，vLLM 作对照。

---

## 一、问题与定位（一句话）

前人（KVFlow / PBKV / Continuum 等）都假设「已知是哪个应用」并对**单一应用**建模；真实 serving 端点同时收到多种匿名、异构的 agent 应用，**serving 不知道来的是什么**。我们要做的是：在不依赖应用声明、离线训练、静态图的前提下，让 serving **实时感知 agent 状态**，把 KV 管理对象从 request 上升到 session / family，覆盖单 session 与跨 session。

### 1.1 单 agent 建模 vs 多 agent 并发

**前人做的（单 agent 建模）**：
- PBKV / KVFlow：已知是哪个应用，给图 / 训练预测器
- 并发只是「同一应用的多个实例同时跑」（PBKV 测 72 个 SWE-bench 实例）
- 跨实例复用靠应用内结构（都遵循同一 call graph，自然共享前缀）

**我们要做的（多 agent 并发）**：
- serving 端点同时收到 N 种不同 agent 应用，不知道是哪些
- 没有图、没有训练好的预测器、session 不带标注
- 这才是「跨 session」问题真正出现的场景：不同应用的 session 混在一起

### 1.2 「跨 session」的两层含义

1. **KV 生命周期层**：不同 session 的 KV 在 GPU 里竞争，谁该留谁该踢？多 agent 并发时，一个 RAG session 和一个 coding session 的 KV 价值不可比（不同应用、不同模式、不同存活期）。
2. **KV 复用层**：不同 session 可能碰巧共享内容（同一文档、同一 API schema、类似 system prompt），但来自不同应用，现有方法识别不出来。

### 1.3 「实时感知」要做什么（不依赖什么）

serving 从看得见的信号实时推断：
- **单 session 内**：agent 现在什么状态（生成中 / 调工具 / 快结束）？会不会回来、多久回来？KV 该保留、下沉还是淘汰？
- **跨 session**：哪些 session 间可能共享前缀 / 知识？哪些 KV 属于不同 session 但应共同保留？

**不依赖**：应用声明身份（Parrot/Teola 的 workflow 声明、Continuum 的 program_id）；离线 artifact（PBKV 训练、PASTE pattern 挖掘、Tempo 历史图库）；单一应用假设（KVFlow/PBKV 评估设定）。

### 1.4 与 11 篇前人的对比（确认空缺）

| 维度 | 前人覆盖 | 我们要做的 |
|------|---------|-----------|
| 负载假设 | 单应用多实例（PBKV 72 个同应用）或单应用已知（KVFlow） | **多应用异构并发，serving 不知道是哪些** |
| 知识来源 | 声明 / 训练 / 历史 / session 标注 | **只用引擎看得见的信号（内容 / 拓扑 / 时序）** |
| 单 session 决策 | InferCept（三选一，不知 program）、Continuum（pin，靠 name 统计 + id） | **实时推断状态 → 生命周期决策，零先验** |
| 跨 session 复用 | vLLM prefix caching（盲匹配）、Parrot（应用内）、KVCOMM（拓扑硬编码） | **异构应用间智能复用，不靠先验** |

**结论**：没有任何一篇占据「多 agent 异构并发 + 零先验实时感知 + 单/跨 session KV 管理」这个组合。

---

## 二、核心架构：从 request 到 family 的三层

管理对象不能直接从 request 跳到 family，必须经过 session：

```text
request
   │  Layer 0: Sessionization（纵向关联）
   ▼      把连续的 requests 关联成 session
session
   │  Layer 1: Family Identification（横向归类）
   ▼      把行为相似的 sessions 归为 family
family
   │  Layer 2: State Estimation + Policy Feedback
   ▼      个体状态 + family 统计 → 保留 / 存储 / 淘汰 / 调度 / 路由
现有 KV 机制
```

### 2.1 严格区分两个识别问题

- **Sessionization（纵向）**：request B 是否是 request A 所属执行实例的后续轮次？
- **Family identification（横向）**：两个不同 session 是否服从相似的行为模式？

二者不能混为一个聚类问题。若 session 边界不可靠，轮次位置、返回概率、工具等待时间、上下文增长轨迹等 family 特征都会被污染。

### 2.2 研究问题（按依赖关系）

- **RQ0：Sessionization**——serving 如何把独立 requests 关联成持续的 agent session？
- **RQ1：Family definition/identification**——什么样的 session 相似性对 KV 管理有预测价值，如何在线识别？
- **RQ2：State estimation**——如何结合 session 个体证据与 family 聚合规律，实时估计 agent 状态和 KV 未来价值？
- **RQ3：Policy feedback**——如何把带置信度的 session/family 信号反馈给保留、淘汰、调度、路由策略？

### 2.3 三层数据结构

```text
RequestTable[request_id]  -> session_id
SessionTable[session_id]  -> family_id
FamilyTable[family_id]    -> aggregate state / statistics
```

- request 状态：瞬时执行状态
- session 状态：一个 agent 执行实例跨轮次的生命周期
- family 状态：多个相似 session 的聚合规律（个体证据不足时作先验 / 校准，不覆盖个体状态）

---

## 三、Family 的定义

### 3.1 定义

> **Family 是在已建立或概率推断出的 session 边界之上，由一组具有相似、可复用执行规律的 session 构成的在线行为类别。**

「相似」不指 prompt 相似，而指**服务于下游决策**：同 family 的历史信息应能提高对以下变量的估计质量——
- session 是否还会返回 / 预计何时返回
- 下一轮可能复用哪些 KV
- session 当前处于生成、工具等待、恢复还是终止状态
- 哪些共享 cache 节点有跨 session 的未来价值
- 如何做 family-aware 保留、淘汰、调度、路由

### 3.2 判断标准

**如果一种分组不能提升上述决策，哪怕请求语义相似，也不一定是有用的 KV management family。** Family 是面向管理收益的行为等价类，不只是应用名称或文本 embedding 聚类。

### 3.3 与前人概念的区分

| 概念 | 谁提出 | 怎么得到 | 粒度 | 我们的 family |
|------|--------|---------|------|--------------|
| program_id | Continuum/Autellix | client 声明 | 单个执行实例 | ❌ 不依赖声明 |
| application type | Tempo | 离线标注 + 预聚类 | 应用类别 | ✅ 在线无监督 |
| workflow graph | PBKV/KVFlow | 开发者给定 / 训练 | 单个应用 | ✅ 从行为推断 |

### 3.4 与 Autellix 的关键差异

| 维度 | Autellix program | 我们的 family |
|------|-----------------|--------------|
| 边界来源 | client 注册 session | **serving 自动识别** |
| 粒度 | 单次执行（一个用户的一个任务） | **多个 session 的集合** |
| 跨用户 | 否（每个 program 独立） | **是（不同用户的同类 agent 归为一个 family）** |
| 用途 | 调度优先级（PLAS） | **调度 + KV 生命周期 + 跨 session 复用** |

---

## 四、Session 身份的来源（RQ0）

### 4.1 现有工作如何获得 session 身份

| 系统/接口 | Serving 看到的基本对象 | Session 边界来源 |
|-----------|----------------------|------------------|
| vLLM/SGLang 通用 API | 独立 request | 默认无稳定跨 request 身份 |
| Autellix | program/session 内的调用 | client 注册 / 显式传递 |
| Continuum | 带 program 信息的请求 | client 提供 `program_id` |
| Parrot/Teola | 框架管理的语义变量/workflow | 应用用其前端/API 声明结构 |
| PBKV/KVFlow | 已知应用/workflow 的执行实例 | 预先给定图/应用身份/模型 |

既有 session/program 级工作都靠 client / 框架 / 离线 artifact 获得边界，**没有从匿名 request 流恢复身份**。

### 4.2 三条可选路线

- **路线 A（显式 metadata）**：client 在 metadata 中带稳定 `session_id`，serving 直接用。边界准确、易比较，但依赖配合，不能声称零先验。
- **路线 B（serving-side 推断）**：从 request 流在线推断关联，候选证据见 §五。零配合，但边界有误差。
- **路线 C（混合，建议）**：有可信 id 用之，无 id 启动推断，维护置信度；低置信度 session 不向 family 写强证据、采保守策略；显式 id 作 ground truth / 校准 / 退化路径。

### 4.3 推断的证据（路线 B）

1. 上下文包含关系：新 request token 序列是否包含历史 request 的输入及输出
2. KV 前缀沿袭：新 request 命中的 cache path 是否延续候选 session 的历史路径
3. 输出—输入衔接：前一 request 的生成结果是否出现在新 request 输入中
4. 时间邻近性：两轮间隔是否符合候选 session/family 的等待分布
5. 工具调用衔接：前一轮生成的 tool call 与后一轮注入的 tool result 是否对应
6. 连接 / 租户信息：弱证据，不能单独作身份

**重要边界**：共享 system prompt 只说明 family 相似，不能证明 session 相同；高 prefix 命中也不充分（同模板下多个并发 session 可共享很长前缀）。sessionization 应基于多证据联合置信度，无法可靠归属时创建新 session，避免错误合并污染统计。

### 4.4 不能过早下的结论

1. vLLM prefix cache 足以恢复 session —— 未证实
2. 同 family session 必然共享高度相似 token prefix —— 未证实
3. sessionization 只是工程配件而非研究贡献 —— 待定
4. 纯 serving-side 推断一定达足够精度 —— 待定
5. 采用显式 metadata 后仍可声称「零 client 配合」—— 不可

---

## 五、请求格式暴露的信息：serving 到底看得到什么（源码核实，SGLang 主线 + vLLM 对照）

> 后续主要在 SGLang 上做，本节以 SGLang 为主线核实，vLLM 压缩为对照节（§5.12）。
> 全部基于 `Engine/sglang/` 与 `Engine/vllm/` 当前源码，带 file:line，不含推断。
> **关键区分：API server 层看到的字段 ≠ 引擎层看到的字段**——请求在两层之间被「瘦身」一次。

### 5.1 SGLang 三类入口 schema 对照（与身份/session/cache 相关的字段）

**先厘清「三类入口」是什么**：Chat / Completion / Responses 不是三种数据，而是同一个模型对外暴露的**三条不同 HTTP 请求入口（schema）**，各对应一套 OpenAI API 标准，SGLang 都实现了。同一个请求走不同的门，serving 能看到的结构信息多寡不同——这直接决定 family/session 识别能拿到多少「免费信号」。

| 入口 | HTTP 端点 | 定义 | 输入形态 | 对识别的意义 |
|------|-----------|------|---------|-------------|
| **Chat** | `/v1/chat/completions` | `ChatCompletionRequest`（`protocol.py:637`） | 结构化 `messages` 数组（含 role/tool_calls）+ `tools` | **结构信号最全**（tools=S1、system prompt=S2、role 序列=S3 全可见）→ 识别主战场；mini-swe-agent 等主流 agent 用这个 |
| **Completion** | `/v1/completions` | `CompletionRequest`（`protocol.py:302`） | 一整段拼好的纯文本/token `prompt`（`protocol.py:309`） | **最贫瘠**：无 `messages`、无 `tools`，历史被 client 拼成一坨字符串，连最强应用指纹（工具 schema）都看不到 |
| **Responses** | `/v1/responses` | `ResponsesRequest`（`protocol.py:1304`） | `input`+`instructions`，靠 `previous_response_id` 串历史 | **有原生会话指针**（`previous_response_id`=S9，识别会话身份最容易），但结构信号需从 `input`/`instructions` 重建；需 client 用新 API + `store=true` |

- **Chat（聊天补全，主流）**：请求体是对话消息数组，system/user/assistant/tool 各轮以 role 标注，并携带 `tools` 工具 schema。结构化信息最完整，是 family 识别信号最强的入口。
- **Completion（文本补全，老式）**：只有一个 `prompt` 字段，所有历史/system/工具都被 client 自己拼成一段文本，serving 无法区分其中结构。对 family 识别的结构信号最弱。
- **Responses（响应，新式有状态）**：server 端记住对话，client 只发增量 `input` + `previous_response_id` 指向上一轮。会话连续性靠 `previous_response_id`（`protocol.py:1328`）这个 server-side 会话指针，而**非** `session_params`；是最强的「同一 session」显式证据，但当前多数 agent 尚未采用。

下表逐字段对照三类入口中与身份/session/cache 相关字段的可见性（`✅ 行号` = 该 schema 声明了此字段）：

| 字段 | Chat (`protocol.py:637`) | Completion (`protocol.py:302`) | Responses (`protocol.py:1304`) |
|------|:-:|:-:|:-:|
| `messages`（含 role/tool_calls/reasoning） | ✅ `640` | ❌（只有 `prompt` `309`） | ✅（重建自 `input`/`instructions`） |
| `tools` / `tool_choice` | ✅ `669/670` | ❌ | ✅ `1335`（仅 builtin 类型） |
| `session_params` | ✅ 声明 `715`（**chat 适配层不转发，见 §5.2**） | ✅ 声明 `345`（同样不转发） | ❌ |
| `rid`（client 可设稳定请求 id） | ✅ `735` | ✅ `363` | ✅（`request_id` `1342`，默认 `resp_<uuid>`） |
| `extra_key` | ✅ `737` | ✅ `365` | ✅ `1347` |
| `cache_salt` | ✅ `739` | ✅ `367` | ✅ `1351` |
| `priority` | ✅ `741` | ✅ `369` | ✅ `1346` |
| `routing_key` | ❌（从 HTTP 头取，见 §5.3） | ❌（同） | ❌ |
| `previous_response_id` / `store` / `metadata` | ❌ | ❌ | ✅ `1328/1331/1325` |
| `return_cached_tokens_details` | ✅ `677` | ✅ `329` | ❌ |
| `return_meta_info` | ✅ `679` | ❌ | ❌ |
| `reasoning_effort` / `custom_params` / `chat_template_kwargs` | ✅ `680/727/718` | ✅ `custom_params` `347` | ✅ `reasoning` `1329` |
| `bootstrap_host/port/room`（P/D） | ✅ `744` | ✅ `351` | ❌ |

> 关键不对称：**Completion 没有 `messages`/`tools` 结构**——纯 prompt token，连最强应用指纹（工具 schema）都看不到；**Responses 的会话连续性靠 `previous_response_id` 而非 `session_params`**。后两类对 family 识别的结构信号弱于 Chat。

### 5.2 字段命运：从 HTTP 到 scheduler `Req` 的逐层穿透

**本节要回答一件事**：§5.1 的字段进入 HTTP 后，一路往引擎深处走，**哪些还在、哪些丢掉、在哪一层死的**。先把「链路上每个节点干什么」和「表里每个字段本意是什么」讲清，再看穿透结果表。

#### 5.2.1 链路节点各自干什么（按请求流向）

```text
[Node ①] ChatCompletionRequest          HTTP / OpenAI API 层收到的原始请求体
            │ serving_chat.py 适配         （把 OpenAI schema 翻译成 SGLang 内部格式）
            ▼
[Node ②] GenerateReqInput               SGLang 内部「尚未 tokenize」的生成请求
            │ tokenizer_manager tokenize   （切词：结构化 messages → 纯 token 序列）
            ▼
[Node ③] TokenizedGenerateReqInput      已切词、准备送进调度器的请求
            │ IPC（进程间通信）             （tokenizer 进程 → scheduler 进程）
            ▼
[Node ④] scheduler.handle_generate_request  调度入口：把请求挂进等待/运行队列
            │
            ▼
[Node ⑤] Req                             引擎内部「权威请求对象」：调度/KV/命中统计都挂在这上面
            │
            ▼
[Node ⑥] RadixKey                        查/写 prefix KV cache 时用的键（决定能不能和其他请求共享）
```

| 节点 | 代码位置 | 一层的作用（读这一行就够） |
|------|---------|--------------------------|
| ① `ChatCompletionRequest` | `protocol.py:637` | **对外契约**：client 按 OpenAI Chat 格式发来的 JSON；结构最完整（有 `messages`/`tools`） |
| ② `GenerateReqInput` | `io_struct.py:138` | **内部协议（未切词）**：API 适配层产出的 SGLang 原生请求对象；仍可能带文本/`session_params`，但 Chat 适配可能已丢字段 |
| ③ `TokenizedGenerateReqInput` | `io_struct.py:736` | **已切词请求**：prompt 变成 `input_ids`；从此以后引擎只认 token，不再认 role/`tools` 结构 |
| ④ `scheduler.handle_generate_request` | `scheduler.py:1921` | **调度入口**：接收 tokenizer 进程传来的请求，决定入队/亲和/挂 Session |
| ⑤ `Req` | `schedule_batch.py:643` | **运行时权威对象**：prefix 命中、KV 占用、retraction、finished_reason、time_stats 等都挂在它上面（§5.5） |
| ⑥ `RadixKey` | `radix_cache.py:56-72` | **cache 查找键** = `(token_ids, extra_key)`；两个请求能共享 prefix KV，当且仅当两边 `RadixKey` 能匹配 |

> 记忆点：① 最「胖」（结构全）；⑤ 最「瘦但权威」（只剩 token + 少量控制字段）；⑥ 决定「能不能跟别人共用 cache」。

#### 5.2.2 表里每个字段本意是什么（按角色分组）

**A. 内容 / 结构指纹（识别 family 最有用，但最先死）**

| 字段 | 本意 | 对我们的用途 |
|------|------|-------------|
| `messages` | 对话数组（system/user/assistant/tool 各 role） | S2 system、S3 增长模式与 role 序列 |
| `tools` | 工具 schema（function name/参数定义） | **S1 最强应用指纹** |
| system prompt | 通常是 `messages[0]`（role=system） | S2 稳定应用指纹 |

三者在 Chat 路径经 `_process_messages` → chat template → encode 后，**全部折叠成一串 `origin_input_ids`**。Node ③ 起再也看不到「哪段是 tools、哪段是 system」。

**B. 身份 / 会话类（名字容易误导，语义必须拆开）**

| 字段 | 本意 | 不是什么 | Chat 路径命运 |
|------|------|---------|--------------|
| `rid` | **单次请求 id**（client 可设；默认每请求新 uuid） | ❌ 不是 session id | 全链保留，但默认每请求变 → 不能当会话身份 |
| `session_params` | 原生 Session 参数（含 `id`）；让 server 维护跨轮请求树 | ❌ 不是 OpenAI 标准字段 | schema **声明了**，但适配层**没传** → Chat 实际无效 |
| `conversation_id` | 注释写「used for tracking」的跟踪字段（`io_struct.py:239`） | ❌ 不是引擎身份 | 原生层有字段，但**未透传到 scheduler** → 不可靠 |
| `routing_key` | HTTP 头 `x-smg-routing-key`：**调度亲和**（同 key 尽量进同 batch） | ❌ **不是** cache 身份、不隔离 KV | 进到 `Req`，但**不进** `RadixKey` |
| `extra_key` | **cache 命名空间隔离键**（不同值 → 阻止共享 radix 节点） | ❌ 不是相似度；乱设会破坏跨会话共享 | **唯一进 `RadixKey` 的身份字段** |
| `cache_salt` | 另一路隔离输入；适配层与 `extra_key` **无分隔拼接**（见 §5.3） | ❌ 单独看没有独立 cache 语义 | 合并进 `extra_key` 后一起进 `RadixKey` |

**C. 调度 / 观测类（非身份）**

| 字段 | 本意 |
|------|------|
| `priority` | 调度优先级；全链可见，不进 `RadixKey` |
| `custom_labels` | HTTP 头白名单标签；只用于 tokenizer 侧指标，**不进 scheduler** |

#### 5.2.3 穿透结果表：谁活到哪一关

表头列 = §5.2.1 的节点；单元格 = 该字段是否仍以**可识别的语义形态**存在（不是「字符串是否碰巧还在某处」）。

| 字段 | ① Chat schema | ② `GenerateReqInput` | ③ `TokenizedGenerateReqInput` | ⑤ `Req` | ⑥ `RadixKey` | 命运一句话 |
|------|:-:|:-:|:-:|:-:|:-:|------|
| `messages`/`tools`/system | ✅ | ❌ 已折叠成 text/ids | ❌ | ❌（只剩 `origin_input_ids`） | ❌（只进 token_ids） | **结构在 ①→②/tokenize 死掉** |
| `rid` | ✅ `735` | ✅ `543` | ✅ `1116` | ✅ `1942`（`self.rid` `690`） | ❌ | 全链在，默认每请求变 → **非会话身份** |
| `extra_key`（含拼接后的 `cache_salt`） | ✅ | ✅ `544`（`_compute_extra_key`） | ✅ `1134` | ✅ `1975`（`self.extra_key` `756`） | ✅ `RadixKey(..., extra_key)` `radix_cache.py:56` | **唯一进 cache 键的身份字段** |
| `routing_key` | 头 `x-smg-routing-key` | ✅ `547` | ✅ `1135` | ✅ `1974`（`self.routing_key` `758`） | ❌ | 调度亲和在，**不隔离 cache** |
| `session_params` | ✅ 声明 `715` | ❌ **适配层未传**（`522-555` 无该 kwarg） | 仅原生 `/generate` 才传 `1124` | 仅原生路径进 `Session`（`scheduler.py:2001-2012`） | — | **Chat 路径实际无效** |
| `conversation_id` | — | ✅ `239`（tracking） | ❌ 未透传 | ❌ | ❌ | 名义上有，**到不了 scheduler** |
| `priority` | ✅ `741` | ✅ `546` | ✅ `1133` | ✅ `1968`（`793`） | ❌ | 调度用，非身份 |
| `custom_labels` | 头（allowlist） | ✅ `548` | ❌ | ❌ | ❌ | 仅 tokenizer 指标 |
| `cache_salt` | ✅ `739` | 并入 `extra_key` | 同 | 同 | 同（经 `extra_key`） | 无独立形态，见 §5.3 |

#### 5.2.4 两条最关键的穿透结论

1. **`session_params` 在 Chat 路径被丢掉**：`ChatCompletionRequest` 声明了 `session_params`（`protocol.py:715`），但 `OpenAIServingChat._convert_to_internal_request` 构造 `GenerateReqInput` 时（`serving_chat.py:522-555`）**没有传 `session_params=`**。原生 session 机制只在 `/generate`（`engine.py:353` → `GenerateReqInput.session_params` `io_struct.py:202`）才生效。**所以「SGLang chat 流量自带 session」是错觉**——这反而强化了 RQ0：连声明了都不一定进。
2. **结构指纹只在 tokenize 之前可见**：`tools`/`system prompt`/`messages` 的 role 序列在 `serving_chat._process_messages` → chat template → encode 后折叠成 `origin_input_ids`（`Req.origin_input_ids` `schedule_batch.py:691`）。到 `Req`（节点⑤）只剩 token 序列 + `extra_key` + `routing_key` + `rid`。要用 S1/S2/S4（工具/system/模板）必须在节点①→②之间（`serving_chat.py`）拦截。

### 5.3 三个「声明式身份」字段的语义边界（必须区分，不可混用）

这是最容易踩坑的地方，单独列出：

| 字段 | 来源 | 进 RadixKey？ | 真实语义 | 当 family/cache 身份用？ |
|------|------|:-:|------|------|
| `session_params.id` | client 显式（原生 `/generate`） | 否（走独立 Session 树） | **会话续接身份**：server 维护请求树，跨轮复用前缀 | ✅ 最强会话身份，但需原生 session API + chat 路径不转发 |
| `previous_response_id` | Responses API | 否 | **应用层状态续接**：从进程内 `response_store`/`msg_store`（`serving_responses.py:114/120`）取上一轮重建输入 | ✅ 强逻辑会话证据，但**进程本地**、**非 KV 指针**、重启即失 |
| `routing_key`（`x-smg-routing-key` 头） | client/代理 | **否** | **调度亲和**：`ROUTING_KEY` 策略把同 key 请求靠拢同 running batch（`schedule_policy.py:365-395`） | ⚠️ **不是 cache 身份**，不隔离 KV；可作 family 路由提示 |
| `extra_key` / `cache_salt` | client 显式 | **是**（`RadixKey` `radix_cache.py:56`） | **cache 命名空间隔离**：不同值 → **阻止**共享 radix 节点 | ⚠️ 是隔离键，**不是相似度**；乱设会破坏跨会话共享 |

**陷阱**：
- `_compute_extra_key`（`serving_base.py:151-162`）把 `cache_salt` 与 `extra_key` **无分隔拼接**：`cache_salt="ab",extra_key="c"` 与 `cache_salt="a",extra_key="bc"` 产生同一 key。若二者代表不同隔离域会冲突。
- 把 `routing_key` 当 cache 隔离键 → 语义错误（它不进 `RadixKey`）。
- 给每个 session/agent 设不同 `cache_salt` → 反而**阻断**本可共享的公共 system 前缀。
- `lora_id` 会被拼到 `extra_key` 末尾（`schedule_batch.py:751-754`），隐式隔离 LoRA cache。

**对我们的启示**：family 识别**不应**依赖 `extra_key`/`cache_salt`（那是客户端控制的隔离，不是行为相似度）；`routing_key` 可复用为 family 路由提示但非身份；真正零配合的身份证据仍是 §5.11 的 S1–S5（tools/system/增长/prefix）。

### 5.4 SGLang 原生 session 的两种形态（都是显式声明式）

**非流式 `Session`**（`session_controller.py:81-256`）：
- 字段：`session_id`、`req_nodes`（请求树，可多分支）、`timeout`、`close_on_finish`、`_inflight`（`81-96`）。
- `create_req`（`103-256`）：从上一 `last_req` 重建输入 `origin_input_ids + output_ids`（`188-199`），支持 `replace`/`offset`/`drop_previous_output` 编辑历史。
- 显式声明式：`session_id` 来自 `SessionParams.id`（`io_struct.py:113`），client 必须主动传。

**流式 `StreamingSession`**（`streaming_session.py`）：
- `SessionSlot` **跨轮持有 KV**：`try_match_prefix`（`237-276`）把 slot 恢复进新请求，`try_cache_finished_req`（`278`+）成功时存 slot、**中途 abort 时清掉全部 session KV**（只保留上一成功轮）。
- **append-only、串行**：`_inflight` 阻止同 session 并发（`session_controller.py:120-133,247-269`），拒绝 `replace`/`drop_previous_output`/非零 `offset`。
- 不是「零 prefill」，是「免历史 prefill」：每轮仍需 prefill 新增 token（tool result 等）。

**两者都靠 client 显式 `session_params.id`**——价值在 server-side 维护请求树/持有 KV，**不在身份识别**。对零配合场景仍是空白。`SessionController` 在 scheduler **默认实例化**（`scheduler.py:924`），HTTP 端点 `/open_session`、`/close_session`（`srt/entrypoints/http_server.py:1404`）。

### 5.5 引擎层真正可观测的 KV/状态信号（无需改 API 即可拿，全在 `Req` 上）

这些是 state estimation 的**现成 ground truth**，不是估计：

| 信号 | 位置 | 含义 | 对我们的用途 |
|------|------|------|------|
| `num_matched_prefix_tokens` | `schedule_policy.py:123`（调度时填） | 真实匹配前缀长度（device+host，封顶） | session 链接物质基础；family 复用价值校准 |
| `prefix_indices` | `schedule_batch.py:813` | device 命中的 KV 索引 | prefix 沿袭证据（§4.3 证据2） |
| `host_hit_length` / `storage_hit_length` | `schedule_batch.py:823/832` | CPU/L3 命中长度 | 分层复用价值 |
| `cached_tokens_device/host/storage` | `schedule_batch.py:920-922`（首 chunk 算 `2034-2059`） | 实际复用 token 数（按层） | family 复用收益的 realized 值 |
| `extend_input_len` | `schedule_batch.py:815` | 本轮仍需 prefill 的 token 数 | 增长轨迹（§4.3 证据1 的量化） |
| `kv_committed_len` / `kv_allocated_len` | `schedule_batch.py:711-712` | 已提交/已分配 KV 长度 | 请求级 KV 占用与浪费 |
| `retraction_count` / `retracted_stain` | `schedule_batch.py:846-848,939` | 被抢占次数/曾被抢占 | KV 压力、admission 误判信号 |
| `finished_reason` | `schedule_batch.py:781` | stop/length/abort… | 状态终止判定（P(terminated)） |
| `time_stats`（queue_time/TTFT/e2e/prefill_finished） | `req_time_stats.py:524-565` | 全阶段时间戳 | 时间邻近性（§4.3 证据4）、工具等待 |
| `session` | `schedule_batch.py:705` | 所属原生 Session（若有） | 显式身份上界 |

### 5.6 已有的 Prometheus 聚合指标（可作 family 级统计的现成基底，但无 per-family 分解）

全部在 `metrics_collector.py` 声明、`metrics_reporter.py` 填充：

- 容量/池：`kv_available_tokens`、`kv_evictable_tokens`、`kv_used_tokens`、`token_usage`、`cache_hit_rate`（`metrics_collector.py:341-358,291`）。
- 队列/运行：`num_running_reqs`、`num_queue_reqs`、`num_grammar_queue_reqs`（`267-284`）。
- 抢占：`num_retracted_reqs`、`num_retracted_requests_total`、`num_retracted_input/output_tokens_total`（`443-463`）。
- 流式 session（仅启用时）：`num_streaming_sessions`、`streaming_session_held_tokens`（`635-646`）。
- routing key（**仅当本批所有请求都带 routing_key 才算**，`metrics_reporter.py:833`）：`num_unique_running_routing_keys`、`routing_key_running/all_req_count`（`651-668`）。
- 请求级（tokenizer 侧）：`cached_tokens_total{cache_source=device|host|storage_*}`（`1507-1511`）、`prompt_tokens_histogram`、`uncached_prompt_tokens_histogram`、`e2e_request_latency_seconds`、`time_to_first_token_seconds`（`1613-1685`）。

**关键缺口**：以上全是**全局聚合**，没有 per-session / per-family 分解。这恰好是我们的位置——把 `extra_key`/识别出的 family_id 作为新 label 注入这些指标，就能得到 family 级统计而无需新机制。但要小心 cardinality（routing key 指标已有「全带才算」的保护，正是为控 cardinality）。

### 5.7 可返回给 client 的请求级证据（评测/校准用）

- `return_cached_tokens_details=true`（`protocol.py:677`）→ 响应带 `cached_tokens_details={device,host,storage,storage_backend}`（`output_streamer.py:60-91`，经 `tokenizer_manager.py:1875-1881` 回传）。
- `return_meta_info=true`（`protocol.py:679`）→ `meta_info` 含 `cached_tokens`、`num_running_reqs`/`num_waiting_reqs`、`queue_time`、TTFT、e2e、`retraction_count`、`dp_rank`（`tokenizer_manager.py:1840-1908`）。
- 这些是**单请求 realized 值**，适合做 family 预测 vs 真实命中的离线校准、reward 构造（`device_hit > host_hit > storage_hit > recompute`）。
- 注意：流式 + `return_meta_info` 的支持受限（当前流式走 `sglext` final chunk，见 §5.8 插桩点 7），动机实验优先用非流式 + `return_meta_info` 采全量证据。

### 5.8 最佳插桩点（最小侵入 observer，带 file:line）

| # | 位置 | 抓什么 | 用途 |
|---|------|------|------|
| 1 | `serving_chat.py:522-555`（OpenAI 适配后） | `tools`/system prompt/`messages` role 序列/`session_params`（适配层丢的那个） | **结构指纹 S1/S2/S4**，必须在 tokenize 前拦 |
| 2 | `tokenizer_manager.py:1106-1142`（tokenize 后） | `rid`、prompt 长度、`session_params`、`routing_key`、effective `extra_key` | 身份归一化、建 `rid→family_id` 映射 |
| 3 | `scheduler.py:1921-1980`（scheduler 入口） | 权威 `Req`：`extra_key`/`routing_key`/`priority`/`session` | 个体状态主表 |
| 4 | `schedule_policy.py:90-130`（prefix match 后） | `num_matched_prefix_tokens`、device/host/storage 命中分解 | **state estimation 主决策点** |
| 5 | `schedule_batch.py:2034-2059`（首 chunk 缓存核算） | realized `cached_tokens_device/host/storage` | 复用收益真实值 |
| 6 | `unified_radix_cache.py` store/evict 钩子（`1016/1033/1402-1456/1577/1663`） | GPU/CPU store、evict 事件 | KV 生命周期（§六 存储决策） |
| 7 | `output_streamer.py` + `tokenizer_manager` meta_info（`1840-1908`） | 最终分层命中、TTFT/e2e、retraction、输出长度 | 离线校准、reward、策略评估 |

**接入策略**：不改 `messages`/`tools`/token_ids（会动 prompt、破坏 prefix hit），只加旁路控制面字段（类比现有 `routing_key`/`extra_key` 的穿透方式）。admission/eviction 先在队列排序与淘汰优先级上实验，不动 radix 正确性逻辑。

### 5.9 Responses API 核实：原生 stateful 会话字段

SGLang 与 vLLM 都实现 OpenAI Responses API：
- SGLang Responses（`protocol.py:1304`）：`previous_response_id`（`1328`）、`store`（`1331`）、`metadata`（`1325`）、`extra_key`（`1347`）。进程内 `response_store`/`msg_store`（`serving_responses.py:114/120`），`store=request.store` 时存（`305-306`），`_construct_input_messages`（`589-628`）从 `msg_store` 重建对话。
- vLLM `ResponsesRequest`（`responses/protocol.py:136`）：`previous_response_id`（`161`）、`store`（默认 True，`165`）、`metadata`（`157`）。server-side response store（`responses/serving.py:232`），新请求带 `previous_response_id` 时从 store 取上一轮拼接输入（`serving.py:363-366`）。

**`previous_response_id` 是最强的「同一 session」显式证据**——本质是 server-side 会话指针。但前提是 client 用 Responses API 且 `store=True`。当前主流 agent（含 mini-swe-agent）仍用 Chat API，不带此字段。

| 维度 | Chat API | Responses API |
|------|---------|--------------|
| 会话连续性 | client 每轮重发全历史 | server 存 response，client 发 `previous_response_id` + 增量 |
| session 边界 | 无原生字段 | **有原生字段，链式可还原** |
| server 状态 | 无状态 | stateful（`response_store`） |
| client 配合度 | 无需改 API | 需用 Responses API |

### 5.10 多轮 benchmark：会话标注是「自己造的」

vLLM multi-turn benchmark（`benchmarks/multi_turn/benchmark_serving_multi_turn.py`）自己往请求塞 `conversation_id`（`payload["conversation_id"]`，行 254-255）和 `X-Session-ID` 头（行 268-269），靠 `send_conversation_id` 开关控制。`grep vllm/`（排除 benchmark/test）**无任何命中**——serving 侧完全不消费，纯靠 `extra="allow"` 静默收下。**反向印证「真实 serving 没有标准会话字段」——连官方 benchmark 都只能自己造自定义字段、自己读。** 但这给我们提供了**带 ground-truth 标注的 trace 来源**（SGLang 侧可经 `extra="allow"` 同样自造，见 §5.11 S8）。

### 5.11 身份识别可用信号（按强度分级，两引擎通用）

| 等级 | 信号 | 可见层 | 稳定性 | 判身份 |
|------|------|--------|--------|--------|
| **S1 强** | `tools`（工具 schema 集合） | API server | 同应用不变、跨应用差异大 | ✅ family 主指纹 |
| **S2 强** | system prompt（`messages[0]`） | API server（tokenize 后变 token） | 同应用稳定 | ✅ family 指纹 |
| **S3 强** | `messages` 增长模式 + role 序列 | API server | 单 session 内单调增长 | ✅ sessionization 核心证据 |
| **S4 中** | `documents`/`chat_template`/`reasoning_effort` | API server | 揭示应用类型 | ✅ family 辅助 |
| **S5 中** | prompt token 序列的 prefix 包含关系 | 引擎层（radix tree） | session 链接物质基础 | ✅ 但**非充分**（共享 prompt ≠ 同 session） |
| **S6 弱** | `cache_salt` / `extra_key` | 引擎层 | 可复用为弱标识 | ⚠️ 是隔离键非相似度（见 §5.3），需 client 设置 |
| **S7 弱** | `routing_key`（SGLang）/ `trace_headers` traceparent（vLLM） | 引擎层 | SGLang 调度亲和非身份；vLLM 同任务内常同 trace-id | ⚠️ 需 client 配合 |
| **S8 弱** | 自造 `conversation_id`/`session_id`（经 `extra="allow"`） | API server | 任意 metadata，benchmark 自造 ground truth | ⚠️ 需配合 + 改造读取，但可作评测标注 |
| **S9 强但需原生 API** | `session_params.id`（SGLang）/ `previous_response_id`（Responses） | 引擎层/服务层 | 显式会话指针 | ✅ ground truth 上界，但需该 API |
| **S10 不可用** | `user` 字段（vLLM 明确忽略）/ `rid`（默认随机每请求变） | — | 无跨轮连续性 | ❌ |

### 5.12 vLLM 对照（压缩版，细节见上方各节对应说明）

SGLang 是比 vLLM 更好的实验平台（更多身份字段全链可见、分层 prefix 命中可观测、Prometheus 基底齐全、请求级证据可回采），但 vLLM 同样是真实生产 serving，作为对照仍有意义：

- **vLLM ChatCompletion schema**（`vllm/entrypoints/openai/chat_completion/protocol.py:186`）：`messages`(`189`)、`tools`(`210`)、`tool_choice`(`211-217`)、`documents`(`296`)、`chat_template`/`chat_template_kwargs`(`308/316`)；采样参数 `208-243`；身份/调度类 `request_id`(`353` 默认随机 uuid)、`user`(`236` 注释明确「will be ignored」)、`priority`(`330`)、`cache_salt`(`373`)、`vllm_xargs`(`392` 塞自定义 metadata 的官方口子)、`kv_transfer_params`(`385`)。
- **`extra="allow"`**（`engine/protocol.py:30`）：`OpenAIBaseModel` 对未声明字段**只打 debug 日志、不拒绝**。agent 可塞任意自定义字段（session_id/conversation_id/trace_id/agent_type），vLLM 照单全收，但**除非有代码主动读取，否则在 API server 层就被丢弃，不进引擎层**。SGLang schema 同样 Pydantic `extra="allow"`，行为一致。
- **vLLM 引擎层身份被剥离**：引擎内部 `Request`（`vllm/v1/request.py:59`，构造参数 `61-79`）只有 `request_id/prompt_token_ids/sampling_params/.../cache_salt/priority/trace_headers/block_hasher/...`，**没有 `user_id`/`session_id`/`conversation_id`/`agent_type`**。`user` 被声明忽略；`messages` 结构化信息在 tokenize 后折叠成 `prompt_token_ids`（`request.py:63,121`）。引擎层可用只剩：prompt_token_ids、request_id（随机）、cache_salt、arrival_time、trace_headers、lora_request/priority（弱）。SGLang 同理，§5.2 已述 `tools`/system prompt 在 `serving_chat` tokenize 后折叠成 `origin_input_ids`。
- **vLLM trace_headers：唯一从 HTTP 头透传到引擎的通道**（`vllm/tracing/utils.py:12` `TRACE_HEADERS=["traceparent","tracestate"]`，`extract_trace_headers`(`62-67`)，`chat_completion/serving.py:312-315` 仅 `is_tracing_enabled()` 才提取 → `Request.trace_headers`(`74,161`)）。默认 None；只有开 tracing 且 client 发 W3C traceparent 才有值，可作「同一逻辑任务」弱证据。SGLang 对应物是 `routing_key`，但二者语义不同（见 §5.3）。
- **vLLM X-Request-Id 中间件只回写响应头，不进引擎**（`server_utils.py:95` `XRequestIdMiddleware`，需 `--enable-request-id-headers`，`api_server.py:263`）。即使 client 每轮带同一 id，引擎层也看不到。
- **vLLM 无原生 session 机制**（不像 SGLang 有 `SessionController`/`StreamingSession`）——vLLM 端的「会话」完全靠 prefix cache 盲匹配或 client 自造 `conversation_id`。这进一步印证 §5.4 结论：连 SGLang 的原生 session 都是显式声明式、chat 路径还不转发，vLLM 更无。
- **真实 agent payload 实测：mini-swe-agent**（`Agent/mini-swe-agent/src/minisweagent/models/openrouter_model.py:67-75`）payload = `{"model":..., "messages":messages, "tools":[BASH_TOOL], "usage":{"include":True}, **kwargs}`。**无 session_id、无 user id、无 conversation 标识。** 纯 OpenAI ChatCompletion。会话连续性完全靠 `messages` 携带历史——这正是 agent 本质：每轮重发全历史。`BASH_TOOL` 随每个请求重复发送，构成稳定应用指纹（S1）。SGLang chat 路径行为一致（同样靠 messages 重发、tools 重发）。

### 5.13 三个数据源的定位（实验设计）

| 数据源 | session 边界 | 用途 |
|--------|------------|------|
| Chat API 真实 trace（如 mini-swe-agent 回放，SGLang 为主、vLLM 对照） | **无标注**，需 serving-side 推断 | 动机实验主战场：证明推断可行且必要 |
| 多轮 benchmark replay（vLLM `conversation_id` / SGLang 自造） | 有 `conversation_id` ground truth | 评测推断精度（precision/recall） |
| Responses API replay（带 `previous_response_id`） | 有原生 server-side 链 | 「显式 id 上界」对照，量化零配合推断的 gap |

### 5.14 对 RQ0/RQ1 的最终影响

1. **零 client 配合可行**：S1–S5 全是 agent 无法不暴露的信号（工具 schema、system prompt、历史增长、prefix 结构），不需主动声明。
2. **最佳观测点在 API server 层（tokenize 之前）**：S1/S2/S4 的结构化信息进引擎后被压平成 token，要用它们必须在 tokenize 之前拦截提取（SGLang `serving_chat.py:522-555` / `tokenizer_manager.py`、vLLM `chat_completion/serving.py`）——这是必须的工程改造点。只用 S3/S5 可在引擎层从 token/radix 推断，但损失结构信息。
3. **两个引擎都无「自动 session」**：vLLM 无原生机制、SGLang 显式声明且 chat 路径连声明的都不转发、Responses 原生但需该 API——**真实匿名 Chat API 流量下 serving-side sessionization 是空白且必要的，这是 RQ0 的立足点。** 在 SGLang 上更扎实（chat 适配层丢 `session_params` 已源码坐实）。
4. **现成 ground truth 来源**：benchmark `conversation_id`、SGLang `session_params.id`（原生 `/generate`）、Responses `previous_response_id`——评测手段不缺。
5. **论文动机实验应优先 Chat API 匿名 replay**（SGLang 主、vLLM 对照）；Responses API replay 作显式 id 上界对照。
6. **SGLang 是比 vLLM 更好的实验平台**：`rid`/`extra_key`/`routing_key`/`session_params` 全链可见、prefix 命中分层可观测、Prometheus 基底齐全、请求级 `return_meta_info`/`return_cached_tokens_details` 可回采。后续主要在 SGLang 上做。
7. **不要把 `routing_key`/`extra_key` 当 family 相似度**：`routing_key` 是调度亲和不进 `RadixKey`；`extra_key` 进 `RadixKey` 但是**隔离键**（不同值阻止共享）。family 相似度仍靠 S1–S5 行为信号。
8. **family 信号分层采集**：结构指纹（tools/system/模板）只在 tokenize 前可见 → 必须在 `serving_chat.py` 拦截（插桩点 1）；行为/缓存信号（prefix hit、`cached_tokens`、retraction、timing）在引擎层可见 → scheduler 旁路采集（插桩点 3-5）。
9. **现成指标可加 family label 复用**：把识别出的 `family_id` 作为新 Prometheus label 注入 §5.6 的聚合指标，即得 family 级统计——但需控 cardinality（借鉴 routing key「全带才算」的保护模式）。

### 5.15 主流 agent 实际使用的入口格式（实证：仓库源码 + 市场核实）

回答「§5.1 三类入口，真实 agent 到底用哪个」。分两部分：本仓库内 4 个真实 agent 的源码核实（带 file:line），以及外部主流 coding agent 的市场现状（2026 网络核实）。

**A. 本仓库 4 个 agent（源码核实）**

| Agent | 入口格式 | 证据（file:line） | 关键行为 |
|-------|---------|------------------|---------|
| mini-swe-agent（默认 `LitellmModel`） | **Chat** | `litellm.completion(messages=..., tools=[BASH_TOOL])`（`Agent/mini-swe-agent/src/minisweagent/models/litellm_model.py:66-70`） | messages+tools，每轮重发全历史 |
| mini-swe-agent（`OpenRouterModel`） | **Chat** | 直接 POST `.../v1/chat/completions`（`openrouter_model.py:60`），payload=`messages`+`tools`+`usage`（`69-75`） | 同上；`BASH_TOOL` 每轮重发=稳定 S1 指纹 |
| mini-swe-agent（`PortkeyResponseAPIModel`） | **Responses** | `client.responses.create(input=..., tools=...)`（`portkey_response_model.py:74`） | **显式 stateless、不用 `previous_response_id`**（`47-49`），仍每轮重发全历史 |
| SWE-agent | **Chat** | `litellm.completion(...)`（`Agent/SWE-agent/sweagent/agent/models.py:722`） | 同 mini 默认路径 |
| codex | **Responses** | `/v1/responses`（`Agent/codex/codex-rs/responses-api-proxy/src/lib.rs:53,173`、`core/src/session/tests/guardian_tests.rs:165`），`response_id` 续接线程（`codex-rs/docs/protocol_v1.md:101`） | **唯一真正吃 Responses 有状态特性的** |
| claude-code | **Anthropic Messages（`/v1/messages`）** | `Agent/claude-code-repo/plugins/security-guidance/README.md:104` | 第四种格式，不在 §5.1 三列内 |

- **主力是 Chat Completions**（mini-swe-agent 默认、SWE-agent）；**codex 是唯一真正用 Responses 会话指针的**；claude-code 走 Anthropic Messages。
- **没有一个用老式 Completion（`/v1/completions`）**。
- 连走 Responses 的 Portkey 实现都**故意 stateless、每轮重发全历史**——印证 §5.9/§5.12：agent 本质是「每轮重发全历史」，用了 Responses API 也不一定用它的会话指针。

**B. 外部主流 coding agent（2026 市场核实）**

| 工具 | 主用入口 | 说明 |
|------|---------|------|
| Cursor | Chat Completions 形态为主 | OpenAI-compatible base URL |
| Cline / Roo Code / Continue | **Chat** | 任意 OpenAI 兼容 base URL；Continue 有 `useResponsesApi: false` 开关 |
| Aider | **Chat** | 最 model-agnostic，`--openai-api-base` 指哪打哪 |
| OpenAI Codex | **Responses** | OpenAI 官方 + Agents SDK 原生 |
| Claude Code | **Anthropic Messages** | Claude 原生 |

出处：OpenAI 官方 2026「Chat Completions remains our most widely adopted API」（[New tools for building agents](https://openai.com/index/new-tools-for-building-agents/)）；Responses 是官方推荐的新默认但落地主要在 OpenAI 自家生态（[Migrate to Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses)）；端点对照把 Cursor-style / LiteLLM / most apps 归到 `/v1/chat/completions`（[DEV Community](https://dev.to/xujfcn/v1chatcompletions-vs-v1responses-vs-v1messages-which-ai-api-endpoint-should-you-use-528n)）。

**C. 对本文档的含义**

1. **§5.1 三列实际权重：Chat ≫ Responses ≫ Completion(≈0)**——动机实验主战场选 Chat API replay（§5.13、§5.14.5）与市场数据一致。
2. **覆盖缺口：Anthropic Messages（`/v1/messages`）**。claude-code 及大量 Claude 原生工具走这条，不在 §5.1 三列。结构上等价于 Chat（有 `messages`+`tools`+顶层 `system`），family 结构信号同样强；若论文声称「覆盖真实 serving 流量」宜补一句定位。
3. **Responses 虽小众但是「显式 id 上界」对照（§5.13 第三行）的现成 trace 源**：codex 自带 `previous_response_id`/`response_id`，可量化零配合推断与显式 id 的 gap。

---

## 六、信号反馈：注入现有机制的四个决策点（RQ3）

### 6.1 保留决策（对应 InferCept 的 preserve/discard）

- `T_INT` 用 **per-family-per-name** 统计替代全局/per-name 统计（避免 Continuum 的跨应用污染）
- `P(return)` 从 family 轮次统计 + 输出内容解析（final answer 标记）推断
- 决策公式：`Waste_preserve = T_INT^family × C × M × (1 - P_terminated^family)`

### 6.2 存储决策（驱逐 / 淘汰）

- **Lifecycle-aware**（借鉴 PBKV）：family 内已终结 session 的 KV 降级为 retired cache，优先淘汰
- **Family 复用价值**：属于 active family 共享前缀的 KV 节点提升保留优先级
  `Value(node) = Σ_{s∈family} P(s 复用 node) × s 的剩余预期轮次`
- **跨 family 隔离**：不同 family 用独立淘汰预算，避免长 context family 挤掉短 session family

### 6.3 调度决策（批次组装 / 优先级）

- **Family-aware batching**：优先把同 family 请求组 batch（最大化 prefix caching 命中）——Parrot 已证收益但靠声明，我们用识别结果
- **Family 级公平性**：`Priority(session) = AttainedService(family) / SessionsInFamily(family)`，避免大 family 饿死小 family
- **跨引擎路由**：同 family 钉到同一组 GPU

### 6.4 预取 / 预判（可选，后期）

- family 的 next-call 分布、argument 来源模式（PASTE 证明参数是抄的）
- 论文可只做前三个，预取留 future work

---

## 七、与现有工作的清晰切割

| 工作 | 做了什么 | 我们的差异 |
|------|---------|-----------|
| **Autellix** | program 级调度，client 声明边界 | ① serving 自动识别 family；② 跨用户/跨 session；③ 信号进 KV 层（Autellix 明确不管 KV 策略） |
| **InferCept** | 单 request preserve/discard | ① 有 session/family 上下文；② 用 family 统计替代全局/per-name |
| **Continuum** | per-name 统计 + TTL pin | ① per-family-per-name（避免污染）；② P(return) 从 family 轮次推断；③ 多 agent 异构 |
| **PBKV** | per-app 训练预测器 | ① 零训练在线识别；② 跨应用；③ family 统计替代预测器 |
| **Tempo** | 在线建图 + 历史匹配，类型靠声明 | ① family 自动识别；② 信号用于 KV 决策（Tempo 不做 KV） |

---

## 八、技术风险与应对

- **Family 识别准确率不够**：即使不完美，粗粒度聚类仍优于全局盲统计；最坏情况每个 session 自成一 family → 退化为 InferCept（但仍有 P(return) 推断增量）。
- **在线聚类开销**：特征向量 O(10) 维、距离 <1ms，只在 session 启动和关键状态变化时更新（类比 Tempo QRF 7ms、PASTE 匹配 <100ms 量级）。
- **被说成 Autellix + InferCept 组合**：① Autellix 不做 KV、不跨用户；② InferCept 不知道 family；③ 核心贡献是「零先验 family 自动识别」building block，是两者都没有的。

---

## 九、下一步规划（只规划思路，不做实验）

1. **确定论文对 session identity 的假设**：显式身份 / 纯推断 / 混合，分别列出可声称与不可声称的性质。
2. **定义 family 的目标函数**：不先选聚类算法，先定义 family 分组应改善哪些状态变量和 KV 决策；区分语义相似、模板相似、行为相似、管理价值相似。
3. **设计 SessionTable / FamilyTable 最小状态**：哪些信号 request 时刻可见、哪些跨轮次积累、哪些 tool 返回或 session 结束后才得到。
4. **识别算法与反馈接口**：session 链接置信度、family 归属置信度、误合并/误拆分对各类 KV 操作的代价、据此采用非对称保守动作策略。

**当前状态**：框架已收敛为 request→session→family 三层；family 定义为面向 KV 管理目标的行为等价类；serving 端可见信号已源码核实（SGLang 主线 + vLLM 对照，§五）。下一步先把 family 目标函数定下来，再选识别算法。

---

## 十、关联文档

- `docs/25_research_directions.md` — 研究方向总览
- `docs/26_cache_management_framework.md` — Cache 管理全链框架（复用价值判据）
- `docs/27_ppt_plan_kv_cache_lifecycle.md` — KV cache 生命周期 PPT 规划
- `docs/30_agentic_serving_request_surface_survey.md` — Agentic serving 请求面改动与身份获取方式调研（前人三路径：声明 / 无身份 / 离线）
- `docs/31_sglang_27574_programmatic_kv_cache_zh.md` — SGLang #27574（Router 可编程 KV hints）完整中文翻译
