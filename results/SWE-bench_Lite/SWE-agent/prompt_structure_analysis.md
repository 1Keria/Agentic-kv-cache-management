# SWE-Agent Prompt 组织结构与跨 Session 共享前缀分析

> 基于 SWE-agent + SWE-bench 配置（07.yaml / default.yaml）
> 最后更新：2026-06-10

---

## 1. 框架概述

SWE-agent 是 Princeton NLP 开发的 SWE-bench agent 框架，与 mini-swe-agent 的核心差异：

| 维度 | mini-swe-agent | SWE-agent |
|------|---------------|-----------|
| 工具数量 | 1 个 (bash) | 3-10 个（视配置） |
| 工具传递方式 | API `tools` 参数 | 07.yaml: 嵌入 system prompt; default.yaml: API `tools` 参数 |
| Demonstration | 无 | 07.yaml 有一条完整示例轨迹 |
| System prompt 长度 | 17 tokens | 07.yaml: 939 tokens; default.yaml: 15 tokens |
| 解析模式 | function_calling | 07.yaml: thought_action; default.yaml: function_calling |

---

## 2. SWE-Agent (07.yaml) 的 Prompt 结构

07.yaml 是 SWE-agent 论文中的原始配置，共享前缀最长。

### 2.1 Turn 0 完整结构

```
┌──────────────────────────────────────────────────────────────────┐
│ 【A】System Message                                               │
│                                                                    │
│   SETTING: You are an autonomous programmer, and you're working    │
│   directly in the command line with a special interface.           │
│                                                                    │
│   The special interface consists of a file editor that shows you   │
│   100 lines of a file at a time. In addition to typical bash       │
│   commands, you can also use the following commands:               │
│                                                                    │
│   COMMANDS:                                                        │
│   goto:                                                            │
│     docstring: moves the window to show <line_number>             │
│     signature: goto <line_number>                                  │
│     arguments:                                                     │
│     - line_number (integer) [required]                             │
│   open:                                                            │
│     docstring: opens the file at the given path in the editor      │
│     signature: open <path> [<line_number>]                         │
│     arguments:                                                     │
│     - path (string) [required]                                     │
│   create:                                                          │
│     docstring: creates and opens a new file with the given name    │
│     signature: create <filename>                                   │
│   scroll_up:                                                       │
│     docstring: moves the window up 100 lines                      │
│   scroll_down:                                                     │
│     docstring: moves the window down 100 lines                    │
│   find_file:                                                       │
│     docstring: finds all files with the given name or pattern      │
│   search_dir:                                                      │
│     docstring: searches for search_term in all files in dir        │
│   search_file:                                                     │
│     docstring: searches for search_term in the specified file      │
│   edit:                                                            │
│     docstring: replaces lines <start_line> through <end_line>      │
│   submit:                                                          │
│     docstring: submits your current code                           │
│                                                                    │
│   Please note that THE EDIT COMMAND REQUIRES PROPER INDENTATION.  │
│   If you'd like to add the line '        print(x)' you must       │
│   fully write that out, with all those spaces before the code!     │
│                                                                    │
│   RESPONSE FORMAT:                                                 │
│   Your shell prompt is formatted as follows:                       │
│   (Open file: <path>) <cwd> $                                     │
│                                                                    │
│   You need to format your output using two fields;                 │
│   discussion and command.                                          │
│   Your output should always include _one_ discussion and _one_     │
│   command field EXACTLY as in the following example:               │
│   DISCUSSION                                                      │
│   First I'll start by using ls to see what files are in the        │
│   current directory.                                               │
│   ```                                                              │
│   ls -a                                                            │
│   ```                                                              │
│                                                                    │
│   You should only include a *SINGLE* command in the command        │
│   section and then wait for a response from the shell before       │
│   continuing with more discussion and commands.                    │
│   You're free to use any other bash commands you want.             │
│   However, the environment does NOT support interactive session     │
│   commands (e.g. python, vim).                                     │
│                                                                    │
│   tiktoken: 939 tokens                                             │
├──────────────────────────────────────────────────────────────────┤
│ 【B】Demonstration Message (user role)                             │
│                                                                    │
│   Here is a demonstration of how to correctly accomplish this      │
│   task. It is included to show you how to correctly use the        │
│   interface. You do not need to follow exactly what is done in     │
│   the demonstration.                                               │
│   --- DEMONSTRATION ---                                            │
│                                                                    │
│   (完整的 marshmallow-code/marshmallow-1867 问题解决轨迹)          │
│   包含多轮 DISCUSSION + command 对，展示如何：                     │
│   - 使用 find_file, search_dir, search_file 定位代码              │
│   - 使用 open, goto, scroll_down 阅读代码                         │
│   - 使用 edit 修改代码                                            │
│   - 使用 submit 提交                                              │
│                                                                    │
│   --- END OF DEMONSTRATION ---                                     │
│                                                                    │
│   tiktoken: 5,572 tokens                                           │
├──────────────────────────────────────────────────────────────────┤
│ 【C】User Message — Instance Template                              │
│                                                                    │
│   【C1】静态前缀                                                    │
│     "We're currently solving the following issue within our        │
│      repository. Here's the issue text:\nISSUE:\n"                 │
│     tiktoken: 20 tokens                                            │
│                                                                    │
│   ┌──────────────────────────────────────────────────────────┐   │
│   │【C2】动态部分 — problem_statement（每个 instance 不同）    │   │
│   │                                                            │   │
│   │  每个 issue 描述不同，长度差异大                            │   │
│   │  tiktoken: 118 ~ 737 tokens                               │   │
│   └──────────────────────────────────────────────────────────┘   │
│                                                                    │
│   【C3】静态后缀                                                    │
│     INSTRUCTIONS:                                                  │
│     Now, you're going to solve this issue on your own...          │
│     Remember, YOU CAN ONLY ENTER ONE COMMAND AT A TIME.           │
│     When you're satisfied, you can submit your changes...         │
│                                                                    │
│     NOTE ABOUT THE EDIT COMMAND: Indentation really matters!      │
│                                                                    │
│     IMPORTANT TIPS:                                                │
│     1. Always start by trying to replicate the bug...             │
│     2. If you run a command and it doesn't work, try another...   │
│     3. If you open a file and need to get to a specific line...   │
│     4. If the bug reproduction script requires inputting/reading   │
│        a specific file, conduct a search...                       │
│     5. Always make sure to look at the currently open file...     │
│     6. When editing files, always check the code after edit...    │
│                                                                    │
│     (Open file: n/a)                                              │
│     (Current directory: /testbed)                                  │
│     bash-$                                                         │
│                                                                    │
│     tiktoken: 646 tokens                                           │
├──────────────────────────────────────────────────────────────────┤
│ 无 Tool Schemas — 07.yaml 使用 thought_action 模式，              │
│ 工具文档已嵌入 System Message 的 COMMANDS 段                      │
└──────────────────────────────────────────────────────────────────┘

Turn 0 合计: ~7,600 tokens (估算)
```

### 2.2 各部分是否跨 Session 相同

| 部分 | 跨 Session 是否相同 | 原因 |
|------|-------------------|------|
| 【A】System Message (含 command_docs) | ✅ 完全相同 | 同一配置渲染，command_docs 由固定工具列表生成 |
| 【B】Demonstration | ✅ 完全相同 | 使用同一条示例轨迹 |
| 【C1】Instance 静态前缀 | ✅ 完全相同 | 模板固定文本 |
| **【C2】Instance 动态部分** | **❌ 每个 instance 不同** | 来自 problem_statement |
| 【C3】Instance 静态后缀 | ⚠️ 内容相同，但被 C2 阻断 | 模板固定文本，但位置不连续 |

### 2.3 跨 Session 共享前缀

```
Token 位置:  0            939            6511           6531       6531+322=6853    6853+646=7499
             │             │               │               │              │               │
             ▼             ▼               ▼               ▼              ▼               ▼
         ┌────────┐  ┌────────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────┐
Turn 0:  │  【A】  │  │    【B】    │  │   【C1】   │  │   【C2】  │  │    【C3】    │  │  API开销  │
         │System  │  │Demo轨迹    │  │静态前缀    │  │problem_ │  │静态后缀      │  │          │
         │+工具文档│  │            │  │"ISSUE:"   │  │statement │  │INSTRUCTIONS  │  │          │
         │939 tk  │  │5,572 tk    │  │20 tk      │  │118-737 tk│  │+TIPS 646 tk │  │  ~245 tk │
         └────────┘  └────────────┘  └───────────┘  └──────────┘  └──────────────┘  └──────────┘
         ├──────────────────── 相同 ────────────────────┤├── 不同 ──┤├── 相同(阻断) ──┤├── 相同 ──┤

连续共享前缀: 【A】+【B】+【C1】= 939 + 5,572 + 20 = 6,531 tokens
```

---

## 3. SWE-Agent (default.yaml) 的 Prompt 结构

default.yaml 是较新的配置，使用 function_calling 模式。

### 3.1 Turn 0 完整结构

```
┌──────────────────────────────────────────────────────────────────┐
│ 【A】System Message                                               │
│   "You are a helpful assistant that can interact with a           │
│    computer to solve tasks."                                      │
│   tiktoken: 15 tokens                                             │
├──────────────────────────────────────────────────────────────────┤
│ 【B】User Message — Instance Template                              │
│                                                                    │
│   【B1】静态前缀                                                    │
│     "<uploaded_files>                                             │
│      /testbed                                                     │
│      </uploaded_files>                                            │
│      I've uploaded a python code repository in the directory      │
│      /testbed. Consider the following PR description:             │
│                                                                    │
│      <pr_description>                                             │
│      "                                                            │
│     tiktoken: 35 tokens                                            │
│                                                                    │
│   【B2】动态部分 (problem_statement)                               │
│     tiktoken: 118 ~ 737 tokens                                     │
│                                                                    │
│   【B3】静态后缀                                                    │
│     "</pr_description>                                            │
│                                                                    │
│      Can you help me implement the necessary changes to the       │
│      repository so that the requirements specified in the          │
│      <pr_description> are met?                                    │
│      I've already taken care of all changes to any of the test    │
│      files described in the <pr_description>. This means you      │
│      DON'T have to modify the testing logic or any of the tests!  │
│      Your task is to make the minimal changes to non-tests files  │
│      in the /testbed directory to ensure the <pr_description>     │
│      is satisfied.                                                │
│      Follow these steps to resolve the issue:                     │
│      1. As a first step, it might be a good idea to find and      │
│         read code relevant to the <pr_description>                │
│      2. Create a script to reproduce the error and execute it     │
│         with `python <filename.py>` using the bash tool           │
│      3. Edit the sourcecode of the repo to resolve the issue      │
│      4. Rerun your reproduce script and confirm that the error    │
│         is fixed!                                                 │
│      5. Think about edgecases and make sure your fix handles      │
│         them as well                                              │
│      Your thinking should be thorough and so it's fine if it's    │
│      very long.                                                   │
│     tiktoken: 223 tokens                                           │
├──────────────────────────────────────────────────────────────────┤
│ 【C】Tool Schemas (3 个工具，通过 API tools 参数传递)             │
│                                                                    │
│   bash:                                                            │
│     name: "bash"                                                  │
│     description: "runs the given command directly in bash"        │
│     arguments: command (string, required)                         │
│     ~50 tokens                                                     │
│                                                                    │
│   str_replace_editor:                                              │
│     name: "str_replace_editor"                                    │
│     description: "Custom editing tool for viewing, creating and   │
│                   editing files. Supports view, create,           │
│                   str_replace, insert, undo_edit commands."       │
│     arguments: command (enum: 5种), path, file_text, old_str,    │
│                new_str, insert_line, view_range                   │
│     ~350 tokens                                                    │
│                                                                    │
│   submit:                                                          │
│     name: "submit"                                                │
│     description: "submits the current file"                       │
│     ~30 tokens                                                     │
│                                                                    │
│   合计: ~430 tokens                                               │
├──────────────────────────────────────────────────────────────────┤
│ 【D】API 格式开销                                                  │
│   估算: ~245 tokens                                               │
└──────────────────────────────────────────────────────────────────┘

Turn 0 合计: ~1,100 tokens (估算)
```

### 3.2 各部分是否跨 Session 相同

| 部分 | 跨 Session 是否相同 | 原因 |
|------|-------------------|------|
| 【A】System Message | ✅ 完全相同 | 同一配置 |
| 【B1】Instance 静态前缀 | ✅ 完全相同 | 模板固定文本（working_dir 所有 instance 相同） |
| **【B2】Instance 动态部分** | **❌ 每个 instance 不同** | 来自 problem_statement |
| 【B3】Instance 静态后缀 | ⚠️ 内容相同，但被 B2 阻断 | 模板固定文本 |
| 【C】Tool Schemas | ⚠️ 内容相同，但被 B2 阻断 | 工具列表固定，但位置不连续 |
| 【D】API 格式开销 | ✅ 完全相同 | 相同的消息结构 |

### 3.3 跨 Session 共享前缀

```
连续共享前缀: 【A】+【B1】= 15 + 35 = 50 tokens
被阻断的相同内容: 【B3】+【C】+【D】= 223 + 430 + 245 = 898 tokens
```

---

## 4. 三种配置的共享前缀对比

| 配置 | 连续共享前缀 | 被阻断的相同内容 | 首 turn 估算 | 共享前缀占比 |
|------|------------|----------------|------------|------------|
| **mini-swe-agent (swebench.yaml)** | 27 tokens | 1,030 tokens | ~1,623 | **1.7%** |
| **SWE-agent (default.yaml)** | 50 tokens | 898 tokens | ~1,100 | **4.5%** |
| **SWE-agent (07.yaml)** | **6,531 tokens** | 646 tokens | ~7,600 | **85.9%** |

### 07.yaml 共享前缀长的三个原因

1. **工具文档在 System Message 中**（939 tokens）
   - 07.yaml 使用 `thought_action` 解析模式，10 个工具的完整文档以纯文本嵌入 system prompt
   - 这些工具文档在所有 session 中完全相同，且位于 prompt 最前面
   - 对比：default.yaml 和 mini-swe-agent 把工具作为 API `tools` 参数传递，虽然内容相同但**被 problem_statement 阻断**，无法形成连续前缀

2. **Demonstration 在 Instance 之前**（5,572 tokens）
   - 一条完整的 marshmallow-1867 问题解决轨迹，作为 user message 插在 system 和 instance 之间
   - 所有 session 共享同一条 demonstration
   - 这是共享前缀中**最大的一块**，占共享前缀的 85%

3. **problem_statement 出现得晚**
   - 直到第 6,531 个 token 才出现动态内容
   - 前面 6,531 tokens 全部是跨 session 完全相同的静态内容

---

## 5. 07.yaml 与 mini-swe-agent 的 Prompt 组织差异根源

| 差异 | mini-swe-agent | SWE-agent 07.yaml | 对共享前缀的影响 |
|------|---------------|-------------------|----------------|
| 工具传递方式 | API `tools` 参数 | 嵌入 system prompt 文本 | tools 参数在 API 层与 messages 分离，被 problem_statement 阻断；嵌入 system prompt 则形成连续前缀 |
| 工具数量 | 1 个 (bash) | 10 个 (goto, open, create, scroll_up/down, find_file, search_dir, search_file, edit, submit) | 更多工具 = 更长的工具文档 = 更长的共享前缀 |
| 是否有 Demonstration | 无 | 有一条完整轨迹 (5,572 tokens) | demonstration 是共享前缀的最大贡献者 |
| 解析模式 | function_calling | thought_action | thought_action 模式强制将工具文档放入 system prompt，间接增加了共享前缀 |

---

## 6. 后续计划

- [ ] 用 07.yaml 配置实际运行 SWE-bench_Lite，采集 trajectory 数据
- [ ] 实测 07.yaml 下首 turn 的 API prompt_tokens，验证共享前缀占比
- [ ] 分析 07.yaml 下 session 内复用率（观察增量 token 模式）
- [ ] 分析 observation 模板对 token 增量的影响（07.yaml 的 next_step_template 含状态变量）
