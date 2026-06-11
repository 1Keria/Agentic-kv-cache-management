# Agent KV Cache — Trace Study 初步实验报告

> 日期：2026-06-11
> Agent：Claude Code (`Agent/claude-code-installed/bin/claude.exe` v2.1.165)
> API：Anthropic 兼容代理 (`maas-coding-api.cn-huabei-1.xf-yun.com/anthropic`)
> 模型：`xopqwen36v35b`
> 关联文档：[07_trace_study_execution_plan.md](docs/07_trace_study_execution_plan.md)

---

## 1. 实验目标

通过真实运行 2-3 条 Claude Code session，采集每个 turn 的输入/输出 token 数，用**最长公共前缀（LCP）**方法量化跨 session 的 prompt 复用比例。

核心指标：**LCP 占比 = LCP_tokens / 首 turn 总 input_tokens**

---

## 2. 数据采集方法

### 2.1 运行命令

```bash
export ANTHROPIC_BASE_URL="https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic"
export ANTHROPIC_API_KEY="<api_key>"
CLAUDE="/share/dai-sys/zhoulongsheng/agentkv/Agent/claude-code-installed/bin/claude.exe"

$CLAUDE -p "<task>" --output-format stream-json --verbose \
  --model xopqwen36v35b --dangerously-skip-permissions 2>&1
```

### 2.2 数据来源

- **stream-json 输出**：`type=result` 提供聚合数据（`num_turns`, `usage.input_tokens`, `usage.output_tokens`）
- **Session JSONL**：`~/.claude/projects/<sanitized-cwd>/<session_id>.jsonl`，其中 `type=assistant` 事件的 `message.usage` 提供 **per-turn** 的 `input_tokens` / `output_tokens`

### 2.3 重要发现：cache 字段始终为 0

这个代理 API 虽兼容 Anthropic 格式，但**不支持 prompt caching**：
- `cache_read_input_tokens` / `cache_creation_input_tokens` 始终为 0
- `cache_creation.ephemeral_1h_input_tokens` / `ephemeral_5m_input_tokens` 始终为 0

**结论**：无法直接观测缓存命中，只能通过比较首 turn `input_tokens` 来推断前缀共享程度。

---

## 3. 主要实验数据

### 3.1 实验用的 3 个 Session（同项目 agentkv）

| Session ID | 任务 | 首turn input | 首turn output | 末turn input | 末turn output | turns |
|-----------|------|-------------|---------------|-------------|---------------|-------|
| `c4530d51` (S1) | "Read docs/01... and summarize 3 reuse schemes" | 20,109 | 47 | 25,985 | 228 | 2 |
| `6a9498a6` (S2) | 同上（相同任务） | 20,110 | 47 | 25,985 | 276 | 2 |
| `43ae6454` (S3) | "List all Python files in scripts/ dir" | 20,099 | 162 | 20,346 | 73 | 2 |

### 3.2 Per-Turn 详细数据

#### S1 (`c4530d51`) — summarize 3 reuse schemes

| Turn | input_tokens | output_tokens | delta_in | 动作 |
|------|-------------|---------------|----------|------|
| 1 | 20,109 | 47 | — | `tool:Read` (读 01 doc) |
| 2 | 25,985 | 228 | +5,876 | `text(433ch)` (总结回复) |
| **合计** | **46,094** | **275** | | 2 turns |

#### S2 (`6a9498a6`) — 相同任务

| Turn | input_tokens | output_tokens | delta_in | 动作 |
|------|-------------|---------------|----------|------|
| 1 | 20,110 | 47 | — | `tool:Read` (读 01 doc) |
| 2 | 25,985 | 276 | +5,875 | `text(571ch)` (总结回复) |
| **合计** | **46,095** | **323** | | 2 turns |

#### S3 (`43ae6454`) — 不同任务

| Turn | input_tokens | output_tokens | delta_in | 动作 |
|------|-------------|---------------|----------|------|
| 1 | 20,099 | 162 | — | `tool:Bash` (列 scripts/) |
| 2 | 20,346 | 73 | +247 | `text(167ch)` (统计回复) |
| **合计** | **40,445** | **235** | | 2 turns |

---

## 4. 跨 Session LCP 分析

### 4.1 方法

由于 API 不支持缓存观测，用 **首 turn input_tokens 作为 prompt 大小的近似**：

- 同项目同配置下，system prompt + tools + CLAUDE.md + 环境上下文约 20,100 tokens
- 用户任务描述仅占 ~10-100 tokens（取决于任务长度）
- 两个 session 的 prompt 差异 ≈ 首 turn input_tokens 之差

**LCP 近似**：`LCP ≈ min(session_A.turn1.input, session_B.turn1.input)`

### 4.2 结果

| Session 对 | 首turn in (A) | 首turn in (B) | LCP 估计 | 差异 | LCP 占比 |
|-----------|-------------|-------------|---------|------|---------|
| S1 vs S2（同任务） | 20,109 | 20,110 | 20,109 | 1 token | **100.0%** |
| S1 vs S3（不同任务） | 20,109 | 20,099 | 20,099 | 10 tokens | **99.95%** |
| S2 vs S3（不同任务） | 20,110 | 20,099 | 20,099 | 11 tokens | **99.95%** |

### 4.3 关键发现

1. **同项目下首 turn prompt 几乎 100% 共享**。首 turn ~20,100 tokens 中，system prompt + tools + CLAUDE.md + 环境上下文占了 ~20,090 tokens，而用户任务仅占 ~10 tokens（0.05%）。

2. **即使用户任务不同，前缀差异也极小**。S1（summarize doc）和 S3（list Python files）的首 turn input 仅差 10 tokens，说明 prompt 结构非常稳定，用户任务在 prompt 中的占比极低。

3. **Agent 框架的 prompt 膨胀效应**：首 turn 输入约 20,000 tokens，但用户实际任务描述只有几十个字符（~10 tokens）。这意味着 ~99.95% 的 prompt 是可以跨 session 复用的公共前缀。

---

## 5. Session 内复用

Session 内跨 turn 的 KV Cache 复用（已有机制）：

| Session | Turn1 in | Turn2 in | 增量 | Session内复用率 |
|---------|----------|----------|------|---------------|
| S1 | 20,109 | 25,985 | +5,876 | **77.4%** |
| S2 | 20,110 | 25,985 | +5,875 | **77.4%** |
| S3 | 20,099 | 20,346 | +247 | **98.8%** |

- S1/S2 的 Turn 2 增量大（~5,876 tokens），因为 Read 工具返回了文件内容
- S3 增量小（~247 tokens），因为 Bash 输出少

---

## 6. N-Session 扩展分析

基于平均首 turn input ~20,100 tokens，共享前缀 ~20,090 tokens：

| N sessions | 无跨session缓存 (total prefill) | +跨session缓存 | 节省 tokens | 节省比例 |
|-----------|------------------------------|---------------|------------|---------|
| 2 | 40,200 | 20,110 | 20,090 | **50.0%** |
| 10 | 201,000 | 20,190 | 180,810 | **90.0%** |
| 50 | 1,005,000 | 20,590 | 984,410 | **98.0%** |
| 300 | 6,030,000 | 23,090 | 6,006,910 | **99.6%** |

**关键 insight**：N 越大，跨 session 复用的收益越显著。在 SWE-bench 300 条批量推理场景下，跨 session 缓存可以节省 **99.6% 的 prefill 计算量**。

---

## 7. 其他测试 Session 汇总

为完整性，汇总所有冒烟测试 session 的首 turn 数据：

| Session ID | 首turn input | 首turn output | turns | 备注 |
|-----------|-------------|---------------|-------|------|
| `dbf09723` | 19,362 | 1 | 1 | 简单 "hello" 测试 (astron-code-latest) |
| `f9d25470` | 20,097 | 2 | 1 | 简单 "hello" 测试 (xopqwen36v35b) |
| `2ec49811` | 20,107 | 47 | 2 | "Read doc and tell title" |
| `ca9ccab1` | 20,094 | 70 | 2 | "List all markdown files in docs" (S1) |
| `d4992a64` | 20,095 | 72 | 2 | "List all markdown files in docs" (S2) |
| `45e9316e` | 0* | 0 | 1 | API error (模型名错误) |
| `7108acd2` | — | 0 | 0 | 被中断，无有效数据 |

> `*` 45e9316e: `--model claude-sonnet-4-6` 在这个代理上不支持，返回 API 500 错误，无有效 usage 数据。

所有 xopqwen36v35b 模型的 session 首 turn input 都在 **20,094 ~ 20,110 范围内（仅差 16 tokens）**，说明同项目下的 prompt 结构高度一致。

---

## 8. 讨论与局限

### 8.1 当前方法的局限

1. **非真正的 LCP**：我们只能比较首 turn `input_tokens` 的数值来推断前缀相似度，无法拿到完整的 token 序列做逐 token 比较。真正的 LCP 需要 API 返回 token 级别的 prompt 内容。

2. **cache 字段为 0**：代理 API 不支持 Anthropic 原生 prompt caching，无法直接观测缓存命中。要用真正的 LCP，需要 OpenRouter / Anthropic 直连 API，或者用 OpenAI 的 `cached_input_tokens` 字段。

3. **short tasks**：当前测试用的是简单任务（读文件、列目录），tool output 小。真实 SWE-bench 任务中 tool output 会大得多，Turn 2+ 的增量也会大得多。

### 8.2 下一步

1. **tiktoken 离线分解**：对 Claude Code 的 prompt 各组件用 tiktoken 精确编码，计算 L0（system+tools）+ L1（CLAUDE.md）+ L2（动态）的精确占比
2. **Codex CLI 采集**：`codex exec --json` 返回的 `cached_input_tokens` 可能非零，可以直接观测缓存命中
3. **多项目对比**：跑不同项目目录的 session，验证 CLAUDE.md 差异对前缀的影响

---

## 9. 核心结论

1. **Claude Code 同项目下首 turn prompt 几乎 100% 可复用**（~20,100 tokens 中仅 ~10 tokens 因用户任务不同而变化）
2. **跨 session 缓存收益随 N 线性增长**：N=300 时节省 99.6% prefill
3. **Session 内复用约 77-99%**（取决于 tool output 大小）
4. **代理 API 不支持 prompt caching**，需要换 API 或换方法才能拿到真实 LCP

---

## 参考

- `docs/07_trace_study_execution_plan.md` — 实验执行计划
- `docs/05_claude_code_prompt_structure.md` — Claude Code prompt 结构
- `docs/04_agent_framework_comparison.md` — 四个框架对比
- `results/SWE-bench_Lite/mini-swe-agent/small_batch/analysis/` — 已有 mini-swe-agent 数据
