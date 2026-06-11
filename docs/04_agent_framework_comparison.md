# Agent 框架 Prompt 结构对比与跨 Session 共享前缀分析

> 最后更新：2026-06-10
> 分析基于源码：mini-swe-agent、SWE-agent、OpenAI Codex CLI、Claude Code

---

## 1. 四个框架的 Prompt 结构总览

### 1.1 mini-swe-agent (swebench.yaml)

```
┌────────────────────────────┐
│ System (17 tokens)         │  ← 所有 session 相同
│ Instance 静态前缀 (10 tk)  │  ← 所有 session 相同
│ Instance 动态 (task)       │  ← 每个 session 不同
│ Instance 静态后缀 (967 tk) │  ← 内容相同，被阻断
│ BASH_TOOL schema (63 tk)   │  ← 内容相同，被阻断
│ API 格式开销 (~245 tk)     │  ← 内容相同，被阻断
└────────────────────────────┘

连续共享前缀: 27 tokens
树状结构: 无（扁平）
```

### 1.2 SWE-agent (07.yaml)

```
┌─────────────────────────────────────┐
│ System + 工具文档 (939 tokens)       │  ← 所有 session 相同
│ Demonstration 轨迹 (5,572 tokens)   │  ← 所有 session 相同
│ Instance 静态前缀 (20 tokens)        │  ← 所有 session 相同
│ Instance 动态 (task)                 │  ← 每个 session 不同
│ Instance 静态后缀 (646 tokens)       │  ← 内容相同，被阻断
└─────────────────────────────────────┘

连续共享前缀: 6,531 tokens
树状结构: 无（扁平，只是棍更长）
```

### 1.3 OpenAI Codex CLI

```
┌─────────────────────────────────────────────────────────┐
│ 【instructions】System prompt (4,395 tokens)              │  ← 所有 session 相同
│                                                           │
│   "You are a coding agent running in the Codex CLI..."   │
│   包含: 身份、AGENTS.md 规范、planning 示例、             │
│         task 执行规则、apply_patch 用法、                  │
│         验证规则、最终回答格式、tool guidelines            │
├─────────────────────────────────────────────────────────┤
│ 【developer message】权限 + AGENTS.md + 协作模式          │
│                                                           │
│   ┌──────────────────────────────────────────────────┐   │
│   │ 权限指令 (sandbox_mode + approval_policy)         │   │  ← 按配置不同
│   │   read_only / workspace_write / danger_full_access│   │
│   │   on_failure / on_request / never / unless_trusted│   │
│   └──────────────────────────────────────────────────┘   │
│   ┌──────────────────────────────────────────────────┐   │
│   │ AGENTS.md 内容                                    │   │  ← 按项目目录不同 ★
│   │   <AGENTS.md instructions for ...>                │   │
│   │   代码规范、架构说明、测试方法...                   │   │
│   │   </AGENTS.md instructions>                       │   │
│   └──────────────────────────────────────────────────┘   │
│   ┌──────────────────────────────────────────────────┐   │
│   │ developer instructions (--developer-instructions) │   │  ← 按用户指定不同
│   └──────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│ 【user message】环境上下文 + 用户任务                      │
│                                                           │
│   环境上下文: cwd, shell, date, timezone, ...            │  ← 按 session 不同
│   用户任务: "Fix the bug in auth.py"                      │  ← 每个 session 不同
├─────────────────────────────────────────────────────────┤
│ 【tools】shell + apply_patch + update_plan + MCP + ...    │  ← 内容相同，被阻断
└─────────────────────────────────────────────────────────┘

连续共享前缀: ~4,395 tokens (system prompt)
树状分支点: developer message 中的 AGENTS.md → 按项目不同形成分支
```

**关键文件**：
- System prompt: `codex-rs/protocol/src/prompts/base_instructions/default.md`
- Prompt 组装: `codex-rs/core/src/session/turn.rs` → `build_prompt()`
- 上下文注入: `codex-rs/core/src/session/mod.rs` → `build_initial_context()`
- AGENTS.md 加载: `codex-rs/core/src/agents_md.rs`
- 权限模板: `codex-rs/prompts/templates/permissions/`
- Fragment 机制: `codex-rs/context-fragments/src/fragment.rs`

### 1.4 Claude Code (Anthropic CLI)

```
┌──────────────────────────────────────────────────────────────┐
│ 【system prompt】身份 + 行为指令 (~2,000-3,000 tokens)         │
│                                                                │
│   "You are Claude Code, Anthropic's official CLI for Claude." │
│   包含: 工具使用指南、编辑协议、搜索策略、安全规则             │
│   按 block 粒度设置 cache_control: ephemeral (5min / 1h TTL)  │
│                                                                │
│   动态边界标记: SYSTEM_PROMPT_DYNAMIC_BOUNDARY                │
├──────────────────────────────────────────────────────────────┤
│ 【system prompt 续】CLAUDE.md 内容                             │
│                                                                │
│   ┌────────────────────────────────────────────────────────┐ │
│   │ ~/.claude/CLAUDE.md (用户级)                           │ │  ← 按用户相同
│   ├────────────────────────────────────────────────────────┤ │
│   │ ./CLAUDE.md 或 ./.claude/CLAUDE.md (项目级)           │ │  ← 按项目目录不同 ★
│   │   代码规范、项目偏好、常用工具链...                     │ │
│   ├────────────────────────────────────────────────────────┤ │
│   │ managed/policy CLAUDE.md (组织级)                      │ │  ← 按组织相同
│   └────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│ 【system prompt 续】技能列表 + Memory                          │
│   .claude/commands/ 和 .claude/agents/ 中的技能定义           │  ← 按项目目录不同 ★
├──────────────────────────────────────────────────────────────┤
│ 【tools】~26 个工具 (Bash, Read, Edit, Write, Glob, Grep,     │
│   WebFetch, WebSearch, Agent, Task*, Plan*, Ask*,             │
│   NotebookEdit, MCP, Cron*, Worktree*, Workflow, Skill...)   │
│   估计: 20,000-30,000 tokens                                  │  ← 内容相同，但被消息阻断
└──────────────────────────────────────────────────────────────┘

连续共享前缀: ~2,000-3,000 tokens (system prompt identity + 核心指令)
树状分支点: CLAUDE.md + 技能列表 → 按项目目录不同形成分支
```

**关键文件**：
- 工具定义: `~/.npm-global/lib/node_modules/@anthropic-ai/claude-code/sdk-tools.d.ts` (26 个工具, 129KB)
- Prompt 组装: 编译后的二进制 (`claude.exe`)，核心函数 `pm()`, `e9()`, `igA()`
- 缓存机制: `setSystemPromptSectionCacheEntry`, `getSystemPromptSectionCache`, 按 block 哈希追踪
- CLAUDE.md 加载: `getClaudeMds()`, 按层级: 用户级 → 项目级 → 组织级

---

## 2. 跨 Session 共享前缀对比

| 框架 | 连续共享前缀 | 树状分支 | 分支来源 | 分支增量 |
|------|------------|---------|---------|---------|
| mini-swe-agent | 27 tokens | ❌ 无 | - | - |
| SWE-agent (07.yaml) | 6,531 tokens | ❌ 无 | - | - |
| **Codex CLI** | **4,395 tokens** | **✅ 有** | **AGENTS.md (按项目)** | **数百~数千 tokens** |
| **Claude Code** | **~2,000-3,000 tokens** | **✅ 有** | **CLAUDE.md (按项目)** | **数百~数千 tokens** |

---

## 3. 树状共享前缀的形成机制

### 3.1 Codex 的树状结构

当 serving 系统同时处理多个项目的 Codex session 时：

```
                    根节点
                    system prompt (4,395 tokens)
                   /          |          \
              项目 A        项目 B       项目 C
              AGENTS.md_A   AGENTS.md_B  AGENTS.md_C
             /    \         /    \        /    \
           s1    s2       s3    s4      s5    s6

KV Cache 复用:
  - 所有 session 复用: system prompt (4,395 tokens)
  - 项目 A 的 session 复用: system prompt + AGENTS.md_A
  - 项目 B 的 session 复用: system prompt + AGENTS.md_B
```

分支来源：
1. **AGENTS.md**：每个项目有自己的 AGENTS.md（代码规范、架构说明、测试方法），按目录树加载，越深层级优先级越高
2. **权限指令**：不同 sandbox_mode / approval_policy 有不同的权限模板
3. **developer instructions**：用户通过 `--developer-instructions` 注入的自定义指令

### 3.2 Claude Code 的树状结构

```
                    根节点
                    身份 + 核心指令 (~2,000-3,000 tokens)
                   /          |          \
              项目 A        项目 B       项目 C
              CLAUDE.md_A   CLAUDE.md_B  CLAUDE.md_C
              技能列表_A    技能列表_B    技能列表_C
             /    \         /    \        /    \
           s1    s2       s3    s4      s5    s6

KV Cache 复用:
  - 所有 session 复用: 身份 + 核心指令 + tool schemas
  - 项目 A 的 session 复用: 上述 + CLAUDE.md_A + 技能列表_A
  - 项目 B 的 session 复用: 上述 + CLAUDE.md_B + 技能列表_B
```

分支来源：
1. **CLAUDE.md**：每个项目有项目级 CLAUDE.md（`./CLAUDE.md` 或 `./.claude/CLAUDE.md`）
2. **技能列表**：`.claude/commands/` 和 `.claude/agents/` 中定义的技能
3. **MCP 工具**：每个项目可能配置不同的 MCP 服务器（`.mcp.json`），动态加载不同的工具集
4. **Memory 文件**：`.claude/projects/<sanitized-cwd>/memory/` 中的持久化记忆

### 3.3 SWE-bench 场景的局限

为什么 mini-swe-agent 和 SWE-agent 没有树状结构？

- **同一数据集**：所有 300 条 instance 使用同一个 `swebench.yaml` 配置，没有项目级的差异化
- **没有项目配置文件**：模板是固定的，不根据 repo 不同注入不同的上下文
- **task 描述是唯一变量**：不同 session 之间只有 `problem_statement` 不同，没有层级化的共享

---

## 4. 实验场景建议

### 4.1 场景 A：Codex 多项目批量编程

**设定**：同时用 Codex 处理来自多个 GitHub 项目的 issue/任务。

```
serving 系统同时运行:
  - django/django: 5 个 session (共享 AGENTS.md_django)
  - sympy/sympy: 3 个 session (共享 AGENTS.md_sympy)
  - scikit-learn: 2 个 session (共享 AGENTS.md_sklearn)
```

**可量化的指标**：
- 树状共享前缀的 KV Cache 节省量 vs 扁平共享
- 不同分支粒度（按项目、按目录、按配置）的收益对比
- KV Cache 前缀树的深度和广度对调度效率的影响

### 4.2 场景 B：Claude Code 多项目开发

**设定**：用 Claude Code 同时开发多个项目，每个项目有自己的 CLAUDE.md。

**特点**：
- tool schemas 极大（20,000-30,000 tokens），所有 session 共享
- CLAUDE.md 内容差异形成树状分支
- 已有内置的 prompt caching 机制，可以对比有/无跨 session 缓存的性能差异

### 4.3 场景 C：SWE-bench + Repo-level 上下文注入

**设定**：在 SWE-bench 场景下，为每个 repo 注入 repo-level 的上下文信息（代码结构、关键文件、API 文档），模拟 AGENTS.md / CLAUDE.md 的效果。

```
修改 instance_template:
  原来: System → Instance (task + instructions)
  改后: System → Repo Context (按 repo 不同) → Instance (task + instructions)

形成树:
  根节点: system prompt + 通用指令
    ├── django 组: repo_context_django
    │     ├── s1, s2, ..., s114
    ├── sympy 组: repo_context_sympy
    │     ├── s1, s2, ..., s77
    └── ...
```

**优点**：不需要换框架，只需修改模板，复用已有的 SWE-bench 数据和运行流程。

---

## 5. 源码位置索引

| 框架 | 仓库路径 | 关键文件 |
|------|---------|---------|
| mini-swe-agent | `Agent/mini-swe-agent/` | `src/minisweagent/config/benchmarks/swebench.yaml` |
| SWE-agent | `Agent/SWE-agent/` | `config/sweagent_0_7/07.yaml`, `config/default.yaml` |
| Codex CLI | `Agent/codex/` | `codex-rs/protocol/src/prompts/base_instructions/default.md`, `codex-rs/core/src/session/turn.rs`, `codex-rs/core/src/agents_md.rs` |
| Claude Code | `Agent/claude-code/` | SDK 源码; 工具定义: `~/.npm-global/lib/node_modules/@anthropic-ai/claude-code/sdk-tools.d.ts` |
