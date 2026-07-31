# GLM-5.1 线上数据形态报告

> 数据：`third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl`  
> 来源副本：`/share/dai-sys/wanghanzhen/projects/MTP/training_data/glm-5dot1_onlinedata_lt32k.jsonl`  
> 分析日期：2026-07-30  
> 规模：约 **1.7G**，**16559** 条有效记录（另有 1 行外层 JSON 解析失败）

---

## 1. 一句话结论

这是一份 **线上 Chat Completion 调用日志**：一行 = 一次 LLM 请求/响应。  
主体是 **带 tools 的 agent / subagent 流量**（约 80% 以 `tool_calls` 结束），上下文很长、输出偏短，且 `usage` 里大量 `cached_tokens`。  
**注意：本文件里每个 `trace_id` 只出现 1 次**，不能靠 trace 直接当 session；历史多轮压在当次 `messages` 里。  
但可用 **首条 user + messages 前缀增长** 从内容推断同 session 多跳（见 §8）。

---

## 2. 外层字段（每行一条 span）

| 字段 | 类型 | 覆盖率 | 含义 |
|---|---|---|---|
| `tenant_id` | string | 100% | 租户 ID（本文件 **仅 1 个租户**：`te-dcjhehqegii2hpiv`） |
| `start_time` | string (ISO8601) | 100% | 请求开始时间，带时区 |
| `trace_id` | string | 100% | 链路 ID（本文件内 **唯一**，16559 个 trace 各 1 条） |
| `span_id` | string | 100% | span ID |
| `prompt_body` | string | 100% | **字符串化的**请求 JSON（需再 `json.loads`） |
| `response_body` | string | 100% | **字符串化的**响应 JSON（需再 `json.loads`） |

时间跨度（按 `start_time`）：**2026-05-08 14:33** ~ **2026-05-10 00:33**（约 1.5 天）。

---

## 3. `prompt_body`（解析后的请求）

本质是一次类 OpenAI Chat Completions 请求。

### 3.1 顶层键

| 字段 | 出现次数 | 说明 |
|---|---:|---|
| `messages` | 16559 | 对话历史（含本轮之前的 assistant/tool） |
| `model` | 16559 | 请求侧模型名（均为 `glm-5.1`） |
| `temperature` / `top_p` / `do_sample` | 16559 | 采样参数 |
| `max_tokens` | 16559 | 常见为 32768（与文件名 lt32k 一致量级） |
| `stream` / `stream_options` | 16559 | 几乎全部 `stream=true` |
| `tools` | 16551 | 工具定义列表（几乎全覆盖） |
| `tool_choice` | 160 | 少见；出现时多为 `"auto"` |
| `separate_reasoning` | 16559 | 分离 reasoning |
| `enable_thinking` / `include_reasoning` | ~16550 | thinking 开关 |
| `reasoning_effort` | 16287 | 常见 `high` |
| `thinking` | 16559 | thinking 配置对象 |
| `chat_template_kwargs` | 16559 | 如 `enable_thinking` / `clear_thinking` |
| `extra` | 16559 | 额外元数据（如 moderation） |

### 3.2 `messages[]` 按 role 的字段

| role | 条数（全库累加） | 典型字段 |
|---|---:|---|
| `system` | 17019 | `role`, `content` |
| `user` | 48518 | `role`, `content` |
| `assistant` | 157178 | `role`, `content`, 常有 `tool_calls`、`reasoning_content` |
| `tool` | 167535 | `role`, `tool_call_id`, `content` |

### 3.3 工具定义

- 带 `tools` 的请求：**16551 / 16559**
- 每个请求工具个数：min 2 / p50 **25** / mean 29.6 / p90 45 / max **180**
- 高频工具名（出现在多少请求的 tools 列表中，非调用次数）：  
  `write_file`, `read_file`, `edit_file`, `search_web`, `fetch_web`, `bash`, `memory_search`, `mobile_use`, …  
  → 偏 **文件编辑 + 网页 + shell + 移动端** 的通用 agent 工具集。

---

## 4. `response_body`（解析后的响应）

| 字段 | 说明 |
|---|---|
| `id` / `created` / `object` / `model` | 标准 completion 元数据；`model=glm-5.1` |
| `choices` | 通常 1 个 choice |
| `usage` | token 用量 |

### 4.1 `choices[0]`

| 字段 | 说明 |
|---|---|
| `finish_reason` | 见下表 |
| `message.role` | `assistant` |
| `message.content` | 文本回复；**大量 tool 轮为空串** |
| `message.reasoning_content` | 几乎总有该键；内容可为空 |
| `message.tool_calls` | 约 13293 条响应带此字段 |

**finish_reason 分布：**

| finish_reason | 条数 | 占比 |
|---|---:|---:|
| `tool_calls` | 13282 | **80.2%** |
| `stop` | 3261 | 19.7% |
| `length` | 10 | ~0.06% |
| 空 | 6 | ~0.04% |

主 agent vs subagent（用 system 是否含 `subagent` 粗分）：

| | tool_calls | stop | 其他 |
|---|---:|---:|---:|
| 非 subagent（约 14292） | 11138 | 3138 | 16 |
| subagent（约 2267，**13.7%**） | 2144 | 123 | 0 |

→ subagent 更「埋头调工具」，较少直接 `stop` 长答。

### 4.2 `usage`

| 字段 | 覆盖 |
|---|---|
| `prompt_tokens` / `completion_tokens` / `total_tokens` | 全覆盖 |
| `prompt_tokens_details.cached_tokens` | 16433 |
| `completion_tokens_details.reasoning_tokens` | 16295 |

---

## 5. 关键统计

### 5.1 上下文与输出

| 指标 | min | p10 | p50 | mean | p90 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| messages 条数 / 请求 | 4 | 5 | **17** | 23.6 | 46 | 112 | 789 |
| prompt_tokens | 7972 | 13024 | **23939** | 23771 | 32100 | 47225 | 129906 |
| completion_tokens | 1 | 32 | **117** | 203 | 487 | 1166 | 2233 |
| cached_tokens | 64 | 8512 | **20032** | 19311 | 29376 | 32256 | 32704 |
| reasoning_tokens | 1 | 18 | **61** | 128 | 310 | 848 | 1923 |
| 输出 content 字符数 | 0 | 0 | **0** | 83 | 240 | 1019 | 6859 |

要点：

- **输入很长**（中位 ~24k tokens），符合 agent 前缀累加。
- **输出偏短**（中位 117 completion tokens）；很多轮 `content` 为空，主要靠 `tool_calls`。
- **缓存命中很高**：`cached_tokens / prompt_tokens` 中位约 **0.93**，p90 约 **0.99**（线上已有强 prefix cache 行为）。

### 5.2 对本规划的含义（混合流量）

| 规划中的画像 | 本数据是否像 |
|---|---|
| Agent：短输出、高频 tool 环、长前缀 | **很像**（主体） |
| Request：人驱动、长 decode | **本文件几乎不体现**；不能单靠它构造双边混合负载 |

另外：因 **每 trace 仅 1 条**，不能直接按 trace 算 `pre_gap`；部分会话可用 §8 从内容还原空档，其余需显式合成到达过程。

---

## 6. 典型例子

下列例子来自真实行；正文只保留结构与短预览，避免大段隐私内容。

### 例子 A：Subagent + `tool_calls`（最常见形态）

- **行号**：1  
- **时间**：2026-05-08T14:33:02+08:00  
- **特征**：system 标明「你是一个 subagent」；历史 39 条 messages；25 个工具定义  
- **结束**：`finish_reason=tool_calls`，调用 `read_file`；`content` 为空  
- **用量**：`prompt_tokens=22952`，`cached_tokens=22592`（约 98% cache），`completion_tokens=27`（几乎全是 reasoning）

角色序列头：`system → user → assistant → tool → tool → assistant → tool → tool → …`

### 例子 B：主 agent + `tool_calls`

- **行号**：2  
- **特征**：非 subagent；9 条 messages；`finish_reason=tool_calls`，`read_file`  
- **用量**：`prompt_tokens=15849`，`cached_tokens=15104`，`completion_tokens=30`  
- 同样是「短输出 + 调工具」，但是主 agent system（「你不是聊天机器人…」一类人设说明书）

### 例子 C：`stop` 短回复（对人说话，但仍在 agent 会话中）

- **行号**：12  
- **特征**：8 条 messages；`finish_reason=stop`；无 tool_calls  
- **content 预览**：`在写了，修订版方案很快就出来。`  
- **reasoning 预览**：提到 sub-agent session 已启动、很快完成  
- **用量**：`prompt_tokens=26430`，`completion_tokens=35`  
→ 说明「stop」不等于「普通聊天 Request」；仍可能是 agent 对人的短状态更新。

### 例子 D：长历史后的 `stop`

- **行号**：47  
- **特征**：`n_messages=81`；`finish_reason=stop`  
- **content 预览**：`正在最后整理中，马上出来！稍等一下刘先生～`  
- **用量**：`prompt_tokens=29177`，`completion_tokens=16`  
→ 超长上下文 + 极短输出，KV 压力在 prompt 侧。

### 例子 E：Subagent 任务收尾（较长 `stop` 文本）

- **行号**：53  
- **特征**：subagent；20 条 messages；`finish_reason=stop`  
- **content**：表格化汇报「修复完成 / Batch_ID 修改结果 / 验证结果…」（约数百字）  
- **用量**：`completion_tokens=252`（其中 `reasoning_tokens=251`，对外 content 相对短、reasoning 占比极高）  
→ 同属 agent，但结束轮会吐出一段汇总；仍远短于「人驱动长文生成」的典型长 decode。

---

## 7. 解析时注意点

1. **必须两层 JSON**：外层 → 再 `loads(prompt_body)` / `loads(response_body)`。  
2. **`trace_id` 不能当多轮 session 键**（本文件一一对应）；多轮结构看 `messages`。  
3. **输出长度不要只看 `content`**：tool 轮常为空；应看 `completion_tokens` / `tool_calls` / `reasoning_tokens`。  
4. **敏感内容**：messages 含用户设定、文件路径、业务文本；报告与对外分享需脱敏。  
5. 文件名 `lt32k` 与大量 `max_tokens=32768`、以及 `cached_tokens` 上界贴近 32k 块，暗示按 32k 相关约束筛过。

---

## 8. 从内容推断「同一 Session」的多跳（方法 + 例子）

### 8.1 为什么还能推断

外层 **没有** 可用的 `session_id`：每个 `trace_id` / `span_id` 在本文件里基本只出现一次。  
但每次请求的 `messages` 是「截至当前的完整对话快照」。若同一条 agent 会话连续多轮调用，则通常满足：

1. **会话锚点相同**：首条 `user`（或 `system + 首条 user`）内容相同；  
2. **历史前缀增长**：后一次的 `messages` 条数更多，且 **前一次 messages 是后一次的 exact prefix**（前面的 role/content/tool 记录一字不差地保留）；  
3. **`start_time` 递增**：两次到达的时间差 ≈ 轮间空档（还含上一次 decode + tool 墙钟）。

> 注意：只靠共用的 system 人设模板 **不能** 当 session（很多人共用同一段「你是 agent…」）。  
> 更稳的是用 **首条 user**（任务正文）做锚点，再用 prefix 增长做验证。

判定流程（当前手工/脚本用法）：

```text
对每行解析 prompt_body.messages
  → 取首条 user 内容做 hash 作为候选 session 键
  → 同键下按 start_time 排序
  → 检查相邻两次是否 messages exact prefix 且长度增加
  → 若是，则视为同一 session 的连续到达；空档 = Δstart_time
```

这是 **内容推断**，不是官方标注；并行 subagent、分叉、截断历史会造成噪声，需要过滤。

### 8.2 例子：同一 Session 的 6 次连续调用

> **完整 messages 正文**（步 0 全 9 条 + 后续每步新增条）见同目录：  
> [`session_example_content.md`](session_example_content.md)  
> （登录账号/密码/手机号已脱敏为 `***REDACTED***` / `***********`。）

#### 汇总表

| 步 | 行号 | start_time | n_messages | finish_reason | prompt_tok | cached_tok | completion_tok | 本轮 tool | Δstart |
|---:|---:|---|---:|---|---:|---:|---:|---|---:|
| 0 | 2 | 14:33:01.722 | 9 | tool_calls | 15849 | 15104 | 30 | read_file | — |
| 1 | 185 | 14:33:04.955 | 11 | tool_calls | 16105 | 15808 | 605 | skill_load | 3.2s |
| 2 | 250 | 14:33:25.920 | 13 | tool_calls | 22359 | 16064 | 65 | bash | 21.0s |
| 3 | 456 | 14:33:33.478 | 15 | tool_calls | 22584 | 22336 | 26 | bash | 7.6s |
| 4 | 504 | 14:33:44.813 | 17 | tool_calls | 22827 | 22528 | 67 | bash | 11.3s |
| 5 | 583 | 14:33:52.038 | 19 | tool_calls | 22947 | 22784 | 26 | bash | 7.2s |

六次 `trace_id` 全不同，例如：

```text
步0 2605081433011ef7583b83c10a08bcde
步1 260508143304cc1f268fb9ded59e7e9f
步2 260508143325b2fc638308a97a4123b7
…
```

相邻两步 messages 均为 **`exact_prefix=True`**。

#### 首条 user（Session 锚点，全文；已脱敏）

六次请求的这条 user **完全相同**：

```text
<主 agent 发送给你的日程信息>

日程ID: e7cc1526-dab0-4bcb-9e17-ca1e278a5919_split_7633370043375436072

日程名称: 皮肤管理店预约提醒

当前时间：2026年5月8日 星期五 14:32:48

日程描述: **任务目标：** 检查云管门店系统是否有新预约，如果有则同时通过微信和扣子APP通知主人。

**执行步骤：**
1. 使用云电脑浏览器访问：https://www.yuguaikeji.com/pc/index.html#/login
2. 登录账号：***REDACTED***，密码：***REDACTED***
3. 进入"预约管理" → "预约列表"
4. 查看今日及未来几天的预约记录
5. 对比之前记录的预约列表，找出新增的预约
6. 如果有新预约，同时发送通知到两个渠道：
   - **微信通知**：使用 sessions_send 发送到微信session ID: 7632253632464830762 …
   - **扣子APP通知**：使用 sessions_send 发送到扣子session ID: 7632244979280380212 …
7. 更新预约记录文件

**运行时间：** 每天 8:00 - 23:00，每小时执行一次
…
</主 agent 发送给你的日程信息>
```

#### System（开头预览）

```text
# 你的角色
你是一个任务执行 agent。你被系统唤起来执行一张任务工单。
工单信息会通过消息发送给你，包含任务名称、描述和调度规则。
执行好工单任务，然后将执行结果告知调度方（主 agent），就是你的全部目的。

# 工作流程
1. 理解工单要求…
2. 判断是否有匹配的技能可用…
3. 最终输出会自动返回给调度方（主 agent）
…
```

#### 步 0 的 messages 角色链（内容见 content 文件）

```text
[0] system
[1] user          ← 上面的日程工单（锚点）
[2] assistant     tool_calls=[bash]
[3] tool          ← bash 列出 预约记录*.md / appointments.json
[4] assistant     tool_calls=[read_file, read_file]
[5] tool          ← 读 预约记录.md
[6] tool          ← 读 appointments.json
[7] assistant     tool_calls=[read_file]
[8] tool          ← 继续读 json 片段
→ 本步响应：再 read_file(appointments.json, offset=158)
```

#### 前缀如何涨（每步只追加 2 条）

```text
步0 (9)  = 上表 0..8
步1 (11) = 步0 全部 + [9] assistant(read_file) + [10] tool(结果)
步2 (13) = 步1 全部 + assistant + tool
…
步5 (19) = 步0 前缀上共追加 5 轮 assistant/tool
```

读法：同一工单 session 在约 50 秒内连打 6 次 LLM；**空档 = Δstart_time**（3～21s），中间夹着 tool 执行。  
逐步新增的 tool 返回原文见 [`session_example_content.md`](session_example_content.md)。

### 8.3 对「缺时间轴」说法的修正

- **缺的是**：现成的 session 字段 / 同 `trace_id` 多 span。  
- **不缺的是**：不少会话仍可通过 **首条 user + messages 前缀增长 + start_time** 从内容里还原多跳时间轴。  
- 全库并非每条都能这么干净归组；大模板碰撞、并行任务需要额外规则。全量聚类脚本与纯度统计可另做，本节只固定方法与一例。

---

## 9. 建议的后续用法（对接 D0）

若用这份数据做混合负载 **Agent 侧原材料**：

1. 以一行一次调用重放 `messages`（或截断到可跑长度）；  
2. 用 `finish_reason` / `completion_tokens` 控制短输出；  
3. **Request（人·长输出）侧需另找数据或合成**；  
4. 跨调用时间轴：优先尝试 §8 的内容聚类还原真实空档；还原失败或纯度不足时，再 **显式合成** 到达过程（见 `docs/真实数据构造.md` / 主规划 D0）。

本报告只描述数据形态与统计，不定义策略。
