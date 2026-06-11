# Claude Code Prompt L0/L1/L2 详细分解

> 日期：2026-06-12
> 基于：sympy SWE-bench trace study 的 3 个 session 实测数据
> 关联文档：[09_sympy_trace_study_results.md](09_sympy_trace_study_results.md)

---

## 1. 什么是 L0 / L1 / L2

在跨 session KV Cache 复用研究中，我们把首 turn prompt 按共享范围分为三个层级：

```
┌──────────────────────────────────────────────────────────────────┐
│                        L0 (全局共享前缀)                          │
│  所有 session、所有项目都相同的部分                                │
│  System prompt + Tools schema + 基础行为指令                      │
├──────────────────────────────────────────────────────────────────┤
│                        L1 (项目/用户级前缀)                        │
│  同一项目（或同一用户）的 session 共享，不同项目可能不同            │
│  CLAUDE.md + Memory + Skills + Git/环境信息 + API 格式开销        │
├──────────────────────────────────────────────────────────────────┤
│                        L2 (Session 级动态内容)                     │
│  每个 session 都不同的部分                                        │
│  Problem statement + 时间戳 + 首 turn 模型输出                    │
└──────────────────────────────────────────────────────────────────┘
```

### 为什么用 L0/L1/L2 而不是单一前缀

- **扁平结构的局限性**：传统 KV Cache 复用只支持"完全相同的连续前缀"。如果 prompt 是扁平的（如 mini-swe-agent），只有从头开始完全相同的前缀才能复用，导致复用率极低（仅 2.0%）。
- **树状结构的优势**：Claude Code 的 prompt 天然是树状的——L0 是根节点，L1 是按项目分叉的分支，L2 是叶子。KV Cache 系统可以利用这个树状结构，在不同分支点进行复用。
- **LCP 是更通用的视角**：L0/L1/L2 是 LCP（最长公共前缀）在树状结构下的具体体现。两个 session 的 LCP 长度取决于它们共享到哪个层级。

---

## 2. 数据来源与方法论

### 2.1 input_tokens 的来源

本文档中所有 token 数均来自 **API 服务端返回的 `usage.input_tokens`**。

具体链路：
1. Claude Code 组装完整 prompt（system prompt + messages + tools）
2. 发送给 API 服务端
3. **API 服务端用其 tokenizer 对完整 prompt 编码，返回 `usage.input_tokens`**
4. Claude Code 将此值写入 session JSONL 的 `assistant.message.usage.input_tokens`

**这是模型实际接收的 token 数，不是客户端估算的。**

### 2.2 本实验的 API 情况

本实验使用代理 API（`maas-coding-api.cn-huabei-1.xf-yun.com/anthropic`），底层模型为 `xopqwen36v35b`（Qwen 模型）。因此 `input_tokens` 是用 Qwen 的 tokenizer 编码的结果，与 Anthropic 原生 tiktoken 可能存在差异。

### 2.3 LCP 的计算方法

**LCP（最长公共前缀）= 两个 session 的 prompt token 序列从头部开始完全一致的最长前缀的 token 数。**

精确 LCP 计算使用 Qwen3-8B tokenizer 对可提取的 prompt 组件（problem_statement、skill_listing）进行 tokenization，结合 API 返回的 `input_tokens` 推算。详见 [`docs/11_precise_lcp_calculation.md`](11_precise_lcp_calculation.md)。

**计算方法**：

```
首 turn input = L0 + L1 + PS_tokens + skill_tokens + L2_other

其中:
  L2_other ≈ 30-50 tokens（时间戳 + 日期 + 格式标记）

L0+L1 = 首 turn input - PS - skill - L2_other
      ≈ 20,147 - 95 - 1,022 - 40 ≈ 18,990

LCP(同任务) = L0+L1 + PS + skill ≈ 20,100 (99.8%)
LCP(不同任务) = L0+L1 + PS_LCP(7) ≈ 18,990 (94.0%)
```

**关键发现**：PS（problem_statement）在 prompt 中的位置影响 LCP。PS 出现在 skill_listing 之前，因此不同任务的 PS 分叉会阻断 LCP 延伸到 skill_listing 部分。将 PS 移到末尾可将不同任务的 LCP 从 94.0% 提升到 99.2%。

### 2.4 L0 和 L1 的分离

**L0 和 L1 的精确分离需要跨项目实验数据。** 目前所有 3 个 session 都在同一个项目 (sympy) 下运行，L1 完全共享，无法区分 L0 和 L1 的边界。

跨项目实验可以分离：
- 同用户、不同项目的 session → L0 相同、L1 不同
- 首 turn input 差值 ≈ L1 中项目相关部分的差异
- L0 ≈ 较小项目的首 turn input - 该项目的 L1 - L2

---

## 3. 实测数据

### 3.1 三个 Session 的首 Turn Input

| Session | Instance | 首 Turn input_tokens | 来源 |
|---------|----------|---------------------|------|
| S1 (`d3f04d61`) | sympy-12481 | **20,233** | API 返回 |
| S2 (`20fb6e2a`) | sympy-12481 | **20,147** | API 返回 |
| S3 (`950d11ca`) | sympy-13480 | **20,212** | API 返回 |

### 3.2 首 Turn Input 的一致性

| Session 对 | 差异 (tokens) | 差异比例 |
|-----------|-------------|---------|
| S1 vs S2 | 86 | 0.43% |
| S1 vs S3 | 21 | 0.10% |
| S2 vs S3 | 65 | 0.32% |

差异极小，说明同项目下 L0+L1 部分完全一致，差异仅来自 L2（problem_statement 长度不同、时间戳等）。

### 3.3 可精确计算的值

| 指标 | 值 | 计算方法 |
|------|-----|---------|
| 首 turn input (平均) | **20,197** | (20233+20147+20212)/3 |
| 首 turn input 范围 | **20,147 - 20,233** | 实测 |
| 首 turn 间最大差值 | **86 tokens** | max(S1,S2,S3) - min(S1,S2,S3) |
| **LCP (同项目)** | **≥ 20,147** | min(首turn input)，因为 LCP 至少包含 L0+L1 |
| **LCP 占比 (同项目)** | **≥ 99.57%** | 20147/20233 |

> 注意：LCP ≥ min(首turn input) 是因为 LCP 包含 L0+L1 的全部，而 L0+L1 占了首 turn input 的绝大部分。更准确地说，LCP = L0+L1，而 L0+L1 ≈ 首 turn input - L2。由于 L2 很小（~100-300 tokens），LCP 占比 ≈ 98-99%。

### 3.4 L2 的估算

L2（session 级动态内容）的组成：

| 组件 | S1 | S2 | S3 | 测量方式 |
|------|-----|-----|-----|------|
| Problem statement | 95 tokens (425 chars) | 95 tokens (425 chars) | 154 tokens (412 chars) | Qwen3-8B tokenizer |
| Skill listing | 1,022 tokens (4,399 chars) | 1,022 tokens (4,399 chars) | 1,022 tokens (4,399 chars) | Qwen3-8B tokenizer |
| 其他动态内容 | ~30-50 tokens | ~30-50 tokens | ~30-50 tokens | 估计（时间戳、日期、格式标记） |
| **L2 总计** | **≈ 1,150-1,170** | **≈ 1,150-1,170** | **≈ 1,200-1,226** | |

> 精确 LCP 计算详见 [`docs/11_precise_lcp_calculation.md`](11_precise_lcp_calculation.md)。

L2 的精确测量方法：
- PS 和 skill_listing 的 token 数用 Qwen3-8B tokenizer 精确计算
- L2_other 从首 turn input 的差值推断：S3 vs S2 差 65 tokens，其中 PS 差 59 tokens，所以 L2_other 差 6 tokens
- L2_other 的绝对值估计约 30-50 tokens

---

## 4. L0/L1/L2 的定性组成

以下列出各层级包含的具体内容。**token 数为基于文档分析的估计值，非实测数据**，用 `?` 标注。

### 4.1 L0：全局共享前缀

所有 Claude Code session 都相同的部分，来自编译后的二进制文件和工具定义文件。

| 组件 | 估计 tokens | 来源 | 说明 |
|------|-----------|------|------|
| Lean Core System Prompt | ? | `claude.exe` 内置 | "You are Claude Code..." + 工具使用协议 + 编辑规范 + 安全规则 + agentic loop 行为 |
| Tools Schema (26个内置工具) | ? | `sdk-tools.d.ts` | Bash, Read, Edit, Write, Glob, Grep, WebSearch, WebFetch, Agent, Workflow, Task*, Plan*, Ask*, Cron*, Worktree*, Skill, NotebookEdit, ScheduleWakeup 等 |
| ToolSearch 占位符 | ? | `claude.exe` 内置 | MCP 工具延迟加载的占位声明 |
| Dynamic Boundary 标记 | ? | `claude.exe` 内置 | 分隔静态/动态 system prompt 段的标记字符串 |

**L0 的内容是确定的**（所有 session 相同），但各组件的精确 token 数需要从 API 或 tokenizer 获取，目前无法直接测量。

**26 个内置工具的完整列表**（来自 init 事件）：

```
Task, AskUserQuestion, Bash, CronCreate, CronDelete, CronList,
Edit, EnterPlanMode, EnterWorktree, ExitPlanMode, ExitWorktree,
NotebookEdit, Read, ScheduleWakeup, Skill, TaskCreate, TaskGet,
TaskList, TaskOutput, TaskStop, TaskUpdate, WebFetch, WebSearch,
Workflow, Write
```

### 4.2 L1：项目/用户级前缀

同一项目（或同一用户）的 session 共享，不同项目可能不同，形成树状分支。

| 组件 | 估计 tokens | 来源 | 是否按项目变化 |
|------|-----------|------|-------------|
| ~/.claude/CLAUDE.md | ? | 用户全局配置 | ❌ 按用户相同 |
| Memory 文件 | ? | `.claude/projects/<cwd>/memory/` | ✅ 按项目目录不同 |
| Skills 摘要 (12个) | ? | `.claude/commands/` + 插件 | ✅ 按项目配置不同 |
| Slash Commands 列表 (28个) | ? | 二进制内置 + 项目配置 | 部分按项目不同 |
| Agents 列表 (5个) | ? | 二进制内置 + 项目配置 | 部分按项目不同 |
| Git Status + Branch | ? | `git` 命令 | ✅ 按项目不同 |
| CWD + 环境信息 | ? | 运行时 | ✅ 按项目不同 |
| Permission Mode | ? | 启动参数 | ❌ 按启动参数相同 |
| API 格式开销 | ? | Anthropic API | ❌ 固定 |

**12 个 Skills 的完整列表**（来自 init 事件）：

```
deep-research, update-config, verify, debug, code-review,
simplify, batch, fewer-permission-prompts, loop, claude-api,
run, run-skill-generator
```

**5 个 Agents 的完整列表**（来自 init 事件）：

```
claude, Explore, general-purpose, Plan, statusline-setup
```

**28 个 Slash Commands 的完整列表**（来自 init 事件）：

```
deep-research, update-config, verify, debug, code-review,
simplify, batch, fewer-permission-prompts, loop, claude-api,
run, run-skill-generator, clear, compact, context, heapdump,
init, reload-skills, review, security-review, usage, insights,
goal, team-onboarding
```

### 4.3 L2：Session 级动态内容

每个 session 都不同的部分，无法跨 session 复用。

| 组件 | Token 数 (Qwen3-8B) | 说明 |
|------|---------------------|------|
| Problem Statement | S1/S2: 95, S3: 154 | SWE-bench issue 描述，每个 instance 不同 |
| Skill Listing | 1,022 (三个 session 相同) | 注入到 user message 中的附件 |
| 时间戳等 | ~30-50 | 每次 session 启动时间不同 |
| **L2 总计** | **≈ 1,150-1,226** | |

> 注意：Skill listing 虽然在同项目下相同，但它出现在 PS 之后，因此 PS 的分叉会阻断 LCP 延伸到 skill_listing。详见 [`docs/11_precise_lcp_calculation.md`](11_precise_lcp_calculation.md) §6。

---

## 5. 树状前缀结构

### 5.1 同项目下的前缀树

本次实验中，3 个 session 都在 sympy 项目下运行：

```
                      根节点
                    L0 (所有 session 相同)
                        |
                      L1 (sympy 项目)
                        |
            ┌───────────┼───────────┐
           S1          S2          S3
        L2(12481)   L2(12481)   L2(13480)

LCP(S1, S2) = L0 + L1 = 首 turn input - L2 ≈ 20,100
LCP(S1, S3) = L0 + L1 = 首 turn input - L2 ≈ 20,100
```

### 5.2 不同项目下的前缀树（理论）

```
                      根节点
                    L0 (所有 session 相同)
                        |
            ┌───────────┼───────────┐
        项目 sympy    项目 django   项目 codex
          L1(sympy)    L1(django)   L1(codex)
            |            |            |
          ┌─┴─┐        ┌─┴─┐        ┌─┘
         S1   S3      S4   S5       S6

LCP(S1, S3) = L0 + L1(sympy)     ← 同项目，L1 共享
LCP(S1, S4) = L0                  ← 不同项目，L1 不同
LCP(S4, S5) = L0 + L1(django)    ← 同项目，L1 共享
```

### 5.3 Session Forking 场景

L0/L1/L2 模型的一个重要推广：**session forking**。

```
Session A: [L0] [L1] [Turn1] [Turn2] ... [TurnK] → [Turn K+1] → [Turn K+2]
Session B: [L0] [L1] [Turn1] [Turn2] ... [TurnK] → [Turn K+1'] → [Turn K+2']

LCP(A, B) = L0 + L1 + Turns 1~K 的全部对话历史
```

在 forking 场景下，LCP 可以远超 L0+L1，延伸到对话历史。这是传统 L0/L1/L2 静态分解无法覆盖的额外复用机会，也是 LCP 方法的核心优势。

---

## 6. 需要补充的实验

### 6.1 跨项目实验（分离 L0 和 L1）

**方法**：在同一用户下，跑两个不同项目（如 sympy 和 django）的 session。

**预期结果**：
- 两个项目的首 turn input 差值 ≈ L1 中项目相关部分的差异
- L0 ≈ 较小项目的首 turn input - 该项目的 L1 - L2

### 6.2 CLAUDE.md 消融实验（量化 L1 中项目级配置的贡献）

**方法**：在同一项目下，分别跑有/无项目级 CLAUDE.md 的 session。

**预期结果**：
- 首 turn input 差值 ≈ CLAUDE.md 的 token 数

### 6.3 真实 Anthropic API（获取 cache 字段）

**方法**：用支持 prompt caching 的 Anthropic 直连 API 运行 session。

**预期结果**：
- `cache_read_input_tokens` 非零，可以直接观测跨 session 缓存命中
- 验证 LCP 估计与实际缓存命中量的一致性

---

## 参考

- [docs/05_claude_code_prompt_structure.md](05_claude_code_prompt_structure.md) — Claude Code prompt 组织结构
- [docs/09_sympy_trace_study_results.md](09_sympy_trace_study_results.md) — Sympy trace study 结果
- [docs/04_agent_framework_comparison.md](04_agent_framework_comparison.md) — 四个框架对比
- [Anthropic Prompt Caching 文档](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
