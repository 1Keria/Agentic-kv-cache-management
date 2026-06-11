# Agent Session Prompt 组织结构

> 基于 mini-swe-agent v2.3.0 + SWE-bench 配置（swebench.yaml）
> 最后更新：2026-06-10

---

## 1. 基本概念

一个 **session** = agent 解决一个 SWE-bench 问题（一个 GitHub issue）的完整过程。

session 内部是**多轮对话**（turn），每轮包含：
1. Agent 发送 prompt 给 LLM（输入）
2. LLM 返回推理文本 + 工具调用（输出）
3. 执行命令，返回结果（observation）

以下以 `astropy__astropy-12907` 为具体实例，逐层展示 prompt 的组成。

---

## 2. Turn 0：首次请求的 Prompt

Turn 0 是 session 的第一次 LLM 调用。此时对话历史为空，prompt 仅包含初始化内容。

### 2.1 完整结构

```
┌──────────────────────────────────────────────────────────────────┐
│ 【A】System Message                                               │
│                                                                    │
│   "You are a helpful assistant that can interact with a           │
│    computer shell to solve programming tasks."                    │
│                                                                    │
│   tiktoken: 17 tokens                                             │
├──────────────────────────────────────────────────────────────────┤
│ 【B】User Message — Instance Template 渲染后的完整内容              │
│                                                                    │
│   ┌──────────────────────────────────────────────────────────┐   │
│   │ 【B1】静态前缀                                            │   │
│   │                                                            │   │
│   │   "<pr_description>                                       │   │
│   │    Consider the following PR description:                 │   │
│   │    "                                                      │   │
│   │                                                            │   │
│   │   tiktoken: 10 tokens                                     │   │
│   ├──────────────────────────────────────────────────────────┤   │
│   │ 【B2】动态部分 — problem_statement（每个 instance 不同）    │   │
│   │                                                            │   │
│   │   "Modeling's `separability_matrix` does not compute      │   │
│   │    separability correctly for nested CompoundModels       │   │
│   │    Consider the following model:                          │   │
│   │                                                            │   │
│   │    from astropy.modeling import models as m               │   │
│   │    from astropy.modeling.separable import separability... │   │
│   │                                                            │   │
│   │    cm = m.Linear1D(10) & m.Linear1D(5)                   │   │
│   │    ..."                                                   │   │
│   │                                                            │   │
│   │   tiktoken: 322 tokens (本例)                              │   │
│   │   范围: 118 ~ 737 tokens (6 条 astropy 实测)               │   │
│   ├──────────────────────────────────────────────────────────┤   │
│   │ 【B3】静态后缀                                            │   │
│   │                                                            │   │
│   │   "</pr_description>                                      │   │
│   │                                                            │   │
│   │    <instructions>                                         │   │
│   │    # Task Instructions                                    │   │
│   │                                                            │   │
│   │    ## Overview                                            │   │
│   │    You're a software engineer interacting continuously    │   │
│   │    with a computer by submitting commands.                │   │
│   │    You'll be helping implement necessary changes to meet  │   │
│   │    requirements in the PR description.                    │   │
│   │    Your task is specifically to make changes to non-test  │   │
│   │    files in the current directory in order to fix the     │   │
│   │    issue described in the PR description...               │   │
│   │                                                            │   │
│   │    ## Important Boundaries                                │   │
│   │    - MODIFY: Regular source code files in /testbed        │   │
│   │    - DO NOT MODIFY: Tests, configuration files            │   │
│   │                                                            │   │
│   │    ## Recommended Workflow                                │   │
│   │    1. Analyze the codebase by finding and reading...      │   │
│   │    2. Create a script to reproduce the issue              │   │
│   │    3. Edit the source code to resolve the issue           │   │
│   │    4. Verify your fix works by running your script again  │   │
│   │    5. Test edge cases to ensure your fix is robust        │   │
│   │                                                            │   │
│   │    ## Command Execution Rules                             │   │
│   │    ...                                                    │   │
│   │                                                            │   │
│   │    ## Environment Details                                 │   │
│   │    ...                                                    │   │
│   │                                                            │   │
│   │    ## Submission                                          │   │
│   │    When you've completed your work, you MUST submit...    │   │
│   │    Step 1: Create the patch file                          │   │
│   │    Run `git diff -- path/to/file1 path/to/file2 >...     │   │
│   │    Step 2: Verify your patch                              │   │
│   │    Step 3: Submit (EXACT command required)                │   │
│   │    echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat...   │   │
│   │    </instructions>"                                       │   │
│   │                                                            │   │
│   │   tiktoken: 967 tokens                                    │   │
│   └──────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│ 【C】Tools 参数 — BASH_TOOL 定义（不在 messages 中，通过 API     │
│       的 tools 参数传递）                                        │
│                                                                    │
│   {                                                                │
│     "type": "function",                                            │
│     "function": {                                                  │
│       "name": "bash",                                              │
│       "description": "Execute a bash command",                     │
│       "parameters": {                                              │
│         "type": "object",                                          │
│         "properties": {                                            │
│           "command": {                                             │
│             "type": "string",                                      │
│             "description": "The bash command to run."              │
│           }                                                        │
│         },                                                         │
│         "required": ["command"]                                    │
│       }                                                            │
│     }                                                              │
│   }                                                                │
│                                                                    │
│   tiktoken: 63 tokens                                             │
├──────────────────────────────────────────────────────────────────┤
│ 【D】API 格式开销（不可直接观测，由 API 端编码产生）               │
│                                                                    │
│   包括：role 标签、消息分隔符、tool schema 编码、                   │
│         message 格式化、special tokens 等                          │
│                                                                    │
│   估算: ~245 tokens                                               │
│   (API prompt_tokens 1,623 - tiktoken 可测量内容 1,378 = 245)     │
└──────────────────────────────────────────────────────────────────┘

Turn 0 合计: 1,623 tokens (API 精确值)
```

### 2.2 各部分的来源

| 部分 | 来源 | 如何确定 |
|------|------|---------|
| 【A】System Message | `swebench.yaml` 的 `system_template` 字段 | 固定字符串，所有 session 相同 |
| 【B1】静态前缀 | `swebench.yaml` 的 `instance_template` 中 `{{task}}` 之前的部分 | 模板固定文本 |
| 【B2】动态部分 | 数据集中每条 instance 的 `problem_statement` 字段，填入 `{{task}}` | 每个 instance 不同 |
| 【B3】静态后缀 | `swebench.yaml` 的 `instance_template` 中 `{{task}}` 之后的部分 | 模板固定文本 |
| 【C】BASH_TOOL | `actions_toolcall.py` 中的 `BASH_TOOL` 常量 | 代码中硬编码，所有 session 相同 |
| 【D】API 格式开销 | OpenAI 兼容 API 端对 messages + tools 的编码 | 不可直接观测，通过差额估算 |

### 2.3 各部分是否跨 Session 相同

| 部分 | 跨 Session 是否相同 | 原因 |
|------|-------------------|------|
| 【A】System Message | ✅ 完全相同 | 由同一个 `system_template` 渲染 |
| 【B1】静态前缀 | ✅ 完全相同 | 由同一个 `instance_template` 的固定文本渲染 |
| 【B2】动态部分 | ❌ 每个 instance 不同 | 来自 `problem_statement`，每个 issue 描述不同 |
| 【B3】静态后缀 | ✅ 完全相同 | 由同一个 `instance_template` 的固定文本渲染 |
| 【C】BASH_TOOL | ✅ 完全相同 | 代码中硬编码 |
| 【D】API 格式开销 | ✅ 完全相同 | 相同的消息结构 + tools 参数 |

### 2.4 各部分在 Prompt 中的位置关系

```
Token 位置:    0                              27          27+322=349                   349+967=1316    1316+63=1379    1379+245=1624
               │                              │                │                            │               │               │
               ▼                              ▼                ▼                            ▼               ▼               ▼
           ┌───────┐  ┌─────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────┐  ┌──────────┐
Turn 0:    │  【A】 │  │  【B1】  │  │      【B2】       │  │      【B3】       │  │   【C】   │  │   【D】   │
           │System │  │静态前缀  │  │  problem_        │  │  静态后缀         │  │BASH_TOOL │  │格式开销  │
           │       │  │         │  │  statement       │  │  (instructions)  │  │          │  │          │
           │ 17 tk │  │ 10 tk   │  │  322 tk          │  │  967 tk          │  │  63 tk   │  │ 245 tk   │
           └───────┘  └─────────┘  └──────────────────┘  └──────────────────┘  └──────────┘  └──────────┘
           ├──────── 相同 ────────┤├──── 每个 session ────┤├──────── 相同 ────────────────────┤├──── 相同 ────┤
           └──────── 不同 ────────┘

"相同" = 所有 300 条 session 内容一致
"不同" = 每个 session 内容不同
```

---

## 3. Turn 1：第二次请求的 Prompt

Turn 1 在 Turn 0 的基础上追加了 Turn 0 的交互结果。

### 3.1 完整结构

```
┌──────────────────────────────────────────────────────────────────┐
│ 【A】System Message                     （与 Turn 0 完全相同）     │
│ 【B】User Message — Instance Template   （与 Turn 0 完全相同）     │
│ 【C】BASH_TOOL 定义                     （与 Turn 0 完全相同）     │
│ 【D】API 格式开销                        （与 Turn 0 完全相同）     │
├──────────────────────────────────────────────────────────────────┤
│ 【E】Turn 0 的 Assistant 回复（新增）                              │
│                                                                    │
│   content:                                                         │
│     "Let me start by understanding the issue and finding the       │
│      relevant source code."                                        │
│                                                                    │
│   tool_calls:                                                      │
│     [{"type": "function", "function": {                            │
│       "name": "bash",                                              │
│       "arguments": "{\"command\": \"cd /testbed && find .          │
│        -path \\\"*/separable.py\\\" ...\"}"                        │
│     }}]                                                            │
│                                                                    │
│   tiktoken: 107 tokens (content + tool_calls 合计)                │
├──────────────────────────────────────────────────────────────────┤
│ 【F】Turn 0 的 Tool 输出 / Observation（新增）                    │
│                                                                    │
│   "<exception>An error occurred while executing the command:       │
│    [Errno 2] No such file or directory: '/testbed'                 │
│    </exception>                                                    │
│    <returncode>-1</returncode>                                     │
│    <output>                                                        │
│    </output>"                                                      │
│                                                                    │
│   tiktoken: 43 tokens                                             │
└──────────────────────────────────────────────────────────────────┘

Turn 1 合计: 1,768 tokens (API 精确值)
新增: 145 tokens (【E】+【F】)
```

### 3.2 新增部分的来源

| 部分 | 来源 | 是否跨 Session 相同 |
|------|------|-------------------|
| 【E】Assistant 回复 | LLM 生成的推理文本 + 工具调用 JSON | ❌ 每次不同 |
| 【F】Tool 输出 | 命令执行结果，经 `observation_template` 渲染 | ❌ 每次不同 |

### 3.3 Observation 的渲染格式

Tool 输出由 `swebench.yaml` 的 `observation_template` 渲染，格式如下：

**正常输出**（output < 10000 chars）：
```
<returncode>0</returncode>
<output>
命令的标准输出内容...
</output>
```

**异常输出**：
```
<exception>错误信息</exception>
<returncode>1</returncode>
<output>
</output>
```

**超长输出**（output >= 10000 chars）：
```
<returncode>0</returncode>
<warning>
The output of your last command was too long.
Please try a different command that produces less output.
</warning>
<elided_chars>
12345 characters elided
</elided_chars>
<output_head>
前 5000 字符...
</output_head>
<output_tail>
后 5000 字符...
</output_tail>
```

---

## 4. Turn N：后续请求的 Prompt

Turn N 的 prompt = Turn 0 的初始化内容 + Turn 0 ~ N-1 的所有交互历史。

### 4.1 结构

```
┌──────────────────────────────────────────────────────────────────┐
│ 【A】System Message                     （始终相同）               │
│ 【B】User Message — Instance Template   （始终相同）               │
│ 【C】BASH_TOOL 定义                     （始终相同）               │
│ 【D】API 格式开销                        （始终相同）               │
├──────────────────────────────────────────────────────────────────┤
│ Turn 0:  【E0】Assistant 回复 + 【F0】Observation                │
│ Turn 1:  【E1】Assistant 回复 + 【F1】Observation                │
│ Turn 2:  【E2】Assistant 回复 + 【F2】Observation                │
│   ...                                                             │
│ Turn N-1:【E_{N-1}】Assistant 回复 + 【F_{N-1}】Observation     │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 实测数据：`astropy__astropy-12907` 的完整 10 Turns

| Turn | API Prompt Tokens | 新增 Tokens | 新增内容 |
|------|------------------|------------|---------|
| 0 | 1,623 | 1,623 | 【A】【B】【C】【D】初始化 |
| 1 | 1,768 | 145 | 【E0】assistant 回复 + 【F0】observation |
| 2 | 1,867 | 99 | 【E1】assistant 回复 + 【F1】observation |
| 3 | 1,970 | 103 | 【E2】assistant 回复 + 【F2】observation |
| 4 | 2,068 | 98 | 【E3】assistant 回复 + 【F3】observation |
| 5 | 2,168 | 100 | 【E4】assistant 回复 + 【F4】observation |
| 6 | 2,284 | 116 | 【E5】assistant 回复 + 【F5】observation |
| 7 | 2,400 | 116 | 【E6】assistant 回复 + 【F6】observation |
| 8 | 2,503 | 103 | 【E7】assistant 回复 + 【F7】observation |
| 9 | 2,628 | 125 | 【E8】assistant 回复 + 【F8】observation |

- 初始化部分（Turn 0）：1,623 tokens
- 每轮增量：99 ~ 145 tokens（assistant 回复 + observation）
- Prompt 随 turn 数**单调递增**，增量大小取决于 assistant 回复长度和命令输出长度

---

## 5. 跨 Session 对比：相同与不同

### 5.1 三条不同 Session 的 Turn 0 对比

| 组件 | astropy-12907 | astropy-14182 | astropy-6938 |
|------|--------------|--------------|-------------|
| 【A】System Message | `You are a helpful assistant...` | `You are a helpful assistant...` | `You are a helpful assistant...` |
| 【B1】静态前缀 | `<pr_description>\nConsider...` | `<pr_description>\nConsider...` | `<pr_description>\nConsider...` |
| **【B2】动态部分** | **Modeling's `separability_...`** (322 tk) | **Please support header rows...** (508 tk) | **Possible bug in io.fits...** (118 tk) |
| 【B3】静态后缀 | `</pr_description>\n<instructions>...` | `</pr_description>\n<instructions>...` | `</pr_description>\n<instructions>...` |
| 【C】BASH_TOOL | 同 | 同 | 同 |
| API prompt_tokens | 1,623 | 1,910 | 1,430 |

- 【A】【B1】【B3】【C】在所有 session 中**逐字符相同**
- 【B2】是唯一不同的部分，长度差异导致首 turn prompt_tokens 从 1,430 到 1,910 不等

### 5.2 同 Repo 内的 Task 差异

对 SWE-bench_Lite 全部 300 条 instance 的分析：

| Repo | Issue 数 | Task 平均 Token 数 | Task 间最长公共前缀 | 含 Traceback 比例 |
|------|---------|-------------------|-------------------|------------------|
| django/django | 114 | 332 | 0 tokens | 16% |
| sympy/sympy | 77 | 331 | 0 tokens | 18% |
| matplotlib/matplotlib | 23 | 753 | 0 tokens | 35% |
| scikit-learn/scikit-learn | 23 | 538 | 0 tokens | 17% |
| pytest-dev/pytest | 17 | 852 | 0 tokens | 6% |
| sphinx-doc/sphinx | 16 | 264 | 0 tokens | 0% |
| astropy/astropy | 6 | 449 | 0 tokens | 33% |
| 其余 5 个 repo | 24 | 224 ~ 1693 | 0 tokens | 0 ~ 50% |

- **所有 repo 内，不同 issue 的 problem_statement 从第一个词就不同**，没有公共前缀
- 同 repo 内存在零散的共同片段（如 Traceback header、import 语句），但不形成连续前缀

---

## 6. 对应的 API 调用格式

以上 prompt 结构对应发送给 OpenAI 兼容 API 的实际请求格式：

```json
{
  "model": "xopdeepseekv4flash",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant that can interact with a computer shell to solve programming tasks."
    },
    {
      "role": "user",
      "content": "<pr_description>\nConsider the following PR description:\nModeling's `separability_matrix`...\n</pr_description>\n\n<instructions>\n...\n</instructions>"
    },
    // Turn 0 之后追加:
    {
      "role": "assistant",
      "content": "Let me start by understanding the issue...",
      "tool_calls": [{"type": "function", "id": "call_xxx", "function": {"name": "bash", "arguments": "{\"command\": \"...\""}}}]
    },
    {
      "role": "tool",
      "tool_call_id": "call_xxx",
      "content": "<exception>...</exception>\n<returncode>-1</returncode>\n<output>\n</output>"
    }
    // 后续 turn 继续追加 assistant + tool 对
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "bash",
        "description": "Execute a bash command",
        "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "The bash command to run."}}, "required": ["command"]}
      }
    }
  ]
}
```

注意：`.traj.json` 中的 messages 比 API 请求多了 `extra` 字段（包含 usage、timestamp 等），发送 API 时会自动剥离。
