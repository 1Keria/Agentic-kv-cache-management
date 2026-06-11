# OpenAI Codex CLI 跨 Session KV Cache 复用 — Trace Study 实验方案

> 最后更新：2026-06-11
> 关联文档：[04_agent_framework_comparison.md](docs/04_agent_framework_comparison.md)
> 关联文档：[05_claude_code_prompt_structure.md](docs/05_claude_code_prompt_structure.md)
> 源码基础：`Agent/codex/codex-rs/`（Rust workspace，90+ sub-crates）

---

## 1. 研究背景

### 1.1 问题

在 agent 推理场景下，多个 agent session 共享大量 prompt 前缀（base instructions、tool schemas、AGENTS.md 等），但现有 serving 框架只支持 session 内跨 turn 的 KV Cache 复用，无法跨 session 复用。

### 1.2 前置分析结论

对四个 agent 框架的 prompt 结构分析表明：

| 框架 | 共享前缀 | 树状结构 | 分支来源 |
|------|---------|---------|---------|
| mini-swe-agent | 27 tokens | ❌ 扁平 | 无 |
| SWE-agent (07.yaml) | 6,531 tokens | ❌ 扁平 | 无 |
| Codex CLI | 4,395 tokens | ✅ 树状 | AGENTS.md (按项目) |
| Claude Code | 12,000-30,000 tokens | ✅ 树状 | CLAUDE.md (按项目) |

Codex CLI 的树状结构来自项目级 AGENTS.md 注入：不同项目的 session 共享 L0（base instructions + tool schemas），同项目的 session 额外共享 L1（项目级 AGENTS.md + skills + plugins）。

### 1.3 本实验目标

用 Codex CLI 作为实验载体，通过 trace study 量化：
1. 树状跨 session KV Cache 复用的特征（L0/L1 前缀长度、缓存命中率）
2. 跨 session 复用的收益（节省的 prefill 计算量和费用）
3. AGENTS.md 大小对收益的影响（消融实验）
4. 与扁平架构的对比

---

## 2. Codex CLI Prompt 组织结构

### 2.1 基本概念

Codex CLI 的一次 **session** = 从 `codex` 启动（或 `--resume`）到退出之间的完整对话。

与 Claude Code 类似，Codex CLI 的「一轮」需要区分两个层次：

| 层次 | 含义 | 典型内容 |
|------|------|---------|
| **User Turn** | 用户发送一条消息后，Codex 完成整段 agentic loop | 1 条 user 文本 + 多步 tool 循环 + 最终 assistant 文本 |
| **API Turn** | 每次调用 OpenAI Responses API | 完整 history + 本轮新增消息；KV cache 在 API Turn 粒度复用 |
| **Tool Step** | agentic loop 内的一步 | `assistant[tool_use]` → `user[tool_result]` |

一次 User Turn 通常包含 **多个 API Turn**（Codex 可能连续调用 shell_command、apply_patch 等工具，每步都是一次 API 调用）。

### 2.2 与 SWE-bench Agent 的关键差异

| 维度 | mini-swe-agent | SWE-agent | Codex CLI |
|------|---------------|-----------|-----------|
| Prompt 模板 | YAML 固定模板 | YAML + Jinja | 多层 system 动态拼接 |
| 工具传递 | API `tools` 参数 | 07.yaml 嵌入 system | API `tools` 参数（Responses API） |
| 项目上下文 | 无 | 无 | AGENTS.md + skills + plugins |
| 每步 observation | `observation_template` 渲染 | Jinja 模板 | 原生 `tool_result` content |
| 源码可见性 | 完全开源 | 完全开源 | **完全开源（Rust）** |

> **重要**：Codex CLI 的 prompt 组装逻辑完全在开源 Rust 代码中，可以直接审计。核心文件：`codex-rs/core/src/session/mod.rs`（`build_initial_context`）、`codex-rs/core/src/session/turn.rs`（`build_prompt`）、`codex-rs/core/src/agents_md.rs`（AGENTS.md 加载）。

---

## 3. 整体 Prompt 架构（分层）

Codex CLI 的每次 API 请求由 **Instructions（base）+ Developer Message + Contextual User Message + Tools** 四部分组成，通过 OpenAI Responses API 发送：

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 【I】Base Instructions — 对应 Responses API 的 `instructions` 参数       │
│                                                                           │
│   来源: codex-rs/protocol/src/prompts/base_instructions/default.md        │
│                                                                           │
│   "You are a coding agent running in the Codex CLI,                      │
│    a terminal-based coding assistant."                                    │
│                                                                           │
│   包含: 身份、AGENTS.md 规范、preamble message 示例、                     │
│         planning 用法、task 执行规则（apply_patch only,                   │
│         no git commit, no one-letter vars, no inline citations）、         │
│         validation 规则、ambition vs precision 指导、                     │
│         progress update 规则、final answer 格式（section headers,         │
│         bullets, monospace, file references, tone）、                      │
│         tool guidelines（shell commands, update_plan）、                   │
│         sandbox/approval mode 行为                                        │
│                                                                           │
│   估计: ~4,395 tokens                                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ 【D】Developer Message — 聚合多个 ContextualUserFragment                  │
│                                                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ 【D1】Model switch 指令                                         │   │  ← 首turn 为空，模型切换时注入
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【D2】Permissions 指令                                          │   │  ← 按配置不同 ★
│   │   <permissions instructions>                                     │   │
│   │     sandbox_mode + network_access + approval_policy              │   │
│   │     + writable_roots + denied_reads                              │   │
│   │   </permissions instructions>                                    │   │
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【D3】Developer instructions (--developer-instructions)          │   │  ← 按用户指定不同 ★
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【D4】Collaboration mode 指令                                    │   │  ← 按 mode 不同
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【D5】Realtime 指令                                              │   │  ← 仅 realtime 模式
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【D6】Personality 指令                                           │   │  ← 模型未内置 personality 时注入
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【D7】Apps/Connectors 指令                                      │   │  ← 按 MCP apps 配置不同
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【D8】Skills 摘要                                                │   │  ← 按项目配置不同 ★
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【D9】Plugins 摘要                                               │   │  ← 按项目配置不同 ★
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【D10】Extension contributor fragments                           │   │  ← 按扩展不同
│   └─────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────┤
│ 【U】Contextual User Message — 聚合用户/环境侧上下文                     │
│                                                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ 【U1】AGENTS.md 指令                                            │   │  ← 按项目目录不同 ★
│   │   "# AGENTS.md instructions for <directory>"                     │   │
│   │   "<INSTRUCTIONS>"                                               │   │
│   │   AGENTS.md 内容（walk-up discovery）                             │   │
│   │   "</INSTRUCTIONS>"                                              │   │
│   ├─────────────────────────────────────────────────────────────────┤   │
│   │ 【U2】Environment context                                       │   │  ← 按 session 不同
│   │   <environment_context>                                          │   │
│   │     <cwd>...</cwd>                                               │   │
│   │     <shell>...</shell>                                           │   │
│   │     <current_date>...</current_date>                             │   │
│   │     <timezone>...</timezone>                                     │   │
│   │     <network ... />                                              │   │
│   │     <filesystem>...</filesystem>                                 │   │
│   │   </environment_context>                                         │   │
│   └─────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────┤
│ 【M】User Message — 用户实际输入                                          │
│   用户发送的文本 + 提及的 skill 注入 + attachment                        │
├─────────────────────────────────────────────────────────────────────────┤
│ 【T】Tools — API tools 参数（不在 messages 文本中）                      │
│   shell_command / exec_command + write_stdin +                           │
│   apply_patch (freeform) + update_plan +                                │
│   request_user_input + request_permissions +                            │
│   view_image + tool_search + web_search + image_generation +            │
│   multi-agent tools (spawn/wait/close/...) +                            │
│   MCP namespace tools + dynamic tools + extension tools                 │
│   估计: 2,000-5,000 tokens（取决于启用的工具集）                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.1 API 请求映射

Codex CLI 使用 **OpenAI Responses API**（非 Chat Completions API），请求结构：

```json
{
  "model": "codex-mini",
  "instructions": "【I】Base Instructions 文本",
  "input": [
    {"role": "developer", "content": "【D】聚合的 developer sections"},
    {"role": "user", "content": "【U】AGENTS.md + 环境上下文"},
    {"role": "user", "content": "【M】用户实际输入"},
    // 后续 turn 追加:
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "user", "content": "...", "tool_result": ...},
    ...
  ],
  "tools": [
    {"type": "function", "name": "shell_command", ...},
    {"type": "function", "name": "apply_patch", ...},   // 或 Freeform
    {"type": "function", "name": "update_plan", ...},
    ...
  ],
  "parallel_tool_calls": true
}
```

**关键**：`instructions` 参数对应 Responses API 的系统级指令，语义等同于 Chat API 的 `system` 消息，但在 Responses API 中作为顶级字段传递。

---

## 4. 各层详细分析

### 4.1 【I】Base Instructions（~4,395 tokens）

**来源**：`codex-rs/protocol/src/prompts/base_instructions/default.md`（276 行）

**解析优先级**（`spawn_internal` 中）：
```
1. config.base_instructions          （用户显式覆盖）
2. conversation_history              （resume 时从历史恢复）
3. model_info.get_model_instructions() （模型默认，通常即 default.md）
```

**内容组成**：

| 部分 | 行数 | 内容 |
|------|------|------|
| 身份 + 能力 | 1-9 | "You are a coding agent running in the Codex CLI..." |
| AGENTS.md 规范 | 16-27 | AGENTS.md 的发现、scope、precedence 规则 |
| Preamble messages | 29-49 | 工具调用前的简短说明，含 8 个示例 |
| Planning | 51-121 | update_plan 用法、高质量/低质量 plan 示例 |
| Task execution | 123-147 | apply_patch only、no git commit、代码规范 |
| Validation | 149-163 | 测试策略、lint/format 规则 |
| Ambition vs precision | 165-169 | 新任务 vs 现有代码的不同策略 |
| Progress updates | 171-179 | 长任务的进度汇报规范 |
| Final answer | 181-256 | 输出格式：headers, bullets, monospace, tone |
| Tool guidelines | 258-276 | shell（prefer rg）+ update_plan 用法 |

**跨 Session 相同性**：✅ 所有使用同一模型的 session 完全相同（除非用户通过 config 或 `--instructions` 覆盖）

### 4.2 【D】Developer Message

Developer message 是一个聚合的 `role=developer` 消息，由 `build_initial_context()` 中多个 section 拼接而成。各 section 的跨 session 稳定性：

| Section | 标记 | 跨 Session | 跨项目 | 树状分支来源 |
|---------|------|-----------|--------|-------------|
| Model switch | 【D1】 | ❌ 仅模型切换时 | ❌ | 无 |
| **Permissions** | **【D2】** | **按配置** | **按配置** | **sandbox_mode + approval_policy** |
| Developer instructions | 【D3】 | 按用户指定 | 按用户指定 | `--developer-instructions` |
| Collaboration mode | 【D4】 | 按配置 | 按配置 | mode 不同 |
| Realtime | 【D5】 | ❌ 仅 realtime | ❌ | 无 |
| Personality | 【D6】 | ✅ 相同 | ✅ 相同 | 无 |
| Apps/Connectors | 【D7】 | 按 MCP 配置 | 按 MCP 配置 | 不同 MCP apps |
| **Skills** | **【D8】** | **按项目** | **按项目** | **项目级 `.codex/skills/`** |
| **Plugins** | **【D9】** | **按项目** | **按项目** | **项目级 plugins 配置** |
| Extensions | 【D10】 | 按扩展 | 按扩展 | 扩展 contributor |

**Permissions 指令（【D2】）** 详细结构：

```
<permissions instructions>
  [sandbox_mode 模板]        ← 3 选 1: read_only / workspace_write / danger_full_access
  [approval_policy 模板]     ← 5 选 1: never / on_failure / on_request / on_request_rule_request_permission / unless_trusted
  [writable_roots]           ← workspace_write 时列出可写目录
  [denied_reads]             ← 列出禁止读取的路径/glob
</permissions instructions>
```

sandbox_mode 模板内容极短（1-2 句），approval_policy 模板长度差异大：
- `never`: 1 句（~15 tokens）
- `on_failure`: 1 句（~20 tokens）
- `unless_trusted`: 2 句（~30 tokens）
- `on_request`: ~58 行（~800 tokens）— 最长，含详细的 escalation 规则和示例

### 4.3 【U】Contextual User Message

**【U1】AGENTS.md 指令** — 树状分支的**主要来源**

AGENTS.md 发现逻辑（`agents_md.rs`）：

```
1. 从 CWD 向上 walk 到项目根（由 project_root_markers 决定，默认 .git）
2. 从项目根向下收集 AGENTS.md 文件到 CWD
3. 每个 directory 优先读 AGENTS.override.md，其次 AGENTS.md
4. 受 project_doc_max_bytes 预算约束（超出截断）
5. 全局指令从 CODEX_HOME 目录加载
```

渲染格式：
```
# AGENTS.md instructions for /path/to/project

<INSTRUCTIONS>
[全局 AGENTS.md 内容]

--- project-doc ---

[项目根 AGENTS.md 内容]
</INSTRUCTIONS>
```

**Provenance 追踪**：每个条目标记来源（User/Project/Internal），用于 scope 和 precedence 判断。

**【U2】Environment Context** — 按 session 不同

```xml
<environment_context>
  <cwd>/path/to/project</cwd>
  <shell>bash</shell>
  <current_date>2026-06-11</current_date>
  <timezone>America/New_York</timezone>
  <network enabled="true">
    <allowed>...</allowed>
    <denied>...</denied>
  </network>
  <filesystem>
    <workspace_roots><root>/path</root></workspace_roots>
    <permission_profile type="managed">...</permission_profile>
  </filesystem>
</environment_context>
```

### 4.4 【T】Tools

工具通过 `build_tool_router()` 组装，核心工具集：

| 工具 | 类型 | 名称 | 跨 Session | 说明 |
|------|------|------|-----------|------|
| shell_command | Function | `shell_command` | ✅ 相同 | command + workdir + timeout_ms + approval 参数 |
| exec_command | Function | `exec_command` | ✅ 相同 | unified exec 模式（含 environment_id） |
| write_stdin | Function | `write_stdin` | ✅ 相同 | 向运行中进程写 stdin |
| apply_patch | Freeform | `apply_patch` | ✅ 相同 | Lark 语法定义的 patch 格式 |
| update_plan | Function | `update_plan` | ✅ 相同 | 计划追踪与更新 |
| request_user_input | Function | `request_user_input` | ✅ 相同 | 请求用户输入 |
| request_permissions | Function | `request_permissions` | ⚠️ 按配置 | 请求额外权限 |
| view_image | Function | `view_image` | ✅ 相同 | 查看图片 |
| tool_search | ToolSearch | (deferred) | ✅ 相同 | 延迟加载 MCP 工具 |
| web_search | WebSearch | (hosted) | ✅ 相同 | 网络搜索 |
| image_generation | ImageGeneration | (hosted) | ✅ 相同 | 图片生成 |
| multi-agent | Function | spawn/wait/close/... | ✅ 相同 | 子 agent 管理 |
| MCP namespace | Namespace | 按配置 | ❌ 按项目 | MCP 服务器提供的工具 |
| dynamic | Function | 按定义 | ❌ 按配置 | 动态工具 |
| extension | Function | 按定义 | ❌ 按配置 | 扩展工具 |

**工具选择影响前缀**：
- **内置工具**（shell_command, apply_patch, update_plan 等）：所有 session 相同，属于 L0
- **MCP 工具**：按项目配置不同，形成 L1 分支或增加 L0
- **Dynamic/Extension 工具**：按配置不同

---

## 5. 跨 Session 共享前缀分析

### 5.1 前缀分解

```
┌─────────────────────────────────────────────────────────────────┐
│ 【I】Base Instructions (~4,395 tokens)                           │  ← L0：所有 session 共享
│   codex-rs/protocol/.../default.md                               │
├─────────────────────────────────────────────────────────────────┤
│ 【D】Developer Message                                           │
│   【D2】Permissions (按配置分支)                                  │  ← L1：同配置 session 共享
│   【D3】Developer instructions (按用户指定)                       │  ← L1
│   【D6】Personality (通常相同)                                    │  ← L0 或 L1
│   【D7】Apps/Connectors (按 MCP 配置)                            │  ← L1
│   【D8】Skills (按项目)                                          │  ← L1：★ 主要分支来源
│   【D9】Plugins (按项目)                                         │  ← L1：★ 主要分支来源
├─────────────────────────────────────────────────────────────────┤
│ 【U】Contextual User Message                                     │
│   【U1】AGENTS.md (按项目目录)                                   │  ← L1：★ 主要分支来源
│   【U2】Environment context (按 session)                          │  ← L2：每个 session 不同
├─────────────────────────────────────────────────────────────────┤
│ 【M】User Message                                                │  ← L2：每个 session 不同
├─────────────────────────────────────────────────────────────────┤
│ 【T】Tools                                                       │
│   内置工具 (所有 session 相同)                                    │  ← L0
│   MCP 工具 (按项目配置)                                          │  ← L1
│   Dynamic/Extension 工具 (按配置)                                │  ← L1
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 树状前缀结构

当 serving 系统同时处理多个项目的 Codex session 时：

```
                    根节点
                    【I】Base Instructions (~4,395 tokens)
                  + 【T】内置工具 schemas
                  + 【D6】Personality
                   /          |          \
              配置 A         配置 B       配置 C
              (workspace-   (read-only,  (danger-
               write,        on-failure)  full-access,
               on-request)               never)
              【D2】perms_A  【D2】perms_B  【D2】perms_C
             /      \         /     \        /     \
          项目 A1  项目 A2  项目 B1  B2   项目 C1  C2
          AGENTS_  AGENTS_  AGENTS_  ...  AGENTS_  ...
          md_A1    md_A2    md_B1        md_C1
          skills_  skills_  skills_      skills_
          A1       A2       B1           C1
         /  \     /  \     /  \        /  \
       s1  s2   s3  s4   s5  s6      s7  s8

KV Cache 复用:
  - 所有 session 复用: L0 = 【I】+ 内置【T】+ 【D6】(~4,395 + 工具 tokens)
  - 同配置 session 复用: L0 + L1_config = 上述 + 【D2】permissions
  - 同项目 session 复用: L0 + L1_config + L1_project = 上述 + AGENTS.md + skills + plugins
```

### 5.3 与 Claude Code 的对比

| 维度 | Codex CLI | Claude Code |
|------|----------|-------------|
| Base Instructions 位置 | Responses API `instructions` 参数 | API `system` 参数 |
| Developer message 位置 | `role=developer` 消息 | `role=developer` 消息（或 system 续） |
| 项目配置文件 | AGENTS.md | CLAUDE.md |
| 配置加载方式 | Walk-up from CWD to .git root | Walk-up from root to CWD |
| 工具 schema 大小 | ~2,000-5,000 tokens | ~20,000-30,000 tokens |
| Prompt caching | 无（OpenAI Responses API 暂无） | ✅ `cache_control: ephemeral` (5min/1h) |
| Context compaction | ✅（compact/prompt.md） | ✅（/compact） |
| 子 agent | ✅（multi-agent V1/V2） | ✅（Agent tool + Task*） |
| L0 前缀估计 | ~4,395 + 工具 tokens | ~2,000-3,000 + 工具 tokens |

---

## 6. 实验场景

### 场景 S1：单项目多 Session（基线 — 独立冷启动）

**目标**：测量单项目 session 的首 turn prefill 开销，建立基线

**设定**：
- 项目：`codex-repo`（Codex CLI 自身，有 AGENTS.md ~20KB，L1 较大）
- 任务：`"Find all Rust files that define tool schemas and list their names."`
- 模型：`codex-mini`（或 `gpt-4.1-mini`）
- 3 个独立 session，每个间隔 ≥ 5 分钟（避免任何隐式缓存）
- 每个 session：`codex -q --model codex-mini "TASK" 2>&1 | tee results/S1/session_$i.jsonl`

**预期结果**：

| Session | Turn | Prefill | 说明 |
|---------|------|---------|------|
| 1 | Turn 1 | L0+L1+L2 | 冷启动，完整 prefill |
| 1 | Turn 2+ | 增量 | session 内前缀命中（Responses API 隐式） |
| 2 | Turn 1 | L0+L1+L2 | 冷启动（无跨 session 缓存） |
| 2 | Turn 2+ | 增量 | session 内前缀命中 |

**量化指标**：首 turn prefill 开销占比、session 内增量 vs 总量

### 场景 S2：单项目多 Session（并发请求）

**目标**：量化并发请求场景下的 prefill 冗余（无跨 session 缓存时 N 个 session 各自独立 prefill L0+L1）

**设定**：
- 同 S1，但 3 个 session **同时启动**（并发）
- 用 `time` 记录总 wall-clock 时间

**预期结果**：

| 方案 | 首 turn prefill 总量 | 说明 |
|------|---------------------|------|
| 无跨 session 缓存 | 3 × (L0+L1+L2) | 每个 session 独立 prefill |
| 理想跨 session 缓存 | (L0+L1+L2) + 2 × L2 | 第一个 session prefill L0+L1，后续只 prefill L2 |

**量化指标**：prefill 冗余量 = (N-1) × (L0+L1)

### 场景 S3：多项目跨 Session（树状分支的核心验证）

**目标**：测量不同项目 session 之间的 L0 共享 vs L1 差异

**设定**：
- 项目 A：`mini-swe-agent`（无 AGENTS.md，L1 ≈ 0）
- 项目 B：`codex-repo`（有 AGENTS.md ~20KB + skills，L1 ≈ 2,000-3,000 tokens）
- 项目 C：`SWE-agent`（无 AGENTS.md，L1 ≈ 0）
- 先运行项目 A 的 session，紧接着运行项目 B 和 C 的 session
- 任务：`"List the main source files and describe the project structure."`

**预期结果**：

| Session | 首 turn prefill | 说明 |
|---------|----------------|------|
| A (mini-swe-agent) | L0 + L1_A(≈0) + L2_A | 冷启动 |
| B (codex-repo) | L0 + L1_B + L2_B | L0 与 A 相同，L1_B 不同 |
| C (SWE-agent) | L0 + L1_C(≈0) + L2_C | L0 与 A 相同，L1_C ≈ 0 |

**跨 session 复用分析**：
- A → B：可复用 L0，L1 不同需重新 prefill → 节省 L0 tokens
- A → C：可复用 L0 + L1(≈0) → 几乎完全复用 → 节省 L0 tokens
- B → C：可复用 L0，L1 不同 → 节省 L0 tokens

**关键验证**：不同项目的 session 共享 L0（base instructions + 内置工具），L1 形成树状分支

### 场景 S4：AGENTS.md 大小消融

**目标**：隔离 AGENTS.md 对 L1 前缀和跨 session 收益的贡献

**设定**：
- 同一项目（`mini-swe-agent`），3 种 AGENTS.md 配置：
  - S4a：无 AGENTS.md（L1 = 0）
  - S4b：合成小 AGENTS.md（~500 tokens，包含代码规范）
  - S4c：合成大 AGENTS.md（~4,000 tokens，包含代码规范+架构+测试方法）
- 每种配置 2 个 session

**预期结果**：

| 配置 | L1 估计 | 跨 session 可节省 | 跨 session 可节省比例 |
|------|---------|------------------|---------------------|
| S4a (无) | 0 | L0 | L0 / (L0+L2) |
| S4b (500 tk) | ~500 | L0 + 500 | (L0+500) / (L0+500+L2) |
| S4c (4000 tk) | ~4,000 | L0 + 4,000 | (L0+4000) / (L0+4000+L2) |

**量化指标**：AGENTS.md token 数 vs 跨 session 可节省量的关系（应为线性）

### 场景 S5：Permissions 配置消融

**目标**：测量 sandbox_mode + approval_policy 对 L0/L1 前缀的影响

**设定**：
- `codex-repo`，3 种 permissions 配置：
  - S5a：`read-only` + `never`（最短，~15 tokens）
  - S5b：`workspace-write` + `on-failure`（中等，~20 tokens）
  - S5c：`workspace-write` + `on-request`（最长，~800 tokens）

**预期**：on-request 的 approval_policy 模板（~800 tokens）形成额外 L1 差异；同配置 session 仍共享

### 场景 S6：MCP 工具消融

**目标**：测量 MCP 工具 namespace 对 L0/L1 前缀的影响

**设定**：
- `codex-repo`，有/无 MCP 配置各 2 个 session

**预期**：MCP 工具增大 L0（如果所有 session 共享同一 MCP）或形成额外 L1 分支（不同 MCP 配置）

---

## 7. 数据采集方案

### 7.1 运行命令模板

```bash
# 通用参数
COMMON_FLAGS="--quiet --model codex-mini --full-auto"

# S1: 单项目，间隔 5min+
for i in 1 2 3; do
  cd /share/dai-sys/zhoulongsheng/agentkv/Agent/codex
  codex $COMMON_FLAGS \
    "Find all Rust files that define tool schemas and list their names." \
    2>&1 | tee results/S1/session_$i.jsonl
  sleep 300  # 5 分钟
done

# S2: 单项目，并发
for i in 1 2 3; do
  cd /share/dai-sys/zhoulongsheng/agentkv/Agent/codex
  codex $COMMON_FLAGS \
    "Find all Rust files that define tool schemas and list their names." \
    2>&1 | tee results/S2/session_$i.jsonl &
done
wait

# S3: 多项目
cd /share/dai-sys/zhoulongsheng/agentkv/Agent/mini-swe-agent
codex $COMMON_FLAGS "List the main source files and describe the project structure." \
  2>&1 | tee results/S3/session_A.jsonl

cd /share/dai-sys/zhoulongsheng/agentkv/Agent/codex
codex $COMMON_FLAGS "List the main source files and describe the project structure." \
  2>&1 | tee results/S3/session_B.jsonl

cd /share/dai-sys/zhoulongsheng/agentkv/Agent/SWE-agent
codex $COMMON_FLAGS "List the main source files and describe the project structure." \
  2>&1 | tee results/S3/session_C.jsonl

# S4a: 无 AGENTS.md
cd /share/dai-sys/zhoulongsheng/agentkv/Agent/mini-swe-agent
codex $COMMON_FLAGS "Explain the build system and how to run tests." \
  2>&1 | tee results/S4a/session_1.jsonl

# S4b/S4c: 先写入合成 AGENTS.md，再运行（同上）
```

### 7.2 数据记录字段

| 字段 | 来源 | 说明 |
|------|------|------|
| `session_id` | rollout thread_id | 唯一 session 标识 |
| `scenario` | 实验标注 | S1/S2/S3/S4a/S4b/S4c/S5a/S5b/S5c/S6 |
| `project` | 工作目录 | 项目名 |
| `turn_index` | 计数 | 0-indexed API turn |
| `timestamp` | rollout event | API 调用时间 |
| `input_tokens` | `usage.input_tokens` | 总输入 tokens |
| `output_tokens` | `usage.output_tokens` | 输出 tokens |
| `total_tokens` | `usage.total_tokens` | 总 tokens |
| `tools_count` | 计数 | 本 turn 启用的工具数 |
| `base_instructions_tokens` | tiktoken 估计 | Base Instructions token 数 |
| `agents_md_tokens` | tiktoken 估计 | AGENTS.md token 数 |
| `permissions_tokens` | tiktoken 估计 | Permissions 指令 token 数 |
| `environment_tokens` | tiktoken 估计 | Environment context token 数 |
| `sandbox_mode` | 配置 | read_only / workspace_write / danger_full_access |
| `approval_policy` | 配置 | never / on_failure / on_request / unless_trusted |
| `has_mcp` | 配置 | 是否有 MCP 工具 |
| `has_agents_md` | 布尔 | 是否有 AGENTS.md |

### 7.3 前缀分解测量

```python
import tiktoken
enc = tiktoken.encoding_for_model("gpt-4")

# 逐层测量各组件 token 数
base_instructions = open("codex-rs/protocol/src/prompts/base_instructions/default.md").read()
L0_base = len(enc.encode(base_instructions))

agents_md = open("AGENTS.md").read()
L1_agents_md = len(enc.encode(agents_md))

# 工具 schema tokens（从 tool_router 输出提取）
# 需要在 Codex CLI 中添加 --dump-tools 选项或从日志提取
L0_tools = estimate_tool_schema_tokens(builtin_tools)

L0 = L0_base + L0_tools
L1 = L1_agents_md + L1_skills + L1_plugins + L1_permissions
L2 = L2_environment + L2_user_message
```

---

## 8. 核心指标与计算

### 8.1 前缀长度

| 指标 | 计算方式 | 预期范围 |
|------|---------|---------|
| L0 前缀 | base_instructions_tokens + builtin_tool_schema_tokens + personality_tokens | 4,395 + 2,000-5,000 ≈ 6,400-9,400 |
| L1 前缀 | agents_md_tokens + skills_tokens + plugins_tokens + permissions_tokens + mcp_tokens | 0-6,000 |
| L0+L1 | L0 + L1 | 6,400-15,400 |

### 8.2 Prefill 开销

```
# 无跨 session 缓存（每个 session 独立 prefill）
prefill_no_cross = N_sessions × (L0 + L1 + L2)

# 有跨 session 缓存（树状复用）
# K 个项目，第 p 个项目有 M_p 个 session，同项目同配置
prefill_with_cross = Σ_projects (
    (L0 + L1_project + L2)                    # 第一个 session 全价
    + (M_project - 1) × L2                    # 后续 session 只 prefill L2
)

# 但不同配置（permissions）的 session 不共享 L1_config
# 需要按 (project, config) 分组计算

# 跨 session 节省
savings = prefill_no_cross - prefill_with_cross
savings_pct = savings / prefill_no_cross × 100%
```

### 8.3 AGENTS.md ROI

```
# 每增加 1 token 的 AGENTS.md，在 N 个同项目 session 中节省
savings_per_token_per_session = 1 × (N - 1) / N  # 趋近 1 token/session

# 在 prefill 计算时间维度（假设 prefill 时间 ∝ token 数）
time_savings = L1_tokens × (N - 1) × time_per_token
```

### 8.4 树状结构效率

```
# K 个项目，第 p 个项目有 M_p 个 session
# C 种不同配置（permissions 组合）
total_savings = (Σ M_p - 1) × L0 × time_per_token       # L0 全局共享
             + Σ_p Σ_c (M_p_c - 1) × L1_p_c × time_per_token  # L1 组内共享

# 其中 M_p_c = 项目 p 中使用配置 c 的 session 数
```

---

## 9. 分析脚本

| 脚本 | 输入 | 输出 | 功能 |
|------|------|------|------|
| `extract_turn_data.py` | rollout JSONL | CSV (每行一 turn) | 提取 usage 字段、前缀组件 token 数 |
| `decompose_prefix.py` | base_instructions, AGENTS.md, tools | CSV (组件, token 数) | tiktoken 逐层测量 |
| `compute_metrics.py` | turn CSV + prefix CSV | 指标汇总表 | 计算 prefill 开销、节省量、ROI |
| `generate_figures.py` | 指标汇总 | 论文图表 | 5 张图 + 1 张表 |

### 图表清单

1. **图1：前缀分解堆叠图** — 各项目 L0-base / L0-tools / L1-agents_md / L1-permissions / L2-history 的 token 数
2. **图2：首 Turn Prefill 开销占比** — L0+L1 vs L2 在首 turn 中的比例
3. **图3：跨 Session Prefill 节省对比** — S1 vs S2 vs S3 的首 turn prefill 开销
4. **图4：AGENTS.md 大小 vs 节省量** — 散点图 + 线性拟合
5. **图5：前缀树示意图** — L0 → L1_config → L1_project → sessions，标注 token 数
6. **表1：汇总统计** — L0/L1 大小、prefill 开销、节省比例

---

## 10. 测试项目

| 项目 | 语言 | AGENTS.md | L1 估计 | 用途 |
|------|------|----------|---------|------|
| `mini-swe-agent` | Python | 无 | 0 | L0-only 基线 |
| `codex-repo` | Rust | 有（~20KB） | ~2,000-3,000 | 丰富 L1 |
| `SWE-agent` | Python | 无 | 0 | L0-only 基线（对比） |
| mini-swe-agent + 合成小 AGENTS.md | Python | ~500 tokens | ~500 | S4b 消融 |
| mini-swe-agent + 合成大 AGENTS.md | Python | ~4,000 tokens | ~4,000 | S4c 消融 |

**合成 AGENTS.md** 需要手工编写，包含代码规范、架构说明、测试方法等内容。

---

## 11. 执行计划

| 阶段 | 内容 | 时间 | 预估费用 |
|------|------|------|---------|
| Phase 0 | 环境搭建、脚本编写、冒烟测试 | 1 天 | $1 |
| Phase 1 | 前缀分解测量 (decompose_prefix.py) | 0.5 天 | $0 |
| Phase 2 | S1 基线实验 | 1 天 | $3 |
| Phase 3 | S2 并发实验 | 0.5 天 | $3 |
| Phase 4 | S3 多项目跨 session | 1 天 | $3 |
| Phase 5 | S4 AGENTS.md 消融 | 1 天 | $4 |
| Phase 6 | S5 Permissions 消融 | 0.5 天 | $2 |
| Phase 7 | S6 MCP 消融 | 0.5 天 | $2 |
| Phase 8 | 分析与制图 | 2 天 | $0 |
| **合计** | | **8 天** | **~$18** |

> 基于 codex-mini 定价：$0.15/M input, $0.60/M output

---

## 12. 预期结果

### 12.1 跨 Session Prefill 节省预期

| 场景 | 跨 Session 可节省 | 原因 |
|------|------------------|------|
| S1 (单项目) | (N-1) × (L0+L1) | 同项目同配置，L0+L1 完全复用 |
| S2 (并发) | (N-1) × (L0+L1) | 同上，并发只是时间维度 |
| S3 (多项目) | (N-1) × L0 | 不同项目仅 L0 共享，L1 不同 |
| S4a (无 AGENTS.md) | (N-1) × L0 | L1 = 0，仅 L0 可复用 |
| S4c (大 AGENTS.md) | (N-1) × (L0+4000) | L1 增大，可复用前缀更长 |
| S5c (on-request) | (N-1) × (L0+L1+800) | approval_policy 增大 L1 |

### 12.2 与扁平架构对比

| Agent 系统 | 共享前缀 | 树状 | 跨 session 可节省 | 前缀复用机制 |
|-----------|---------|------|------------------|------------|
| mini-swe-agent | 27 tokens | 扁平 | ≈ 0 | 无 |
| SWE-agent 07.yaml | 6,531 tokens | 扁平 | ≈ 0 | 无 |
| Codex CLI（无跨 session 调度） | 6,400-9,400 | 树状 | 0%（无调度） | 仅 session 内 |
| **Codex CLI（跨 session 调度）** | **6,400-15,400** | **树状** | **40-70%** | **跨 session 树状复用** |

### 12.3 与 Claude Code 对比

| 维度 | Codex CLI | Claude Code |
|------|----------|-------------|
| L0 前缀 | ~6,400-9,400 tokens | ~12,000-30,000 tokens |
| L1 前缀 | 0-6,000 tokens | 0-8,000 tokens |
| Prompt caching | ❌ 无 | ✅ 有（5min/1h TTL） |
| 可直接验证缓存命中 | ❌ | ✅（cache_read_input_tokens） |
| 实验可操作性 | ✅ 全开源，可修改 | ⚠️ 核心逻辑在二进制中 |
| API 费用 | 低（codex-mini） | 较高（claude-sonnet） |
| 树状分支来源 | AGENTS.md + permissions | CLAUDE.md + skills + memory |

**Codex CLI 的优势**：完全开源，prompt 组装逻辑可直接审计和修改，费用低。
**Claude Code 的优势**：已有 prompt caching 机制，可直接观测 cache_read/cache_creation，L0 前缀更大。

### 12.4 论文贡献

1. **首次量化** Codex CLI 场景下的树状跨 session KV Cache 复用特征
2. **实验证明**项目级配置文件（AGENTS.md）和权限配置（sandbox_mode + approval_policy）是树状前缀共享的自然分支点
3. **消融分析** AGENTS.md 大小、permissions 配置与跨 session 收益的关系
4. **与扁平架构的对比**：树状结构的共享前缀是扁平结构的 2-5 倍
5. **与 Claude Code 的对比**：两个树状结构 agent 框架的异同，L0/L1 分解差异

---

## 13. 前置条件与风险

| 前置条件 | 说明 | 解决方案 |
|---------|------|---------|
| 需要 OpenAI API Key | 使用 Codex CLI 需要 OpenAI API | 使用 codex-mini（性价比最高） |
| 无 prompt caching 数据 | OpenAI Responses API 暂无 cache_read/cache_creation 字段 | 通过 tiktoken 离线估计前缀大小，计算理论节省量 |
| 需要提取 tool schema | 需要知道工具 schema 的 token 数 | 添加 --dump-tools 选项或从 rollout 日志提取 |
| AGENTS.md 合成文件 | S4b/S4c 需要手工编写 | 可从真实项目提取 |
| Session 时间控制 | S1 需要 5min 间隔 | 脚本自动控制 sleep 时间 |
| 费用控制 | 每个场景 ~$2-4，总计 ~$18 | 先跑冒烟测试，确认数据格式正确后再批量 |

---

## 14. 关键文件索引

| 文件 | 位置 | 用途 |
|------|------|------|
| Base Instructions | `codex-rs/protocol/src/prompts/base_instructions/default.md` | L0 核心系统指令 |
| Prompt 组装 | `codex-rs/core/src/session/mod.rs` → `build_initial_context()` | 首 turn 上下文组装 |
| Turn 执行 | `codex-rs/core/src/session/turn.rs` → `build_prompt()` | API 请求构建 |
| AGENTS.md 加载 | `codex-rs/core/src/agents_md.rs` → `AgentsMdManager` | 项目配置发现与加载 |
| 工具组装 | `codex-rs/core/src/tools/spec_plan.rs` → `build_tool_router()` | 工具集组装 |
| 工具定义 | `codex-rs/tools/src/tool_spec.rs`, `responses_api.rs` | 工具 schema 类型定义 |
| Shell 工具 | `codex-rs/core/src/tools/handlers/shell_spec.rs` | shell_command schema |
| Apply Patch 工具 | `codex-rs/core/src/tools/handlers/apply_patch_spec.rs` | apply_patch schema (Freeform) |
| Permissions 模板 | `codex-rs/prompts/templates/permissions/` | sandbox + approval 模板 |
| Permissions 组装 | `codex-rs/prompts/src/permissions_instructions.rs` | 权限指令渲染 |
| Compact 模板 | `codex-rs/prompts/templates/compact/prompt.md` | context compaction |
| Agent 层级 | `codex-rs/prompts/templates/agents/hierarchical.md` | 子 agent AGENTS.md 规范 |
| User Instructions | `codex-rs/core/src/context/user_instructions.rs` | AGENTS.md 渲染 |
| Environment Context | `codex-rs/core/src/context/environment_context.rs` | 环境上下文渲染 |
| Context 更新 | `codex-rs/core/src/context_manager/updates.rs` | turn 间 context diff |
| Codex 主仓库 | `Agent/codex/` | 实验运行 |
| mini-swe-agent | `Agent/mini-swe-agent/` | L0-only 基线测试项目 |
| SWE-agent | `Agent/SWE-agent/` | L0-only 基线测试项目 |

---

## 15. 与 Claude Code 实验方案的对照

| 维度 | Codex CLI 方案 | Claude Code 方案 |
|------|---------------|-----------------|
| 文档 | 本文档 | [05_claude_code_trace_study_plan.md](docs/05_claude_code_trace_study_plan.md) |
| L0 前缀 | ~6,400-9,400 tokens | ~12,000-30,000 tokens |
| 项目配置文件 | AGENTS.md | CLAUDE.md |
| API | OpenAI Responses API | Anthropic Messages API |
| 缓存验证 | ❌ 无 cache 字段（理论计算） | ✅ 有 cache_read/cache_creation |
| 权限消融 | S5: sandbox_mode × approval_policy | 无（Claude Code 用 permission mode） |
| MCP 消融 | S6: 有/无 MCP | S5: 有/无 MCP |
| 费用 | ~$18（codex-mini） | ~$25（claude-sonnet） |
| 可审计性 | ✅ 全开源 | ⚠️ 核心在二进制中 |

**互补价值**：两个实验方案共同证明树状跨 session KV Cache 复用的普遍性——不同框架（OpenAI vs Anthropic）、不同项目配置机制（AGENTS.md vs CLAUDE.md）、不同工具规模（~3K vs ~26K tokens）下，树状结构都是自然形成的。
