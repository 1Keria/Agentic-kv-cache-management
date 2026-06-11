# Claude Code Prompt 组织结构

> 基于 Claude Code CLI（`@anthropic-ai/claude-code`，本地安装于 `~/.npm-global/.../claude-code/`）  
> 分析方法：官方文档 + `sdk-tools.d.ts` + 编译二进制 `claude.exe` 字符串 + 本地 session JSONL 转录  
> 最后更新：2026-06-10

---

## 1. 基本概念

### 1.1 Session 与 Turn 的定义

Claude Code 的一次 **session** = 从 `claude` 启动（或 `--resume`）到退出之间的完整对话。每个 session 对应 `~/.claude/projects/<sanitized-cwd>/<uuid>.jsonl` 中的一条转录。

与 mini-swe-agent / SWE-agent 不同，Claude Code 的「一轮」需要区分两个层次：

| 层次 | 含义 | 典型内容 |
|------|------|---------|
| **User Turn** | 用户发送一条消息后，Claude 完成整段 agentic loop | 1 条 user 文本 + 若干 attachment + 多步 tool 循环 + 最终 assistant 文本 |
| **API Turn** | 每次调用 Anthropic API | 完整 history + 本轮新增消息；KV cache 在 API Turn 粒度复用 |
| **Tool Step** | agentic loop 内的一步 | `assistant[tool_use]` → `user[tool_result]` |

一次 User Turn 通常包含 **多个 API Turn**（Claude 可能连续调用 Bash、Read、Grep 等工具，每步都是一次 API 调用）。

### 1.2 与 SWE-bench Agent 的关键差异

| 维度 | mini-swe-agent | SWE-agent | Claude Code |
|------|---------------|-----------|-------------|
| Prompt 模板 | YAML 固定模板 | YAML + Jinja | 多层 system 动态拼接 |
| 工具传递 | API `tools` 参数 | 07.yaml 嵌入 system 或 API | API `tools` + ToolSearch 延迟加载 |
| 项目上下文 | 无 | 无（SWE-bench 场景） | CLAUDE.md / rules / auto memory |
| 每步 observation | `observation_template` 渲染 | Jinja 模板 | 原生 `tool_result` content block |
| 源码可见性 | 完全开源 | 完全开源 | **核心组装逻辑在 `claude.exe` 二进制中** |

> **重要**：`Agent/claude-code/` 仓库主要是插件、hooks、skills 示例；prompt 组装引擎在编译后的 CLI 二进制里（函数名如 `pm()`, `getClaudeMds()`, `setSystemPromptSectionCacheEntry` 等可从 strings 中观测）。

---

## 2. 整体 Prompt 架构（分层）

Claude Code 的每次 API 请求由 **System（多段）+ Messages（对话历史）+ Tools（工具 schema）** 三部分组成：

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 【S】System Prompt — 多段拼接，按 block 设置 cache_control               │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 【S1】Lean / Full 核心指令（静态，可 cache）                      │   │
│  │   "You are Claude Code, Anthropic's official CLI for Claude."    │   │
│  │   工具使用协议、编辑规范、安全规则、agentic loop 行为等            │   │
│  │   估计: ~2,000–3,000 tokens（lean 为默认，Haiku/Sonnet/Opus 4.7-）│   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │ 【S2】SYSTEM_PROMPT_DYNAMIC_BOUNDARY（分界标记）                  │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │ 【S3】动态段（session 内可能变化，分界之后）                       │   │
│  │   git 分支/状态、环境信息、permission mode 等                      │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │ 【S4】用户/项目/组织 Memory（树状分支的主要来源）                  │   │
│  │   ~/.claude/CLAUDE.md → 祖先目录 CLAUDE.md → ./CLAUDE.md         │   │
│  │   CLAUDE.local.md、.claude/rules/*.md、auto memory (MEMORY.md)   │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │ 【S5】Skills 摘要 + Hooks 注入（SessionStart 等）                 │   │
│  │   skill_listing attachment 中的技能名与 whenToUse 摘要             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────┤
│ 【M】Messages — 对话历史（随 API Turn 线性增长）                         │
│   user(text) → assistant(text+tool_use) → user(tool_result) → ...      │
│   + 各类 attachment 在发送前注入为 user 侧上下文                         │
├─────────────────────────────────────────────────────────────────────────┤
│ 【T】Tools — API tools 参数（不在 messages 文本中）                      │
│   ~34 个内置工具类型（见 sdk-tools.d.ts）                                │
│   MCP 工具 schema 可通过 ToolSearch 延迟加载，减少初始 context           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.1 System Prompt 各段来源

| 部分 | 来源 | 跨 Session | 跨项目 |
|------|------|-----------|--------|
| 【S1】核心指令 | `claude.exe` 内置（`CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT` / full） | ✅ 相同 | ✅ 相同 |
| 【S3】动态段 | 运行时采集（git、cwd 等） | ❌ 可能变 | 按 cwd 变 |
| 【S4】CLAUDE.md | `getClaudeMds()` 目录树 walk-up | 按用户/组织 | **按项目目录树分支** ★ |
| 【S4】Auto memory | `.claude/projects/<cwd>/memory/MEMORY.md` | 按 repo | 按 repo |
| 【S5】Skills | `.claude/commands/`、`.claude/agents/`、插件 | 按项目配置 | 按项目 |
| 【S5】Hooks | `SessionStart` → `additionalContext` 等 | 按 settings | 按 settings |

**CLAUDE.md 加载顺序**（官方文档）：从文件系统根向 cwd 逐级向下；同级内 `CLAUDE.local.md` 追加在 `CLAUDE.md` 之后；子目录中的 CLAUDE.md **按需加载**（Claude 读取该目录文件时才注入）。

### 2.2 Tools 的组织方式

工具定义来自 `sdk-tools.d.ts`（由 JSON Schema 自动生成），主要 Input 类型包括：

```
Agent, Bash, FileRead, FileEdit, FileWrite, Glob, Grep,
WebFetch, WebSearch, AskUserQuestion, TodoWrite,
EnterPlanMode, ExitPlanMode, TaskCreate/Get/Update/List,
Workflow, Mcp, NotebookEdit, Cron*, Worktree*, REPL, ...
```

特点：

1. **走 API `tools` 参数**，不嵌入 system prompt 文本（与 SWE-agent 07.yaml 不同）。
2. **ToolSearch**（`ENABLE_TOOL_SEARCH`）：MCP 等大型 schema 默认延迟加载；Claude 通过 `ToolSearch` 工具按需拉取完整定义，初始 context 仅保留工具名。
3. **Prompt caching**：system 各 block 可设 `cache_control: { type: "ephemeral" }`（5min 或 1h TTL）；二进制中有 `setSystemPromptSectionCacheEntry` / `getSystemPromptSectionCache` 按 section 哈希追踪。

---

## 3. Turn 0：Session 启动后的第一次 API 调用

Turn 0 是 session 中**第一次**模型调用。此时 messages 历史为空（或仅含 resume 带来的历史），prompt 由 system + tools + 首条 user 消息 + 启动 attachment 构成。

### 3.1 完整结构（首次 User Turn 的 API Turn 0）

以本地 session `38f6f62a-...`（cwd: `/share/dai-sys/zhoulongsheng/agentkv`）为例：

```
┌──────────────────────────────────────────────────────────────────┐
│ 【S1–S5】System Prompt 全段                                       │
│   lean 核心指令 + DYNAMIC_BOUNDARY + git/环境 + CLAUDE.md 等       │
│   （本仓库若无 CLAUDE.md，【S4】为空或仅 ~/.claude/CLAUDE.md）     │
├──────────────────────────────────────────────────────────────────┤
│ 【T】Tools 定义                                                   │
│   内置 ~34 工具 schema + 已启用 MCP 工具（或 ToolSearch 占位）   │
│   估计: 数千–数万 tokens（ToolSearch 开启时 MCP 部分可延迟）      │
├──────────────────────────────────────────────────────────────────┤
│ 【U0】User Message — 用户首条输入                                 │
│                                                                    │
│   role: user                                                       │
│   content: "请你查看一下现在的目录文件都是什么 熟悉一下文件架构"    │
│   （26 字符；JSONL 中为字符串 content，非 block 数组）              │
├──────────────────────────────────────────────────────────────────┤
│ 【A0】启动 Attachment（JSONL type=attachment，注入 user 侧）       │
│                                                                    │
│   skill_listing: 13 个 skill 的名称与 whenToUse 摘要 (~4.7KB)      │
│   selected_lines_in_ide: Cursor 中选中的代码片段 (~2.8KB)          │
│   （后续 User Turn 还可能出现 task_reminder, opened_file_in_ide,   │
│    directory, file, plan_mode 等）                                 │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 JSONL 转录 vs 实际 API Payload

本地 `~/.claude/projects/.../*.jsonl` **不是** API 请求的 1:1 副本，而是事件流：

| JSONL `type` | 含义 | 对应 API 侧 |
|--------------|------|------------|
| `user` | 用户消息或 tool_result | `messages[]` 中的 user role |
| `assistant` | 模型回复 | `messages[]` 中的 assistant role |
| `attachment` | IDE/环境附加上下文 | 组装进下一次 API 调用的 user 侧 |
| `system` | 元事件（`turn_duration`, `compact_boundary` 等） | 不直接进入 messages |
| `mode` / `permission-mode` | 权限模式变更 | 影响后续行为，可能更新 system 动态段 |

因此 token 精确值需从 API usage（`cache_read_input_tokens`, `cache_creation_input_tokens`）或 `/context` 获取；JSONL 中的 `usage` 字段在本机 session 中常为 `{0, 0}` 占位。

---

## 4. Tool Step：Agentic Loop 内的增量

用户发送首条消息后，Claude 进入 agentic loop。每一步 **Tool Step** 在 API 层面 = 上一次完整 history **加上** 新的 assistant 与 user 消息。

### 4.1 单步结构

```
┌──────────────────────────────────────────────────────────────────┐
│ 【S】【T】System + Tools                    （与上一步相同）         │
│ 【H】已有 Messages History                  （累积，前缀不变）     │
├──────────────────────────────────────────────────────────────────┤
│ 【E】Assistant Message（新增）                                     │
│                                                                    │
│   content: [                                                       │
│     { "type": "text", "text": "..." },        // 可选，常为空       │
│     { "type": "tool_use", "name": "Bash",                         │
│       "input": { "command": "...", "description": "..." } }       │
│   ]                                                                │
├──────────────────────────────────────────────────────────────────┤
│ 【F】User Message — tool_result（新增）                          │
│                                                                    │
│   role: user                                                       │
│   content: [                                                       │
│     { "type": "tool_result", "tool_use_id": "...",                 │
│       "content": "命令输出或错误信息..." }                          │
│   ]                                                                │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 实测序列（session 38f6f62a，首条 User Turn 前几步）

| 步骤 | JSONL 事件 | 新增内容 | 约计字符 |
|------|-----------|---------|---------|
| 0 | user_text | 用户问题 | 26 |
| 0+ | attachment ×2 | skill_listing + IDE 选区 | ~7.5K |
| 1 | assistant (text) | 规划说明，无工具 | 2,263 |
| 2 | assistant → tool_result | `Bash` 列目录 | 0 + 2,176 |
| 3 | assistant → tool_result | `Bash` | 0 + 429 |
| 4 | assistant → tool_result | `Bash` tree | 0 + 16,513 |
| 5 | assistant → tool_result | `Bash` | 0 + 15,366 |
| 6 | assistant (text) | 简短过渡 | 25 |
| ... | ... | 更多 Bash 步骤 | ... |
| 末 | assistant (text) | 目录结构总结 | 1,929 |

规律：

- **工具步**：assistant 常只有 `tool_use`（`text_len=0`），结果在下一步 `tool_result` 进入 history。
- **总结步**：assistant 仅 `text`，无 `tool_use`，标志该 User Turn 的 agentic loop 结束。
- **大输出**：Bash/Read 的 `tool_result` 可达 10K+ 字符，是 context 膨胀主因。

### 4.3 相比上一轮 API Turn 增加了什么

| 对比 | 不变部分 | 新增部分 |
|------|---------|---------|
| API Turn 0 → 1 | 【S】【T】 | 【U0】+【A0】attachments |
| API Turn 1 → 2（首次 tool） | 【S】【T】【U0】【A0】 | 【E】assistant(text) |
| API Turn 2 → 3 | 上述全部 | 【E】assistant(tool_use) + 【F】tool_result |
| API Turn k → k+1 | 全部 history 前缀 | 上一步的 assistant + user(tool_result) |

**KV cache 视角**：理想情况下，【S1】lean 段 + 【T】稳定工具 schema 形成**跨 session 可复用前缀**；messages 部分 strictly monotonic 增长，每步只 append 新 block。

---

## 5. 后续 User Turn：用户再次发消息

当用户发送第二条消息时（同一 session），在已有完整 history 基础上追加。

### 5.1 结构变化

```
┌──────────────────────────────────────────────────────────────────┐
│ 【S】【T】System + Tools                                            │
│ 【H】Turn 0 全部 history（含所有 Tool Step）                        │
├──────────────────────────────────────────────────────────────────┤
│ 【U1】新 User Message（新增）                                       │
│   "现在我想在这个目录下展开实验..."（220 字符）                      │
├──────────────────────────────────────────────────────────────────┤
│ 【A1】新 Attachment（新增，按需）                                   │
│   task_reminder, opened_file_in_ide, directory, file, plan_mode... │
├──────────────────────────────────────────────────────────────────┤
│ （随后进入新的 agentic loop：assistant → tool → ...）             │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Attachment 类型（本 session 统计）

| attachment.type | 触发场景 | 对 prompt 的影响 |
|-----------------|---------|-----------------|
| `skill_listing` | session 启动 / 技能变更 | 注入全部 skill 摘要（可达数千 tokens） |
| `selected_lines_in_ide` | IDE 选中代码 | 注入文件路径 + 选区内容 |
| `opened_file_in_ide` | IDE 打开文件 | 提示当前打开文件路径 |
| `task_reminder` | TodoWrite 相关 | 任务列表提醒 |
| `directory` | @ 目录或探索 | 目录 listing 快照 |
| `file` | @ 文件 | 文件内容或引用 |
| `plan_mode` | 进入 Plan 模式 | plan 文件路径与模式说明 |
| `queued_command` | 队列命令 | 排队的用户指令 |

**与 mini-swe-agent 对比**：SWE-bench agent 的 observation 一律经固定 XML 模板渲染；Claude Code 的 attachment 种类更多，且与 IDE 状态强绑定，**前缀结构更不规则**。

---

## 6. 特殊机制对 Prompt 的影响

### 6.1 Context Compaction（`/compact` 或自动）

当 context 接近上限时，Claude Code 会：

1. 先清除较旧的 **tool 输出**；
2. 必要时 **摘要** 早期对话；
3. 在 JSONL 中写入 `system` / `subtype: compact_boundary` 标记。

Compaction **破坏** strict prefix monotonicity：history 被替换为摘要后，后续 API Turn 的 prefix 与 compaction 前不同。持久规则应写在 **CLAUDE.md**，而非依赖早期对话。

### 6.2 Subagent（`Agent` 工具 / Task）

Subagent 在 **独立 context window** 中运行：

- 主 session history **不包含** subagent 内部的 tool 循环；
- Subagent 结束后仅返回 **摘要** 到主 session；
- Subagent 可有独立 system prompt（如 `.claude/agents/*.md` 中的 `systemPrompt`）。

KV 影响：subagent session 与主 session **不共享** messages prefix；但可能共享同一项目的 CLAUDE.md 分支。

### 6.3 Plan Mode / Permission Mode

- **Plan mode**：注入 `plan_mode` attachment；限制编辑类工具，prompt 动态段包含 plan 文件路径。
- **Permission mode**（Default / acceptEdits / plan / auto）：影响工具执行策略，可能更新 system 动态段或 tool 行为，不一定改变 messages。

### 6.4 Hooks（SessionStart 示例）

插件 `session-start.sh` 可在启动时注入 `additionalContext`：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "You are in 'explanatory' output style mode..."
  }
}
```

等价于在 session 早期 system 或 user 侧追加一段指令。

---

## 7. 跨 Session 共享前缀与树状分支

### 7.1 连续共享前缀（所有 Claude Code session）

```
根节点: 【S1】lean 核心指令 (~2,000–3,000 tokens)
      + 【T】内置工具 schema（ToolSearch 关闭时含完整 MCP）
```

估计 **连续可 cache 前缀 ~2,000–3,000 tokens**（仅 system 静态段；工具 schema 另计且可能极大）。

### 7.2 树状分支（按项目 / 用户）

```
                    根节点
                    【S1】身份 + 核心指令
                   /          |          \
              项目 A        项目 B       项目 C
           CLAUDE.md_A   CLAUDE.md_B   CLAUDE.md_C
           skills_A      skills_B      skills_C
             /  \          /  \           /  \
           s1  s2        s3  s4         s5  s6
```

分支来源：

1. **CLAUDE.md 目录树**（walk-up + 按需子目录）
2. **Skills 列表**（项目/插件不同）
3. **MCP 配置**（`.mcp.json` / settings 中启用的服务器）
4. **Auto memory**（`.claude/projects/<sanitized-cwd>/memory/`）

### 7.3 与 AgentKV 实验的关联

| 场景 | 可观测前缀 | 说明 |
|------|-----------|------|
| 同 repo 多 session | system + CLAUDE.md + skills | 树状复用 |
| 同 session 多 API Turn | 上述 + 线性 messages | 标准 prefix caching |
| Compaction 后 | 摘要替换 history | prefix 突变，cache miss |
| Subagent | 独立 window | 与主 session 分离 |

---

## 8. API Turn 增量汇总表（通用模板）

| API Turn | 相对上一轮新增 | 是否进入后续 prefix |
|----------|---------------|-------------------|
| 0（session 启动） | 【S】全段 + 【T】+ 【U0】+ 启动 attachments | ✅ system/tools 稳定部分 |
| 1 | 【E】assistant 首次回复（常为 text） | ✅ |
| 2+（tool step） | 【E】tool_use + 【F】tool_result | ✅（compaction 前） |
| 新 User Turn | 【U_n】+ 新 attachments + 新 loop | ✅ |
| Compaction 后 | 摘要替换部分 【H】 | ❌ 前缀断裂 |

---

## 9. 数据来源与验证方法

### 9.1 可读来源

| 来源 | 路径 | 内容 |
|------|------|------|
| 工具 schema | `~/.npm-global/.../claude-code/sdk-tools.d.ts` | 34+ 工具 Input/Output 类型 |
| 官方文档 | [Memory](https://code.claude.com/docs/en/memory), [How it works](https://code.claude.com/docs/en/how-claude-code-works) | CLAUDE.md 加载、context、compaction |
| 二进制 strings | `claude.exe` | `SYSTEM_PROMPT_DYNAMIC_BOUNDARY`, `getClaudeMds`, `cache_control` |
| Session 转录 | `~/.claude/projects/<cwd>/<uuid>.jsonl` | messages / attachment 事件流 |
| 插件示例 | `Agent/claude-code/plugins/` | hooks、subagent system prompt 范例 |

### 9.2 推荐验证命令

```bash
# 查看 context 占用
claude
/context

# 查看 session 文件
ls ~/.claude/projects/-share-dai-sys-zhoulongsheng-agentkv/

# 提取 prompt 相关字符串
strings ~/.npm-global/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe \
  | grep -iE "SYSTEM_PROMPT|DYNAMIC_BOUNDARY|getClaudeMds|cache_control|ToolSearch"
```

### 9.3 局限

1. **无法从 Git 源码直接阅读**完整 system prompt 文本（在二进制中）。
2. **JSONL ≠ API payload**：attachment 注入时机、system 分段 cache 标记需 inference 或 API 日志。
3. **ToolSearch / MCP / 模型选择** 会显著改变 【T】的 token 占用。
4. 本地 session 的 `usage` 字段可能为 0，不宜用于 token 计量。

---

## 10. 与 docs/03、SWE-agent 分析的对照

| 文档 | 框架 | Turn 0 核心 | 每步增量 |
|------|------|-------------|---------|
| `docs/03_prompt_structure.md` | mini-swe-agent | system + instance_template | assistant + observation (XML) |
| `results/.../SWE-agent/prompt_structure_analysis.md` | SWE-agent | system + demo + instance | assistant + observation (Jinja) |
| **本文档** | Claude Code | 多层 system + tools + user + attachments | assistant(text/tool_use) + tool_result |

Claude Code 的 prompt 组织**更分层、更动态**：静态可 cache 前缀集中在 lean system；项目差异通过 CLAUDE.md 树引入分支；对话历史以原生 Anthropic messages 格式线性增长，并辅以大量 IDE attachment 与 compaction 机制。

---

## 参考

- [Claude Code Memory / CLAUDE.md](https://code.claude.com/docs/en/memory)
- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)
- 本仓库 `docs/04_agent_framework_comparison.md` §1.4、§3.2
- 本仓库 `Agent/claude-code/plugins/plugin-dev/skills/agent-development/references/agent-creation-system-prompt.md`
