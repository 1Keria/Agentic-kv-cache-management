# Agent KV Cache 跨 Session 复用 — 实验结果与分析

> 最后更新：2026-06-10
> 当前数据规模：6 条 instance（均来自 astropy/astropy 仓库，步数限制 10 步）
> 核心数据基于 API 精确值（`usage.prompt_tokens`），前缀拆分使用 tiktoken 估计 + API 校准
> 对应方法论文档：[01_background_and_methodology.md](01_background_and_methodology.md)

---

## 0. 计算方法详解：数据来源与计算逻辑

本节详细说明每个统计指标的数据来源——哪些直接从 `.traj.json` 文件中读取，哪些是脚本自行计算的，以及自行计算的公式和逻辑。

### 0.1 数据源：`.traj.json` 文件结构

mini-swe-agent 运行后自动保存的 `.traj.json` 包含以下结构：

```json
{
  "info": {
    "model_stats": { "instance_cost": float, "api_calls": int },
    "config": { "agent": {...}, "agent_type": str },
    "exit_status": str,
    "submission": str
  },
  "instance_id": str,
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "...", "tool_calls": [...], "extra": {
      "actions": [...],
      "response": { "usage": { "prompt_tokens": int, "completion_tokens": int, "total_tokens": int }, ... },
      "cost": float,
      "timestamp": float
    }},
    { "role": "tool", "tool_call_id": "...", "content": "...", "extra": {
      "raw_output": str,
      "returncode": int,
      "timestamp": float
    }},
    ...
  ],
  "trajectory_format": "mini-swe-agent-1.1"
}
```

### 0.2 指标分类总览

> 📄 = 直接从 `.traj.json` 文件读取 &nbsp;&nbsp; 🔢 = 脚本自行计算 &nbsp;&nbsp; 📄🔢 = JSON 中有精确值，脚本也用 tiktoken 计算了近似值

| 指标 | 来源 | 含义 |
|------|------|------|
| instance_id | 📄 | 当前 session 对应的 SWE-bench 问题标识，格式如 `astropy__astropy-12907`，由仓库名和 issue 编号组成。用于区分不同 session 和按 repo 分组。来源：`data["instance_id"]` |
| exit_status | 📄 | Agent 退出原因：`Submitted`（正常提交）、`LimitsExceeded`（超出步数/费用限制）、`TimeExceeded`（超时）等。影响 trajectory 完整性。来源：`data["info"]["exit_status"]` |
| api_calls | 📄 | Agent 调用 LLM API 的总次数，等于 session 中的 turn 数。反映对话长度。来源：`data["info"]["model_stats"]["api_calls"]` |
| instance_cost | 📄 | 当前 session 的 API 调用总费用（美元）。来源：`data["info"]["model_stats"]["instance_cost"]` |
| n_messages | 📄 | messages 列表的总消息数，包括 system、user、assistant、tool 等所有角色。2 + 2×turns（system + user 初始 + 每轮 assistant + observation）。来源：`len(data["messages"])` |
| system_content | 📄 | System prompt 的原始文本内容，由 swebench.yaml 的 `system_template` 渲染而来。所有 session 完全相同。来源：第一条 `role="system"` 消息的 `content` |
| instance_content | 📄 | Instance template 渲染后的完整文本，包含静态指令部分 + 动态的 `{{task}}` 部分。不同 session 因 task 不同而不同。来源：第一条 `role="user"` 消息的 `content` |
| api_input_tokens | 📄 | LLM API 返回的该 turn 实际输入 token 数，即模型端计算的精确值。来源：`message["extra"]["response"]["usage"]["prompt_tokens"]`。这是衡量 prefill 计算量的**权威数据** |
| api_output_tokens | 📄 | LLM API 返回的该 turn 实际输出 token 数。来源：`message["extra"]["response"]["usage"]["completion_tokens"]`。反映模型生成了多长的回复 |
| api_cached_tokens | 📄 | API 返回的该 turn 命中缓存的 prompt token 数。来源：`message["extra"]["response"]["usage"]["prompt_tokens_details"]["cached_tokens"]`。当前 OpenAI 兼容接口返回 0，Anthropic 原生接口可返回非零值，可用于验证实际缓存命中情况 |
| api_reasoning_tokens | 📄 | API 返回的该 turn 推理 token 数（思维链）。来源：`message["extra"]["response"]["usage"]["completion_tokens_details"]["reasoning_tokens"]`。当前 DeepSeek V4 Flash 返回 0 |
| timestamp | 📄 | 该 turn API 调用的时间戳。来源：`message["extra"]["timestamp"]`。可用于分析 session 间的时间局部性 |
| raw_output | 📄 | 命令执行的原始输出文本。来源：observation 消息的 `extra["raw_output"]` |
| returncode | 📄 | 命令执行返回码。来源：observation 消息的 `extra["returncode"]` |
| n_turns | 🔢 | Agent 与 LLM 交互的轮次数，等于 messages 中 `role="assistant"` 的消息数量。每轮包含一次模型查询 + 一次命令执行。见 0.3 |
| input_tokens | 🔢 | 该 turn 发送给 LLM 的完整输入 prompt 的 tiktoken 估计 token 数。与 📄 `api_input_tokens` 是同一件事的两个度量：`input_tokens` 是 tiktoken 离线估计，`api_input_tokens` 是 API 返回的精确值。tiktoken 系统性偏低约 14%。见 0.4 |
| assistant_tokens | 🔢 | 该 turn 模型回复的 tiktoken 估计 token 数。与 📄 `api_output_tokens` 是同一件事的两个度量。见 0.4 |
| observation_tokens | 🔢 | 该 turn 命令执行结果的 tiktoken 估计 token 数，即 `<returncode>` + `<output>` 等渲染后的内容。**JSON 中无直接对应字段**（`raw_output` 是原始输出，`observation_tokens` 是经 observation_template 渲染后的 token 数）。见 0.4 |
| new_tokens | 🔢 | 该 turn 相比上一 turn 新增的 input token 数 = `input_tokens[k] - input_tokens[k-1]`。如果有 session 内 prefix caching，这就是实际需要 prefill 的 token 量。**JSON 中无直接对应字段**，因为 API 不区分"新增"和"复用"的 prompt_tokens。见 0.5 |
| system_tokens | 🔢 | System prompt 的 tiktoken 估计 token 数。**JSON 中无直接对应字段**（API 的 `prompt_tokens` 是整个输入的总 token 数，不按消息拆分）。见 0.6 |
| instance_static_prefix_tokens | 🔢 | Instance template 中 `{{task}}` 之前的静态文本 token 数。**JSON 中无直接对应字段**（API 不报告消息内部的结构性拆分）。见 0.7 |
| instance_static_suffix_tokens | 🔢 | Instance template 中 `{{task}}` 之后的静态文本 token 数。**JSON 中无直接对应字段**。见 0.7 |
| instance_dynamic_tokens | 🔢 | Instance template 中 `{{task}}` 渲染后的 token 数。**JSON 中无直接对应字段**。见 0.7 |
| shared_prefix_tokens | 🔢 | 跨 session 可复用的共享前缀总 token 数 = system_tokens + instance_static_prefix_tokens + instance_static_suffix_tokens。**JSON 中无直接对应字段**，这是本研究定义的核心指标。见 0.8 |
| session_reuse_ratio | 🔢 | Session 内前缀复用率 = session_reused_tokens / total_input_tokens。**JSON 中无直接对应字段**，但可用 📄 `api_cached_tokens` 验证（如果 API 返回非零 cached_tokens）。见 0.9 |
| cross_session_savings | 🔢 | 跨 session 额外节省的 prefill token 数。**JSON 中无直接对应字段**，这是本研究的核心结论指标。见 0.10 |

### 0.3 JSON 精确值 vs tiktoken 近似值的关系

脚本对同一组量有两种度量：

| 量 | tiktoken 近似值 (脚本计算) | API 精确值 (JSON 读取) | 关系 |
|----|--------------------------|----------------------|------|
| 输入 token 数 | `input_tokens` | `api_input_tokens` | `api_input_tokens ≈ input_tokens × 1.14`（校准系数，见 §4） |
| 输出 token 数 | `assistant_tokens` | `api_output_tokens` | `api_output_tokens ≈ assistant_tokens`（输出侧 tiktoken 误差较小） |

**为什么同时需要两套值**：
- tiktoken 近似值用于**离线分析**：不需要 API 调用，速度快，可以对任意文本做 token 计数（包括 instance_content 的静态/动态拆分、共享前缀等，这些在 API usage 中没有拆分信息）
- API 精确值用于**校准和验证**：`api_input_tokens` 是模型端实际看到的 token 数，是最权威的度量。但由于 API 只报告整个输入的总 token 数，不按消息内部结构拆分，所以**无法直接从 API usage 得到"共享前缀有多少 token"这类细粒度信息**

**只有 tiktoken 能算、API usage 无法提供的指标**：
- `system_tokens`、`instance_static_prefix_tokens`、`instance_static_suffix_tokens`、`instance_dynamic_tokens`：API 只报告 `prompt_tokens` 总数，不拆分每条消息或消息内部的结构
- `shared_prefix_tokens`：这是基于上述拆分合成的指标，API 无法直接提供
- `new_tokens`：API 报告的是每 turn 的总 `prompt_tokens`，不区分新增和复用部分
- `observation_tokens`：API 报告的是上一轮的输出 token，不区分 assistant 回复和 observation 渲染

### 0.3 Turn 划分逻辑

**输入**：`messages` 列表（从 `.traj.json` 读取）

**方法**：按 `role="assistant"` 的消息位置切分

```
messages: [sys, user, asst_0, obs_0, asst_1, obs_1, ..., asst_N, obs_N]

Turn 0: input = messages[:asst_0的位置] = [sys, user]
        assistant = asst_0
        observation = [obs_0]

Turn 1: input = messages[:asst_1的位置] = [sys, user, asst_0, obs_0]
        assistant = asst_1
        observation = [obs_1]

Turn k: input = messages[:asst_k的位置]  (到当前 assistant 之前的所有消息)
        assistant = asst_k
        observation = [asst_k 之后到 asst_{k+1} 之前的 tool/user 消息]
```

**含义**：`input` 就是 Turn k 发送给 LLM API 的完整 prompt（剥离 `extra` 字段后）。

**n_turns** = assistant 消息的数量

### 0.4 Token 计数方法

**对单条消息** `count_message_tokens(msg)`：

```
content_tokens = len(tiktoken.encode(msg["content"]))
tool_call_tokens = Σ len(tiktoken.encode(json.dumps(tc)))  for tc in msg["tool_calls"]
total = content_tokens + tool_call_tokens + 4   (4 = 格式开销近似)
```

**对每个 turn**：

```
input_tokens     = Σ count_message_tokens(msg)  for msg in turn.input_messages  (剥离 extra 后)
assistant_tokens = count_message_tokens(turn.assistant_message)
observation_tokens = Σ count_message_tokens(msg)  for msg in turn.observation_messages
```

### 0.5 New Tokens（每 turn 增量）

```
Turn 0: new_tokens = input_tokens[0]                          (首次全部是新计算)
Turn k: new_tokens = input_tokens[k] - input_tokens[k-1]     (相比上一 turn 新增的部分)
```

**含义**：
- `input_tokens`：Turn k 发给 LLM 的完整 prompt 的 token 数。这个值随 turn 增长而单调递增（因为每轮对话都在历史后面追加）。**它代表了该 turn 的 KV Cache 需要覆盖的总长度**
- `assistant_tokens`：模型该轮回复消耗的 token 数，包括推理文本和工具调用的 JSON。代表输出侧的开销
- `observation_tokens`：命令执行结果渲染后的 token 数，即 `<returncode>` + `<output>` 的内容。它将作为下一轮 input 的一部分，进入 KV Cache

**注意**：`input_tokens[k] = input_tokens[k-1] + assistant_tokens[k-1] + observation_tokens[k-1]`（近似，因为 tiktoken 编码的边界效应可能有微小差异）

### 0.5 New Tokens（每 turn 增量）

```
Turn 0: new_tokens = input_tokens[0]                          (首次全部是新计算)
Turn k: new_tokens = input_tokens[k] - input_tokens[k-1]     (相比上一 turn 新增的部分)
```

**含义**：`new_tokens` 衡量的是该 turn 相比上一 turn **新进入 KV Cache 的 token 数**。在有 session 内 prefix caching 的情况下，Turn k 不需要重新计算整个 `input_tokens[k]` 的 prefill，只需要 prefill 新增的 `new_tokens` 部分（即上一轮的 assistant 回复 + observation），前缀部分直接复用已有 KV Cache。这是 **session 内 KV Cache 复用的核心量化指标**。

### 0.6 System Tokens

```
system_tokens = count_message_tokens(第一条 role="system" 的消息)
```

**含义**：System prompt 的 token 数。这是所有 session 共享的最外层前缀，由 swebench.yaml 的 `system_template` 渲染而来。内容固定为 `"You are a helpful assistant that can interact with a computer shell to solve programming tasks."`，在跨 session 复用中始终可被缓存。

### 0.7 Instance Template 静态/动态分离

**输入**：`instance_content`（第一条 `role="user"` 消息的完整 content，从 `.traj.json` 直接读取）

**为什么要分离**：instance_content 中既包含跨 session 相同的静态指令模板，又包含每个 session 不同的 `problem_statement`。只有精确分离，才能算出真正的跨 session 共享前缀，而不是把整个 instance_content 都当作共享前缀（那会高估复用量）。

**方法**：识别 swebench.yaml 模板中的标记标签，在渲染后的文本中定位动态部分

```
instance_content 的结构（渲染后）:
┌─────────────────────────────────────────────────────┐
│ <pr_description>\n                                │ ← 静态前缀
│ Consider the following PR description:\n          │
│ {{task}}                                          │ ← 动态部分（problem_statement）
│ \n</pr_description>\n\n<instructions>\n...         │ ← 静态后缀
└─────────────────────────────────────────────────────┘
```

**计算步骤**：

```
1. 在 instance_content 中搜索 "<pr_description>\nConsider the following PR description:\n"
2. 找到后，task_start = 该位置 + len(静态前缀文本)
3. 从 task_start 开始搜索 "\n</pr_description>"
4. 找到后，suffix_start = 该位置

5. static_prefix_text = instance_content[:task_start]
   task_content       = instance_content[task_start:suffix_start]
   static_suffix_text = instance_content[suffix_start:]

6. instance_static_prefix_tokens = count_tokens(static_prefix_text)
   instance_dynamic_tokens      = count_tokens(task_content)
   instance_static_suffix_tokens = count_tokens(static_suffix_text)
```

**验证**：`instance_tokens ≈ instance_static_prefix_tokens + instance_dynamic_tokens + instance_static_suffix_tokens`

**各指标含义**：
- `instance_static_prefix_tokens`：`{{task}}` 之前的固定文本 token 数，如 `<pr_description>\nConsider the following PR description:\n`。内容极短（~10 tokens），但它是共享前缀的起始边界标记
- `instance_dynamic_tokens`：`{{task}}` 渲染后的 token 数，即 `problem_statement` 的内容。这是每个 session **唯一不同**的部分，不可跨 session 复用。其值取决于 issue 的描述长度，差异很大（118-737 tokens）
- `instance_static_suffix_tokens`：`{{task}}` 之后的完整指令模板 token 数，包括 `</pr_description>` 后的 `<instructions>` 块（Recommended Workflow、Command Execution Rules、Environment Details、Submission 步骤等）。这是共享前缀中**最大的一块**（~967 tokens），也是跨 session 复用的主要收益来源

### 0.8 跨 Session 共享前缀

```
shared_prefix_tokens = system_tokens + instance_static_prefix_tokens + instance_static_suffix_tokens
```

**含义**：这是**跨 session KV Cache 复用的核心目标**——所有使用同一 `swebench.yaml` 配置的 session 在首次 prefill 时，这部分 token 的 KV Cache 完全相同，只需计算一次即可被所有 session 复用。

**为什么这是跨 session 复用的上界**：在当前 swebench.yaml 配置下，`shared_prefix_tokens` 是一个连续的消息前缀（system + instance template 的静态部分），KV Cache 可以从消息列表开头连续匹配。如果不同 session 的前缀不是连续的（例如中间夹了动态内容），则无法直接复用整个前缀块。

**注意**：BASH_TOOL 定义（~67 tokens）通过 API `tools` 参数传递，不在 messages 列表中，因此脚本无法自动计入。在报告中以 `shared_prefix_tokens + 67 ≈ 1,065` 的方式手动补充。

### 0.9 Session 内复用率

```
total_input_tokens  = Σ_{turn=0}^{N-1} input_tokens[turn]
total_new_tokens    = Σ_{turn=0}^{N-1} new_tokens[turn]
session_reused_tokens = total_input_tokens - total_new_tokens
session_reuse_ratio  = session_reused_tokens / total_input_tokens
```

**各指标含义**：
- `total_input_tokens`：所有 turn 的 input_tokens 之和。这是**没有任何缓存**时需要 prefill 的总 token 数（每轮都从头计算整个 prompt）。它反映了最坏情况下的 prefill 计算量
- `total_new_tokens`：所有 turn 的 new_tokens 之和。这是**有 session 内 prefix caching** 时实际需要 prefill 的总 token 数（每轮只计算新增部分）。它反映了理想情况下的 prefill 计算量
- `session_reused_tokens`：两者之差。这是**被 session 内 prefix caching 节省掉的 prefill token 数**，即不需要重复计算、直接复用已有 KV Cache 的部分
- `session_reuse_ratio`：`session_reused_tokens / total_input_tokens`。衡量 session 内 prefix caching 可节省的 prefill 比例。值越高，说明同一 session 内跨 turn 的前缀重复度越高，缓存收益越大

### 0.10 跨 Session KV Cache 节省量

**三种方案**：

```
方案1 - 无缓存（baseline）:
  total_prefill_no_cache = Σ_sessions(Σ_turns(input_tokens))

方案2 - Session 内缓存（现有方案）:
  total_prefill_session_cache = Σ_sessions(first_turn_input + Σ_{turn>0}(new_tokens[turn]))
  session_cache_savings = total_prefill_no_cache - total_prefill_session_cache

方案3 - + 跨 session 缓存:
  cross_session_savings = Σ_groups((group_size - 1) × group_shared_prefix)
  total_prefill_cross_session = total_prefill_session_cache - cross_session_savings
```

**跨 session 节省的直觉**：同一组内第一个 session 计算 shared_prefix 的 KV Cache，后续 (group_size - 1) 个 session 直接复用，每个节省 shared_prefix tokens 的 prefill。

**各方案含义**：
- **方案1（无缓存 baseline）**：每个 session 的每个 turn 都从头做完整 prefill，不利用任何 KV Cache 复用。`total_prefill_no_cache` 是所有 session 所有 turn 的 input_tokens 之和，代表最坏情况下的总 prefill 计算量
- **方案2（Session 内缓存）**：同一 session 内，后续 turn 复用已有 KV Cache，只 prefill 新增部分。`first_turn_input` 是首 turn 的完整 prefill，`Σ_{turn>0}(new_tokens)` 是后续 turn 的增量 prefill。这是当前 serving 框架已经支持的方案
- **方案3（+ 跨 session 缓存）**：在方案2 基础上，不同 session 的首次 prefill 也复用共享前缀。同一组内第一个 session 正常计算共享前缀的 KV Cache，后续 session 跳过这部分 prefill，直接从动态 task 内容开始计算。`cross_session_savings` 就是这些被跳过的 prefill 总量

---

## 1. 实验数据概览

| 参数 | 值 |
|------|-----|
| 已分析 session 数 | 6 |
| 来源仓库 | astropy/astropy（全部） |
| 每 session 最大步数 | 10 |
| 退出状态 | 全部 LimitsExceeded |
| 平均 turn 数 | 10 |
| Token 计数方式 | tiktoken cl100k_base + API 实际值对比 |

---

## 2. 跨 Session 共享前缀分析

### 2.1 前缀组件 Token 数与复用能力

> 以下数据基于 `astropy__astropy-12907` 的 Turn 0（API prompt_tokens = 1,623）。

| 组件 | 标记 | tiktoken | API 校准后 | 跨 Session 相同？ | 能否形成连续前缀？ | 复用范围 |
|------|------|---------|-----------|------------------|------------------|---------|
| System Prompt | 【A】 | 17 | ~21 | ✅ 完全相同 | ✅ 位于最开头 | 所有 300 条 |
| Instance 静态前缀 | 【B1】 | 10 | ~12 | ✅ 完全相同 | ✅ 紧接 System 之后 | 所有 300 条 |
| **Instance 动态部分** | **【B2】** | **322** | **~397** | **❌ 每个 instance 不同** | **❌ 阻断前缀** | **仅本 session** |
| Instance 静态后缀 | 【B3】 | 967 | ~1,193 | ✅ 完全相同 | ❌ 被 B2 阻断 | 所有 300 条 |
| BASH_TOOL 定义 | 【C】 | 63 | ~78 | ✅ 完全相同 | ❌ 被 B2 阻断 | 所有 300 条 |
| API 格式开销 | 【D】 | - | ~245 | ✅ 完全相同 | ⚠️ 分散在各消息间 | 所有 300 条 |

### 2.2 前缀断裂问题

**核心发现**：虽然【B3】+【C】+【D】在所有 session 中内容完全相同（~1,516 tokens），但由于动态的【B2】插在中间，**传统 prefix caching 无法复用这些内容**。

```
传统前缀缓存可复用:  【A】+【B1】                    = ~33 tokens  (2.0%)
被阻断的相同内容:    【B3】+【C】+【D】              = ~1,516 tokens (93.3%)
不可复用:            【B2】(动态)                     = ~397 tokens  (24.5%)
```

### 2.3 三种复用方案对比

| 方案 | 可复用内容 | API 校准后 | 占首 turn | 实现方式 |
|------|-----------|-----------|----------|---------|
| **传统前缀缓存** | 【A】+【B1】 | ~33 | ~2.0% | 现有 serving 框架已支持 |
| **Prompt 重排** | 【A】+【B1】+【B3】+【C】 | ~1,304 | ~80.3% | 修改模板，把 `{{task}}` 移到末尾 |
| **非连续 KV Cache 复用** | 【A】+【B1】+【B3】+【C】+【D】 | ~1,302 | ~80.2% | 新系统设计，跳过动态部分 |

> **Prompt 重排**是最实际的优化：只需修改 `swebench.yaml`，将 `{{task}}` 移到模板末尾，即可让传统 prefix caching 复用 ~80% 的首 turn 内容。

### 2.4 每个 Session 的前缀分解（实测数据）

| Instance | 首 turn API Prompt | 【A】+【B1】(传统前缀) | 【B2】(动态) | 【B3】+【C】(被阻断) | 重排后可复用 |
|----------|-------------------|---------------------|------------|-------------------|------------|
| astropy-12907 | 1,623 | ~33 (2.0%) | ~397 (24.5%) | ~1,193 (73.5%) | ~1,226 (75.5%) |
| astropy-14182 | 1,910 | ~33 (1.7%) | ~625 (32.7%) | ~1,252 (65.6%) | ~1,285 (67.3%) |
| astropy-14365 | 1,797 | ~33 (1.8%) | ~547 (30.4%) | ~1,217 (67.7%) | ~1,250 (69.6%) |
| astropy-14995 | 2,061 | ~33 (1.6%) | ~908 (44.1%) | ~1,120 (54.3%) | ~1,153 (56.0%) |
| astropy-6938 | 1,430 | ~33 (2.3%) | ~145 (10.1%) | ~1,252 (87.5%) | ~1,285 (89.9%) |
| astropy-7746 | 1,797 | ~33 (1.8%) | ~701 (39.0%) | ~1,063 (59.1%) | ~1,096 (61.0%) |

**关键发现**：
- **传统前缀缓存只能复用 ~2% 的首 turn**（仅 System + 静态前缀 ~33 tokens），几乎无用
- **Prompt 重排后可复用 56%-90%**，均值 ~70%，收益巨大
- 动态部分（task）越短，重排收益越高（astropy-6938: task 仅 145 tokens → 可复用 89.9%）

---

## 3. Session 内前缀复用分析

### 3.1 单 Session 逐 Turn 分析（API 精确数据）

以 `astropy__astropy-12907` 为例（10 turns）：

| Turn | Prompt Tokens (API) | Completion Tokens (API) | Increment | Reuse% |
|------|--------------------|-----------------------|-----------|--------|
| 0 | 1,623 | 92 | 1,623 | 0.0% |
| 1 | 1,768 | 45 | 145 | 91.8% |
| 2 | 1,867 | 49 | 99 | 94.7% |
| 3 | 1,970 | 44 | 103 | 94.8% |
| 4 | 2,068 | 46 | 98 | 95.3% |
| 5 | 2,168 | 62 | 100 | 95.4% |
| 6 | 2,284 | 62 | 116 | 94.9% |
| 7 | 2,400 | 49 | 116 | 95.2% |
| 8 | 2,503 | 71 | 103 | 95.9% |
| 9 | 2,628 | 73 | 125 | 95.2% |

> 所有数据来自 `.traj.json` 中的 `extra.response.usage` 字段，无 tiktoken 估计。

**Session 内复用统计**：
- 总 prompt_tokens（所有 turns）: 21,279
- 增量 prompt_tokens: 2,628
- 复用 prompt_tokens: 18,651
- **Session 内复用率: 87.6%**

### 3.2 所有 Session 的 Session 内复用率（API 精确数据）

| Instance | 总 Prompt Tokens | 增量 | 复用 | 复用率 |
|----------|-----------------|------|------|-------|
| astropy-12907 | 21,279 | 2,628 | 18,651 | 87.6% |
| astropy-14182 | 25,074 | 2,837 | 22,237 | 88.7% |
| astropy-14365 | 23,652 | 2,703 | 20,949 | 88.6% |
| astropy-14995 | 25,803 | 2,788 | 23,015 | 89.2% |
| astropy-6938 | 19,728 | 2,401 | 17,327 | 87.8% |
| astropy-7746 | 23,603 | 2,761 | 20,842 | 88.3% |
| **总计** | **139,139** | **17,118** | **122,021** | **87.7%** |

---

## 4. tiktoken 与 API 精确值对比

### 4.1 校准系数

| 指标 | 值 |
|------|-----|
| 校准系数均值 (API/tiktoken) | **1.23** |
| 校准系数范围 | 1.19 - 1.29 |
| 差额来源 | API 格式开销（role tags, tool schema 编码, 消息分隔符）约 245 tokens/turn |

### 4.2 差额分析（以 astropy-12907 Turn 0 为例）

| 组成 | tiktoken 估计 | API 精确值 | 差额 |
|------|-------------|-----------|------|
| system + instance content | 1,315 | - | - |
| BASH_TOOL 定义 | 63 | - | - |
| **可测量内容合计** | **1,378** | - | - |
| API 格式开销 | - | ~245 | - |
| **首 turn 总计** | - | **1,623** | 245 |

> API 的 `prompt_tokens` 包含了消息格式、role 标签、tool schema 在 API 端的编码开销，这些 tiktoken 无法精确计算。但**这些格式开销在所有 session 中也是相同的**，因此也属于跨 session 可复用的共享前缀。

---

## 5. 跨 Session KV Cache 节省量

### 5.1 三种方案对比（6 条数据，API 精确值）

| 方案 | 总 Prefill Tokens | 节省量 | 节省比例 |
|------|------------------|--------|---------|
| 无缓存（baseline） | 139,139 | - | - |
| Session 内缓存（现有方案） | 27,552 | 111,587 | 80.2% |
| + 跨 session 缓存（我们的方案） | 21,423 | 6,109 (额外) | 4.4% (额外) |
| **总计** | **21,423** | **117,716** | **84.6%** |

### 5.2 跨 Session 节省的理论分析

N 个 session 共享前缀 P tokens（API 校准后 ~1,222 tokens）时的节省量：

| N (session 数) | 跨 Session 节省 (tokens) | 节省比例 |
|----------------|------------------------|---------|
| 2 | 1,222 | 50.0% |
| 5 | 4,888 | 80.0% |
| 10 | 10,998 | 90.0% |
| 50 | 59,878 | 98.0% |
| 100 | 120,978 | 99.0% |
| 300 | 365,278 | 99.7% |

> 以上为首次 prefill 的节省比例。跨 session 缓存的增量节省主要体现在首次 prefill 阶段。

---

## 6. 关键洞察

### 6.1 前缀断裂是跨 Session 复用的核心障碍

传统 prefix caching 只能复用从 prompt 开头连续匹配的部分。在当前模板结构下，动态的 `problem_statement` 插在中间，导致**~1,516 tokens 的相同内容被阻断**：

- 传统前缀缓存仅复用 ~33 tokens（2.0%）——几乎无用
- Prompt 重排可恢复 ~1,304 tokens（80.3%）的连续前缀
- 这意味着**模板设计对 KV Cache 复用有决定性影响**

### 6.2 Prompt 重排是最实际的优化

| 方案 | 可复用 | 实现成本 | 兼容性 |
|------|--------|---------|--------|
| 传统前缀缓存 | ~2.0% | 零 | 现有框架 |
| Prompt 重排 | ~80.3% | 修改模板 | 现有框架 |
| 非连续复用 | ~80.2% | 新系统设计 | 需要新框架 |

Prompt 重排只需修改 `swebench.yaml`，将 `{{task}}` 移到模板末尾，无需任何框架改动，就能让传统 prefix caching 复用 ~80% 的首 turn。

### 6.3 同 Repo 内没有额外前缀复用（L3 层级）

对 SWE-bench_Lite 全部 300 条数据的分析：
- **所有 repo 内，task 之间的最长公共前缀 = 0 tokens**（不同 issue 描述从第一个词就不同）
- 同 repo 内的共同内容是零散片段（Traceback header、import 语句），不形成前缀
- L3 层级的额外复用收益极小（最大 django ~144 tokens），且需要非连续复用机制
- **跨 session 复用的主要收益来自模板级共享（L1+L2），而非 repo 级共享（L3）**

### 6.4 Session 内复用 vs 跨 Session 复用

| 维度 | Session 内复用 | 跨 Session 复用（重排后） |
|------|--------------|------------------------|
| 解决的问题 | 同一 session 内后续 turn 的重复 prefill | 不同 session 之间首次 prefill 的重复计算 |
| 复用率 | ~87.7% (API 精确值) | 首 turn 的 ~80.3% (重排后, API 精确值) |
| 实现难度 | 已有成熟方案（prefix caching） | Prompt 重排 + 跨 session 缓存管理 |
| 关系 | 正交的、可叠加的 | 正交的、可叠加的 |

### 6.5 当前数据的局限

1. **数据规模小**：仅 6 条，且全部来自 astropy 仓库
2. **步数限制**：10 步限制导致 trajectory 不完整，真实场景通常 30-50 步
3. **单一配置**：仅分析了 `swebench.yaml`，未覆盖其他配置
4. **tiktoken 校准**：共享前缀的精确拆分仍依赖 tiktoken 估计 + API 校准（比例法），非 API 直接返回
5. **缺少时间局部性分析**：未分析 batch 运行中 session 的到达模式
6. **API cached_tokens = 0**：当前 OpenAI 兼容接口不返回缓存命中信息，无法验证实际缓存情况
7. **Prompt 重排未实测**：重排后的复用率是理论计算，未实际运行验证

---

## 7. 待补充的分析

- [ ] Prompt 重排实测：修改 `swebench.yaml` 将 `{{task}}` 移到末尾，实际运行验证复用率
- [ ] 全量 300 条 SWE-bench_Lite 数据的 trace 采集与分析（覆盖多 repo）
- [ ] 更完整 trajectory（30-50 步）下的 KV Cache 增长模式
- [ ] 时间局部性分析：batch 运行中 session 的到达时间差
- [ ] 不同配置下的共享前缀长度对比（如 swebench_backticks.yaml）
- [ ] KV Cache 显存节省量估算（token 数 → GPU 显存 GB）
- [ ] 跨不同 agent 框架的 prompt 结构对比（如 OpenDevin, SWE-Agent 原版）
