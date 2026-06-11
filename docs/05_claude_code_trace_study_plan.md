# Claude Code 跨 Session KV Cache 复用 — Trace Study 实验方案

> 最后更新：2026-06-11
> 关联文档：[cross_session_kv_cache_analysis.md](results/SWE-bench_Lite/claude-code/cross_session_kv_cache_analysis.md)
> 关联文档：[04_agent_framework_comparison.md](docs/04_agent_framework_comparison.md)

---

## 1. 研究背景

### 1.1 问题

在 agent 推理场景下，多个 agent session 共享大量 prompt 前缀（system prompt、tool schemas、项目配置等），但现有 serving 框架只支持 session 内跨 turn 的 KV Cache 复用，无法跨 session 复用。

### 1.2 前置分析结论

对四个 agent 框架的 prompt 结构分析表明：

| 框架 | 共享前缀 | 树状结构 | 分支来源 |
|------|---------|---------|---------|
| mini-swe-agent | 27 tokens | ❌ 扁平 | 无 |
| SWE-agent (07.yaml) | 6,531 tokens | ❌ 扁平 | 无 |
| **Claude Code** | **12,000-30,000 tokens** | **✅ 树状** | **CLAUDE.md (按项目)** |
| Codex CLI | 4,395 tokens | ✅ 树状 | AGENTS.md (按项目) |

Claude Code 的树状结构来自项目级 CLAUDE.md 注入：不同项目的 session 共享 L0（system prompt + tool schemas），同项目的 session 额外共享 L1（项目级 CLAUDE.md + 技能 + Memory）。

### 1.3 本实验目标

用 Claude Code 作为实验载体，通过 trace study 量化：
1. 树状跨 session KV Cache 复用的特征（L0/L1 前缀长度、缓存命中率）
2. 跨 session 复用的收益（节省的 prefill 计算量和费用）
3. CLAUDE.md 大小对收益的影响（消融实验）
4. 与扁平架构的对比

---

## 2. 实验场景

### 场景 S1：单项目多 Session（基线 — TTL 过期）

**目标**：测量 session 内缓存命中 vs 跨 session 缓存未命中（5min TTL 过期后的冷启动）

**设定**：
- 项目：`claude-code-repo`（有 CLAUDE.md + 技能定义，L1 较大）
- 任务：`"Find all TypeScript files that define tool schemas and list their names and line counts."`
- 模型：`claude-sonnet-4-6`
- 3 个独立 session，间隔 **≥ 7 分钟**
- 每个 session：`claude -p --output-format stream-json --model claude-sonnet-4-6 --dangerously-skip-permissions "TASK"`

**预期结果**：

| Session | Turn | `cache_read` | `cache_creation` | 说明 |
|---------|------|-------------|-----------------|------|
| 1 | Turn 1 | 0 | L0+L1 | 冷启动，写入 L0+L1 缓存 |
| 1 | Turn 2+ | >0（session 内） | 0 | session 内前缀命中 |
| 2 | Turn 1 | **0** | L0+L1 | 5min TTL 过期，跨 session 未命中 |
| 2 | Turn 2+ | >0（session 内） | 0 | session 内前缀命中 |

**量化指标**：session 内缓存命中率、首 turn prefill 开销占比

### 场景 S2：单项目多 Session（1h TTL 内）

**目标**：量化 Claude Code 现有 1h 缓存能恢复多少 L0+L1 前缀

**设定**：
- 同 S1，但 session 间隔 **≤ 2 分钟**（在 1h TTL 窗口内）
- 3 个 session

**预期结果**：

| Session | Turn | `cache_read` | `cache_creation` | 说明 |
|---------|------|-------------|-----------------|------|
| 1 | Turn 1 | 0 | L0+L1 | 冷启动 |
| 1 | Turn 2+ | >0 | 0 | session 内命中 |
| **2** | **Turn 1** | **≈ L0+L1** | **0** | **跨 session 命中！** |
| 2 | Turn 2+ | >0 | 0 | session 内命中 |

**量化指标**：1h TTL 内的跨 session 命中率、L0+L1 前缀的 token 数

### 场景 S3：多项目跨 Session（树状分支的核心验证）

**目标**：测量不同项目 session 之间的 L0 共享 vs L1 差异

**设定**：
- 项目 A：`SWE-agent`（无 CLAUDE.md，L1 ≈ 0）
- 项目 B：`claude-code-repo`（有 CLAUDE.md + 技能，L1 ≈ 2,000 tokens）
- 先运行项目 A 的 session，**2 分钟内**运行项目 B 的 session
- 任务：`"List the main source files and describe the project structure."`

**预期结果**：

| Session | Turn 1 `cache_read` | Turn 1 `cache_creation` | 说明 |
|---------|---------------------|------------------------|------|
| A (SWE-agent) | 0 | L0 | 冷启动 |
| **B (claude-code-repo)** | **≈ L0** | **≈ L1** | **L0 命中，L1 缓存断裂需新写** |

**关键验证**：`cache_read` 量 ≈ L0 大小，`cache_creation` 量 ≈ L1 大小，**证明树状前缀共享的存在**

### 场景 S4：CLAUDE.md 大小消融

**目标**：隔离 CLAUDE.md 对 L1 前缀和跨 session 收益的贡献

**设定**：
- 同一项目（`SWE-agent`），3 种 CLAUDE.md 配置：
  - S4a：`--bare`（无 CLAUDE.md，L1 = 0）
  - S4b：合成小 CLAUDE.md（~500 tokens，包含代码规范）
  - S4c：合成大 CLAUDE.md（~4,000 tokens，包含代码规范+架构+测试方法）
- 每种配置 2 个 session（2 分钟内）

**预期结果**：

| 配置 | L1 估计 | 跨 session `cache_read` | 跨 session `cache_creation` |
|------|---------|------------------------|---------------------------|
| S4a (bare) | 0 | ≈ L0 | 0 |
| S4b (500 tk) | ~500 | ≈ L0 | ≈ 500 |
| S4c (4000 tk) | ~4,000 | ≈ L0 | ≈ 4,000 |

**量化指标**：CLAUDE.md token 数 vs `cache_creation` 增量的关系（应为线性）

### 场景 S5：MCP 工具消融

**目标**：测量 MCP 工具 schema 对 L0/L1 前缀的影响

**设定**：
- `claude-code-repo`，有/无 `--mcp-config` 各 2 个 session

**预期**：MCP 工具增大 L0（共享），或形成额外 L1 分支（不同 MCP 配置）

---

## 3. 数据采集方案

### 3.1 运行命令模板

```bash
# 通用参数
COMMON_FLAGS="--output-format stream-json --model claude-sonnet-4-6 --dangerously-skip-permissions"

# S1: 单项目，间隔 7min+
for i in 1 2 3; do
  cd /path/to/claude-code-repo
  claude -p $COMMON_FLAGS --session-id "s1-session-$i" \
    "Find all TypeScript files that define tool schemas and list their names and line counts." \
    2>&1 | tee results/S1/session_$i.jsonl
  sleep 420  # 7 分钟
done

# S2: 单项目，2min 内
for i in 1 2 3; do
  cd /path/to/claude-code-repo
  claude -p $COMMON_FLAGS --session-id "s2-session-$i" \
    "Find all TypeScript files that define tool schemas and list their names and line counts." \
    2>&1 | tee results/S2/session_$i.jsonl
  sleep 30  # 30 秒
done

# S3: 多项目
cd /path/to/SWE-agent
claude -p $COMMON_FLAGS --session-id "s3-session-A" \
  "List the main source files and describe the project structure." \
  2>&1 | tee results/S3/session_A.jsonl
sleep 30
cd /path/to/claude-code-repo
claude -p $COMMON_FLAGS --session-id "s3-session-B" \
  "List the main source files and describe the project structure." \
  2>&1 | tee results/S3/session_B.jsonl

# S4a: bare 模式
cd /path/to/SWE-agent
claude -p $COMMON_FLAGS --bare --session-id "s4a-session-1" "Explain the build system and how to run tests." \
  2>&1 | tee results/S4a/session_1.jsonl
sleep 30
claude -p $COMMON_FLAGS --bare --session-id "s4a-session-2" "Explain the build system and how to run tests." \
  2>&1 | tee results/S4a/session_2.jsonl

# S4b/S4c: 先写入合成 CLAUDE.md，再运行（同上）
```

### 3.2 每 Turn 记录字段

| 字段 | 来源 | 说明 |
|------|------|------|
| `session_id` | CLI `--session-id` | 唯一 session 标识 |
| `scenario` | 实验标注 | S1/S2/S3/S4a/S4b/S4c/S5 |
| `project` | 工作目录 | 项目名 |
| `turn_index` | 计数 | 0-indexed |
| `timestamp` | JSONL | API 调用时间 |
| `input_tokens` | `usage.input_tokens` | 未缓存输入 |
| `cache_creation_input_tokens` | `usage.cache_creation_input_tokens` | 缓存写入 |
| `cache_read_input_tokens` | `usage.cache_read_input_tokens` | 缓存读取 |
| `ephemeral_5m_input_tokens` | `usage.cache_creation.ephemeral_5m_input_tokens` | 5min 缓存写入 |
| `ephemeral_1h_input_tokens` | `usage.cache_creation.ephemeral_1h_input_tokens` | 1h 缓存写入 |
| `output_tokens` | `usage.output_tokens` | 输出 tokens |
| `total_input_tokens` | 计算：`input + cache_creation + cache_read` | 总 prompt 大小 |
| `claude_md_size_tokens` | tiktoken | 项目 CLAUDE.md token 数 |
| `has_mcp` | 实验标注 | 是否有 MCP 工具 |

### 3.3 前缀分解测量（一次性，使用 `count_tokens` API）

```python
import anthropic
client = anthropic.Anthropic()

# 逐层测量各组件 token 数
base = client.messages.count_tokens(
    model="claude-sonnet-4-6", messages=[{"role":"user","content":"x"}]
).input_tokens

with_tools = client.messages.count_tokens(
    model="claude-sonnet-4-6", tools=ALL_TOOLS,
    messages=[{"role":"user","content":"x"}]
).input_tokens
L0_tools = with_tools - base

with_system = client.messages.count_tokens(
    model="claude-sonnet-4-6", system=SYSTEM_PROMPT,
    messages=[{"role":"user","content":"x"}]
).input_tokens
L0_system = with_system - base

with_claude_md = client.messages.count_tokens(
    model="claude-sonnet-4-6", system=SYSTEM_PROMPT + CLAUDE_MD,
    messages=[{"role":"user","content":"x"}]
).input_tokens
L1_claude_md = with_claude_md - with_system
```

---

## 4. 核心指标与计算

### 4.1 前缀长度

| 指标 | 计算方式 | 预期范围 |
|------|---------|---------|
| L0 前缀 | tool_schema_tokens + system_prompt_tokens + user_claude_md_tokens | 12,000-20,000 |
| L1 前缀 | project_claude_md_tokens + skills_tokens + memory_tokens + mcp_tokens | 0-8,000 |
| L0+L1 | L0 + L1 | 12,000-30,000 |

### 4.2 缓存命中率

```
session内命中率 = Σ_{turn≥1} cache_read[turn] / Σ_{turn≥1} total_input[turn]

跨session命中率 = cache_read[session_k.turn_0] / total_input[session_k.turn_0]
```

### 4.3 KV Cache 节省量

```
# 无跨 session 缓存（每个 session 独立 prefill）
cost_no_cross = Σ_sessions (首turn_total × 1.0 + Σ_{turn≥1} input × 1.0 + cache_creation × 1.25 + cache_read × 0.1)

# 有跨 session 缓存（L0+L1 从缓存读取）
cost_with_cross = session_1全价 + Σ_{session≥2} (
    cache_read(L0+L1) × 0.1 +    # L0+L1 从缓存读，0.1x 价格
    cache_creation(L1_new) × 1.25 + # L1 差异部分新写
    input × 1.0                     # 动态部分全价
)

savings = cost_no_cross - cost_with_cross
savings_pct = savings / cost_no_cross × 100%
```

### 4.4 CLAUDE.md ROI

```
savings_per_session = L1_tokens × (1.0 - 0.1) × $3.00 / 1,000,000
ROI = savings_per_session / claude_md_token_count
```

### 4.5 树状结构效率

```
# K 个项目，第 p 个项目有 M_p 个 session
total_savings = (Σ M_p - 1) × L0 × 0.9 × price          # L0 共享
             + Σ_p (M_p - 1) × L1_p × 0.9 × price       # L1 组内共享
```

---

## 5. 分析脚本

| 脚本 | 输入 | 输出 | 功能 |
|------|------|------|------|
| `extract_turn_data.py` | stream-json JSONL | CSV (每行一 turn) | 提取 usage 字段，计算 total_input |
| `decompose_prefix.py` | system prompt, tools, CLAUDE.md | CSV (组件, token 数) | 用 count_tokens API 逐层测量 |
| `compute_metrics.py` | turn CSV + prefix CSV | 指标汇总表 | 计算命中率、节省量、ROI |
| `generate_figures.py` | 指标汇总 | 论文图表 | 5 张图 + 1 张表 |

### 图表清单

1. **图1：前缀分解堆叠图** — 各项目 L0-tools / L0-system / L1-claude_md / L2-history 的 token 数
2. **图2：Session 内缓存命中率** — cache_read / total_input 随 turn 变化的折线图
3. **图3：跨 Session 首 Turn 缓存对比** — S1 vs S2 vs S3 的 Turn 1 cache_read 量
4. **图4：CLAUDE.md 大小 vs 节省量** — 散点图 + 线性拟合
5. **图5：前缀树示意图** — L0 → L1 → sessions，标注 token 数和缓存状态
6. **表1：汇总统计** — L0/L1 大小、命中率、节省比例

---

## 6. 测试项目

| 项目 | 语言 | CLAUDE.md | L1 估计 | 用途 |
|------|------|----------|---------|------|
| `SWE-agent` | Python | 无 | 0 | L0-only 基线 |
| `claude-code-repo` | TypeScript | 有（`.claude/commands/`） | ~2,000 | 丰富 L1 |
| SWE-agent + 合成小 CLAUDE.md | Python | ~500 tokens | ~500 | S4b 消融 |
| SWE-agent + 合成大 CLAUDE.md | Python | ~4,000 tokens | ~4,000 | S4c 消融 |

**合成 CLAUDE.md** 需要手工编写，包含代码规范、架构说明、测试方法等内容。

---

## 7. 执行计划

| 阶段 | 内容 | 时间 | 预估费用 (Sonnet) |
|------|------|------|------------------|
| Phase 0 | 环境搭建、脚本编写、冒烟测试 | 1 天 | $0.5 |
| Phase 1 | 前缀分解测量 (decompose_prefix.py) | 0.5 天 | $1.5 |
| Phase 2 | S1 基线实验 | 1 天 | $5 |
| Phase 3 | S2 跨 session (1h TTL) | 1 天 | $5 |
| Phase 4 | S3 多项目跨 session | 1 天 | $4 |
| Phase 5 | S4 CLAUDE.md 消融 | 1 天 | $6 |
| Phase 6 | S5 MCP 消融 | 0.5 天 | $3 |
| Phase 7 | 分析与制图 | 2 天 | $0 |
| **合计** | | **8 天** | **~$25** |

> 基于 claude-sonnet-4-6 定价：$3/M input, $15/M output, 0.1x cache read, 1.25x cache write

---

## 8. 预期结果

### 8.1 跨 Session 缓存命中率预期

| 场景 | 预期命中率 | 原因 |
|------|-----------|------|
| S1 (7min+ 间隔) | 0% | 5min TTL 过期 |
| S2 (1h 内) | 50-70% | L0+L1 从 1h 缓存读取 |
| S3 (不同项目) | 40-60% | 仅 L0 共享，L1 不同导致缓存断裂 |
| S4a (无 CLAUDE.md) | 60-80% | L0 即全部前缀 |
| S4c (大 CLAUDE.md) | 30-50% | L0 占比被 L1 稀释 |

### 8.2 与扁平架构对比

| Agent 系统 | 共享前缀 | 树状 | 跨 session 命中率 | 前缀复用机制 |
|-----------|---------|------|-----------------|------------|
| mini-swe-agent | 27 tokens | 扁平 | ~0% | 无 |
| SWE-agent 07.yaml | 6,531 tokens | 扁平 | ~0% | 无 |
| Claude Code（无跨 session 调度） | 12K-30K | 树状 | 0%（TTL 过期） | 仅 session 内 |
| **Claude Code（1h TTL 内）** | **12K-30K** | **树状** | **30-70%** | **跨 session 树状复用** |

### 8.3 论文贡献

1. **首次量化** agent 场景下的树状跨 session KV Cache 复用特征
2. **实验证明**项目级配置文件（CLAUDE.md/AGENTS.md）是树状前缀共享的自然分支点
3. **消融分析** CLAUDE.md 大小与跨 session 收益的线性关系
4. **与扁平架构的对比**：树状结构的共享前缀是扁平结构的 2-5 倍，跨 session 命中率从 0% 提升到 30-70%

---

## 9. 前置条件与风险

| 前置条件 | 说明 | 解决方案 |
|---------|------|---------|
| 需要 Anthropic API Key | 必须使用 Anthropic 模型才能获取真实的 cache token 数据 | 使用 claude-sonnet-4-6（性价比最高） |
| 需要验证 cache 字段非零 | 当前代理模型返回 cache 字段全为 0 | 冒烟测试确认后再批量运行 |
| CLAUDE.md 合成文件 | S4b/S4c 需要手工编写 | 可从真实项目提取 |
| Session 时间控制 | S2 需要在 1h 内连续运行，S1 需要 7min 间隔 | 脚本自动控制 sleep 时间 |
| 费用控制 | 每个场景 ~$3-6，总计 ~$25 | 先跑冒烟测试，确认数据格式正确后再批量 |

---

## 10. 关键文件索引

| 文件 | 位置 | 用途 |
|------|------|------|
| Claude Code 二进制 | `Agent/claude-code-installed/bin/claude.exe` | 实验运行 |
| Tool 类型定义 | `Agent/claude-code-installed/sdk-tools.d.ts` | 前缀分解 |
| 已有 session 日志 | `~/.claude/projects/-share-dai-sys-zhoulongsheng-agentkv/*.jsonl` | 数据格式参考 |
| claude-code-repo | `Agent/claude-code-repo/` | 有 CLAUDE.md 的测试项目 |
| SWE-agent | `Agent/SWE-agent/` | 无 CLAUDE.md 的测试项目 |
| 前置分析 | `docs/04_agent_framework_comparison.md` | 框架对比 |
| Claude Code 前缀分析 | `results/SWE-bench_Lite/claude-code/cross_session_kv_cache_analysis.md` | L0/L1 结构 |
