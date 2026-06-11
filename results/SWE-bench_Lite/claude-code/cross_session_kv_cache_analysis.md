# Claude Code 跨 Session KV Cache 复用分析

> 基于 Claude Code v2.1.165 源码（二进制逆向 + sdk-tools.d.ts + 实际运行数据）
> 最后更新：2026-06-11

---

## 1. Claude Code Prompt 的组装方式

Claude Code 的 system prompt 不是单一字符串，而是由多个 block 组成的数组，每个 block 可以独立设置 `cache_control`。

### 1.1 组装流程（从二进制逆向）

```
函数调用链:
  pm()              → 构建 system prompt 数组
    ├── agentDefinition.getSystemPrompt()  → 身份声明 + Persona 指令
    ├── customSystemPrompt                 → 默认 coding instructions (yfA 变量)
    └── appendSystemPrompt                 → 追加的指令
  
  e9()              → 返回 system prompt 数组（identity 函数）
  
  最终组装 (T39 generator):
    e9([
      We$(C),              → API billing header
      e78({...}),           → 身份声明 ("You are Claude Code...")
      ...$,                 → pm() 返回的各段
      ...j ? [LV7] : []     → Advisor tool prompt（可选）
    ].filter(Boolean))
  
  igA($, x, {...})  → 为各 block 添加 cache_control 标记
```

### 1.2 关键标记

- `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` / `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__`：分隔静态部分和动态部分的边界标记
- `cache_control: {"type": "ephemeral"}`：5 分钟 TTL 缓存
- `cache_control: {"type": "ephemeral", "ttl": "1h"}`：1 小时 TTL 缓存
- `cache_control: {"type": "ephemeral", "scope": "global"}`：全局缓存（跨 session 共享，MCP 工具存在时启用）

---

## 2. System Prompt 的逐层内容

### 2.1 身份声明（所有 session 相同）

```
"You are Claude Code, Anthropic's official CLI for Claude."
```

tiktoken: 13 tokens

根据运行模式有三种变体：

| 模式 | 身份声明 | 触发条件 |
|------|---------|---------|
| 交互式 CLI | `"You are Claude Code, Anthropic's official CLI for Claude."` | 默认 |
| SDK 非交互 + append | `"You are Claude Code, Anthropic's official CLI for Claude, running within the Claude Agent SDK."` | isNonInteractive && hasAppendSystemPrompt |
| Agent/SDK 最小化 | `"You are a Claude agent, built on Anthropic's Claude Agent SDK."` | isNonInteractive && !hasAppendSystemPrompt |

### 2.2 Persona 指令（所有 session 相同，但可选不同 persona）

Claude Code 支持 4 种 persona，默认为 Proactive：

| Persona | 核心指令 | 估计 tokens |
|---------|---------|------------|
| **Proactive**（默认） | `"You are an interactive CLI tool that helps users with software engineering tasks. You should work proactively and autonomously, executing immediately and minimizing interruptions."` + `# Proactive Style Active` + coding instructions (yfA) + turn reminder (hfA) | ~34 + ~2,000 |
| Explanatory | `"You are an interactive CLI tool that helps users with software engineering tasks. In addition to software engineering tasks, you should provide educational insights about the codebase along the way."` + `_I4` instructions | ~50 + ~1,000 |
| Learning | `"You are an interactive CLI tool that helps users with software engineering tasks. In addition to software engineering tasks, you should help users learn more about the codebase through hands-on practice and educational insights."` + 完整的 Learn-by-Doing 框架 | ~80 + ~2,000 |
| null (aC) | 无额外指令 | 0 |

Persona 选择通过 `--output-style` 参数或 UI 设置。

### 2.3 Coding Instructions（所有 session 相同）

跟随 Persona 注入的核心指令块（`yfA` 变量），包含：

- 工具使用指南（Read、Edit、Write、Bash 等的使用规则）
- 编辑协议（如何修改代码、如何处理 diff）
- 搜索策略（Glob、Grep 的最佳实践）
- 安全和权限规则
- 会话管理指令

估计: ~1,000-3,000 tokens（从二进制推断，具体内容在编译后的 `yfA` 变量中）

### 2.4 CLAUDE.md 内容（按层级加载，是树状分支的关键）

CLAUDE.md 按**文件层级**加载，越深层的文件优先级越高：

```
加载顺序:
  1. ~/.claude/CLAUDE.md          → 用户级（同一用户所有 session 共享）
  2. ./CLAUDE.md                   → 项目根目录（同一项目所有 session 共享）
  3. ./.claude/CLAUDE.md           → 项目 gitignored 目录（同一项目共享）
  4. managed/policy CLAUDE.md      → 组织级（同一组织共享）
  5. Memory service CLAUDE.md      → 远程记忆服务
```

各层级 token 数估算：

| 层级 | 典型内容 | 典型 tokens | 跨 Session 共享范围 |
|------|---------|------------|-------------------|
| 用户级 (`~/.claude/CLAUDE.md`) | 全局偏好（语言、风格） | 50-200 | 同一用户的所有 session |
| **项目级** (`./CLAUDE.md`) | **代码规范、架构说明、测试方法、依赖说明** | **0-5,000+** | **同一项目的所有 session** |
| 项目级 (`.claude/CLAUDE.md`) | 项目私有指令 | 0-2,000 | 同一项目的所有 session |
| 组织级 (managed) | 团队规范、安全策略 | 0-3,000 | 同一组织的所有 session |

**项目级 CLAUDE.md 是树状分支的关键**：不同项目的 CLAUDE.md 内容不同，导致 system prompt 在此处分化。

加载函数：`getClaudeMds()`，缓存函数：`setCachedClaudeMdContent()` / `getCachedClaudeMdContent()`

可禁用：`CLAUDE_CODE_DISABLE_CLAUDE_MDS=true`

### 2.5 技能列表（按项目不同）

来自 `.claude/commands/` 和 `.claude/agents/` 目录的技能定义。

```
.claude/
  commands/          → 用户可调用的 slash 命令
    review.md        → /review 技能
    simplify.md      → /simplify 技能
    ...
  agents/            → 子 agent 定义
    code-reviewer.md → code-reviewer agent
    ...
```

- 不同项目可以定义不同的技能 → 形成树状分支
- 技能列表注入 system prompt 中，在 DYNAMIC_BOUNDARY 之前

### 2.6 Memory 文件（按项目不同）

来自 `.claude/projects/<sanitized-cwd>/memory/` 目录的持久化记忆文件。

```
.claude/projects/-share-dai-sys-zhoulongsheng-agentkv/
  memory/
    project-structure.md    → 项目结构记忆
    coding-style.md         → 代码风格偏好
    ...
  MEMORY.md                 → 记忆索引
```

- 不同项目目录有不同的 memory → 形成树状分支
- 注入 system prompt 中

### 2.7 Tool Schemas（所有 session 相同，但 MCP 工具可按项目不同）

Tool schemas 通过 API `tools` 参数传递，不在 system prompt 消息中。

| 工具类别 | 工具名 | 估计 schema tokens |
|---------|-------|-------------------|
| 文件操作 | Read, Edit (FileEdit), Write (FileWrite) | ~500 |
| 搜索 | Glob, Grep | ~200 |
| 执行 | Bash | ~100 |
| Web | WebFetch, WebSearch | ~300 |
| 笔记本 | NotebookEdit | ~200 |
| 任务管理 | TaskCreate, TaskGet, TaskUpdate, TaskList, TaskStop | ~400 |
| 计划模式 | EnterPlanMode, ExitPlanMode | ~150 |
| 用户交互 | AskUserQuestion | ~1,500 |
| 待办事项 | TodoWrite | ~100 |
| MCP | ListMcpResources, ReadMcpResource, Mcp | ~300 |
| 调度 | CronCreate, CronDelete, CronList, ScheduleWakeup | ~300 |
| 工作树 | EnterWorktree, ExitWorktree | ~200 |
| Agent | Agent (subagent spawning) | ~300 |
| 监控 | Monitor, RemoteTrigger, PushNotification | ~200 |
| REPL | REPL | ~100 |
| Workflow | Workflow | ~200 |
| Skill | Skill | ~100 |
| ToolSearch | ToolSearch (延迟加载) | ~100 |
| **合计** | **~26 个** | **~8,000-15,000** |

**MCP 工具的特殊性**：
- MCP 工具从 `.mcp.json` 配置动态加载
- 不同项目可以配置不同的 MCP 服务器 → 形成额外分支
- 当 MCP 工具存在时，Claude Code 自动启用 `scope: "global"` 的缓存策略

延迟加载机制：`ToolSearch` 工具允许只在需要时才加载完整的 MCP 工具 schema，节省首 turn 的 context window。

---

## 3. 跨 Session 共享前缀的树状结构

### 3.1 层级定义

| 层级 | 共享范围 | 内容 | 估计 tokens |
|------|---------|------|------------|
| **L0** | 所有 session | 身份声明 + Persona 指令 + Coding Instructions + 用户级 CLAUDE.md + Tool Schemas | ~10,000-18,000 |
| **L1** | 同项目的 session | 项目级 CLAUDE.md + 技能列表 + Memory 文件 + 项目级 MCP 工具 | 0-8,000+ |
| **L2** | 单个 session | 对话历史（assistant 回复 + tool_result） | 动态增长 |

### 3.2 树状结构示意

假设 serving 系统同时处理以下场景：

```
用户 Alice 同时用 Claude Code 在 3 个项目上工作：
  项目 A: django/django（大型 Python 项目，有详细 CLAUDE.md + 技能 + MCP）
  项目 B: 小型脚本项目（无 CLAUDE.md，无技能）
  项目 C: rust-cli（中型 Rust 项目，有 CLAUDE.md）
```

```
                         L0 根节点 (~10,000-18,000 tokens)
                         ├── 身份声明 (13 tokens)
                         ├── Persona + Coding Instructions (~2,000-3,000 tokens)
                         ├── 用户级 CLAUDE.md (~100 tokens)
                         └── Tool Schemas (~8,000-15,000 tokens)
                        /                    |                    \
               L1-项目 A               L1-项目 B             L1-项目 C
               项目级 CLAUDE.md_A       (无 L1 扩展)          项目级 CLAUDE.md_C
               + 技能列表_A                                   + Memory 文件_C
               + Memory 文件_A
               + MCP 工具_A (django-helper)
               +2,000-8,000 tokens                             +500-3,000 tokens
              /           \                                        |
        session_A1      session_A2                             session_C1
        (修复 auth bug)  (添加 API endpoint)                  (重构 CLI parser)
```

### 3.3 KV Cache 复用计算

**N 个项目、每个项目 M_k 个 session 的总 prefill 计算：**

```
无跨 session 缓存:
  total = Σ_k Σ_{j=1}^{M_k} (L0 + L1_k + L2_{k,j})

有跨 session 缓存 (prefix tree):
  total = L0                          ← 根节点只算 1 次
        + Σ_k L1_k                    ← 每个项目的 L1 只算 1 次
        + Σ_k Σ_{j=1}^{M_k} L2_{k,j} ← 每个 session 的动态部分各算 1 次

节省量 = Σ_k (M_k - 1) × (L0 + L1_k)
       = (N_sessions - 1) × L0 + Σ_k (M_k - 1) × L1_k
```

**具体示例**：

```
3 个项目，各 2 个 session:
  L0 = 10,000 tokens
  L1_A = 3,000, L1_B = 0, L1_C = 1,500

无缓存: (10,000+3,000)×2 + (10,000+0)×2 + (10,000+1,500)×2 = 56,000
有缓存: 10,000 + 3,000 + 0 + 1,500 = 14,500 (静态部分)
节省: 56,000 - 14,500 = 41,500 tokens (74.1%)
```

---

## 4. Claude Code 已有的缓存机制

Claude Code **已经内置了 prompt caching**，但其作用范围有限：

### 4.1 现有缓存的作用范围

| 缓存类型 | TTL | 作用范围 | 说明 |
|---------|-----|---------|------|
| `cache_control: ephemeral` | 5 分钟 | **同一 session 内** | Anthropic API 的 session 内 prefix caching |
| `cache_control: ephemeral, ttl: 1h` | 1 小时 | **同一 session 内** | 长时间间隔的 session 内缓存 |
| `cache_control: ephemeral, scope: global` | 5 分钟 / 1 小时 | **跨 session** | MCP 工具存在时启用，允许跨 request 复用 |

### 4.2 现有缓存的局限

1. **5 分钟 TTL 过短**：agent session 之间可能间隔更长，缓存已过期
2. **没有前缀树管理**：不主动管理 KV Cache 的前缀树结构，不会把同项目的 session 调度到同一 GPU
3. **没有显式的跨 session 调度**：即使 `scope: global` 允许跨 session 复用，也没有 agent-aware 的调度策略
4. **MCP 工具触发条件苛刻**：只有存在 MCP 工具时才启用 global scope，大多数项目没有 MCP 工具

### 4.3 缓存失效追踪

Claude Code 内置了详细的缓存失效追踪（`sb7()` 函数），当缓存读取量下降超过 2,000 tokens 时触发诊断：

| 失效原因 | 检测方式 |
|---------|---------|
| System prompt 变化 | perBlockHashes 对比 |
| Tool schema 变化 | perToolHashes 对比 |
| 模型切换 | model 字段对比 |
| Fast mode 切换 | fastMode 对比 |
| Cache control 变化 | cacheControlHash 对比 |
| 5 分钟过期 | 距上次 assistant >300s |
| 1 小时过期 | 距上次 assistant >3600s |
| Beta 标志变化 | betas 对比 |
| Auto mode 切换 | isAutoModeActive 对比 |

---

## 5. 实验设计建议

### 5.1 数据采集

使用 Claude Code 的 JSONL 日志（`~/.claude/projects/<cwd>/<session-id>.jsonl`）记录每个 session 的：
- 完整 system prompt 各 block 的内容和 token 数
- Tool schema 的内容和 token 数
- CLAUDE.md 的内容和 token 数
- 每 turn 的 `cache_creation_input_tokens` 和 `cache_read_input_tokens`（API 返回）

### 5.2 模拟场景

1. **单用户多项目**：同一用户在 N 个项目上分别运行 M 个 Claude Code session
2. **单项目多 session**：同一项目上运行多个不同任务的 session
3. **多用户同项目**：不同用户在同一项目上运行 session（共享项目级 CLAUDE.md，不共享用户级）

### 5.3 关键量化指标

| 指标 | 定义 | 意义 |
|------|------|------|
| L0 共享前缀长度 | 身份 + Persona + Coding + 用户级 CLAUDE.md + Tool Schemas | 根节点的 KV Cache 大小 |
| L1 分支增量 | 项目级 CLAUDE.md + 技能 + Memory + MCP 工具 | 分支节点的 KV Cache 大小 |
| 树的深度 | L0 → L1 → L2 | 层级数 |
| 树的广度 | 项目数 N | 分支数 |
| 跨 session 节省率 | (1 - 有缓存/无缓存) × 100% | 总体复用效率 |
| 缓存命中率 | cache_read_input_tokens / total_input_tokens | 实际缓存利用效率 |

---

## 6. 源码位置索引

| 组件 | 位置 | 说明 |
|------|------|------|
| 工具类型定义 | `~/.npm-global/lib/node_modules/@anthropic-ai/claude-code/sdk-tools.d.ts` | 26 个工具的 TypeScript 输入/输出类型 |
| 核心二进制 | `~/.npm-global/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe` | 编译后的 Bun 原生二进制 |
| System prompt 组装 | 二进制中 `pm()` 函数 | 构建 system prompt 数组 |
| 缓存控制 | 二进制中 `igA()` 函数 | 添加 cache_control 标记 |
| 缓存失效追踪 | 二进制中 `sb7()` 函数 | 追踪缓存未命中原因 |
| CLAUDE.md 加载 | 二进制中 `getClaudeMds()` | 按层级加载 CLAUDE.md |
| Persona 定义 | 二进制中 `qLH` 对象 | Proactive / Explanatory / Learning / null |
| 项目日志 | `~/.claude/projects/<sanitized-cwd>/<session-id>.jsonl` | session 对话记录 |
| Memory 文件 | `~/.claude/projects/<sanitized-cwd>/memory/` | 持久化记忆 |
