# Agent KV Cache 跨 Session 复用 — Trace Study 实验计划

> 最后更新：2026-06-11
> 目标：量化跨 session 共享前缀占首 turn 的比例，以及在全 session 生命周期中的增量收益
> 原则：最小实验 → 快速出数据 → 用已有数据合成全生命周期视角

---

## 1. 核心要回答的问题

### Q1：跨 session 共享前缀占首 turn prompt 多大比例？

```
首turn复用比例 = 跨session共享前缀tokens / 首turn总input_tokens
```

- 比例高（>50%）→ 跨 session 缓存有很大收益，值得做
- 比例低（<10%）→ 跨 session 缓存意义不大

### Q2：加入跨 session 缓存后，全生命周期能额外省多少？

```
已有：session内复用率 = 87.7%（mini-swe-agent, 6条数据）

新增量化：
  跨session额外节省 = (N-1) × 首turn共享前缀tokens
  全生命周期节省 = session内节省 + 跨session额外节省
  增量比例 = 跨session额外节省 / 无缓存总prefill
```

### Q3：不同框架的复用比例差异有多大？

对比 mini-swe-agent / SWE-agent / Codex CLI / Claude Code 的首 turn 复用比例，看树状结构 vs 扁平结构的差异。

---

## 2. 已有数据（可直接复用）

### 2.1 mini-swe-agent（6 条 astropy，10 步限制）

来自 `results/SWE-bench_Lite/mini-swe-agent/small_batch/analysis/`

| 指标 | 值 |
|------|-----|
| 首 turn 平均 prompt_tokens (API) | ~1,753 |
| 跨 session 共享前缀（传统前缀缓存） | ~33 tokens（2.0%） |
| 跨 session 共享前缀（Prompt 重排后） | ~1,250 tokens（71.3%） |
| Session 内复用率 | 87.7% |
| 无缓存总 prefill | 139,139 tokens |
| Session 内缓存后总 prefill | 27,552 tokens |
| + 跨 session 缓存后总 prefill | 21,423 tokens |
| 跨 session 增量节省 | 6,109 tokens（4.4%） |

**问题**：mini-swe-agent 是扁平结构，共享前缀极短（27 tokens tiktoken），6 条数据且步数少。

### 2.2 需要补充的数据

| 框架 | 需要采集 | 目的 |
|------|---------|------|
| **Claude Code** | 首turn input_tokens, cache_read/cache_creation | 直接观测跨session缓存命中，验证树状结构 |
| **Codex CLI** | 首turn input_tokens, 前缀token分解 | 开源审计，验证树状结构的普遍性 |
| **SWE-agent** | 首turn prompt结构分析 | 对比扁平架构的大前缀（6,531 tokens） |
| **mini-swe-agent** | 全量300条运行（如时间允许） | 更大样本量 |

---

## 3. 量化方法

### 3.1 方法一：直接观测（Claude Code）

Claude Code 的 Anthropic API 返回 `cache_read_input_tokens` 和 `cache_creation_input_tokens`，可以直接观测缓存命中。

```
首turn复用比例 = cache_read[session2.turn1] / input_tokens[session2.turn1]
```

**前提**：Session 1 已写入缓存，Session 2 在 TTL 内启动。

### 3.2 方法二：tiktoken 离线计算（所有框架）

对于任何框架，只要知道 prompt 的组成结构，就可以 tiktoken 计算各部分 token 数：

```
首turn复用比例 = (L0 + L1) / 首 turn 总 input_tokens

其中：
  L0 = 所有 session 共享的前缀（base instructions / system prompt + 内置工具 schema）
  L1 = 同项目 session 共享的前缀（AGENTS.md / CLAUDE.md + 项目级 skills/plugins）
  首 turn 总 input = L0 + L1 + L2（动态内容：environment context + 用户消息）
```

**优势**：不依赖 API 缓存功能，可以分析任何框架。

### 3.3 方法三：API usage 推断

首 turn 的 `input_tokens` 减去 tiktoken 估计的 L2（动态部分），余数即为 L0+L1：

```
L0 + L1 ≈ input_tokens[turn0] - tiktoken(environment_context + user_message)
```

---

## 4. 实验设计

### 4.1 优先级排序

| 优先级 | 实验 | 目的 | 耗时 | 费用 |
|--------|------|------|------|------|
| **P0** | Claude Code 冒烟测试 | 验证 cache 字段非零 | 2 min | $0.05 |
| **P1** | Claude Code A1: 同项目2 session | 量化首turn复用比例 | 3 min | $0.3 |
| **P2** | Claude Code A2: 不同项目2 session | 验证L0共享+L1差异 | 3 min | $0.3 |
| **P3** | Codex CLI B1: 前缀token精确分解 | tiktoken逐层计算 | 5 min | $0 |
| **P4** | Codex CLI B2: 同项目2 session | 对比首turn input_tokens | 3 min | $0.1 |
| **P5** | SWE-agent 前缀分析 | 补充扁平架构数据 | 10 min | $0 |

### 4.2 实验 A1：Claude Code 同项目 2 session

**目的**：量化首 turn 复用比例

```bash
# Session 1：冷启动
cd /share/dai-sys/zhoulongsheng/agentkv
claude -p "List all markdown files in the docs directory" \
  --output-format stream-json --verbose \
  --model claude-sonnet-4-6 \
  --dangerously-skip-permissions \
  2>&1 | tee /tmp/a1_session1.jsonl

# 等待 30 秒（1h TTL 内）
sleep 30

# Session 2：跨 session 缓存命中
cd /share/dai-sys/zhoulongsheng/agentkv
claude -p "List all markdown files in the docs directory" \
  --output-format stream-json --verbose \
  --model claude-sonnet-4-6 \
  --dangerously-skip-permissions \
  2>&1 | tee /tmp/a1_session2.jsonl
```

**要提取的数据**：

| 指标 | Session 1 Turn 1 | Session 2 Turn 1 | 说明 |
|------|-----------------|-----------------|------|
| `input_tokens` | X₁ | X₂ | 总输入 |
| `cache_read_input_tokens` | 0 | R₂ | **关键：跨session命中量** |
| `cache_creation_input_tokens` | C₁ | C₂ | 缓存写入量 |
| `output_tokens` | O₁ | O₂ | 输出 |

**计算**：

```
首turn复用比例 = R₂ / X₂

L0+L1 估计 ≈ R₂  (跨 session 缓存命中的就是 L0+L1)
L2 估计 ≈ X₂ - R₂  (未命中的部分 = 动态内容)

如果 R₂/X₂ > 50% → 跨 session 缓存很有意义
如果 R₂/X₂ > 80% → 跨 session 缓存收益巨大
```

### 4.3 实验 A2：Claude Code 不同项目 2 session

**目的**：量化 L0 vs L1 的比例，验证树状结构

```bash
# Session A：项目 agentkv（有 CLAUDE.md）
cd /share/dai-sys/zhoulongsheng/agentkv
claude -p "Describe the project structure in 3 sentences" \
  --output-format stream-json --verbose \
  --model claude-sonnet-4-6 --dangerously-skip-permissions \
  2>&1 | tee /tmp/a2_sessionA.jsonl

sleep 30

# Session B：项目 SWE-agent（无 CLAUDE.md）
cd /share/dai-sys/zhoulongsheng/agentkv/Agent/SWE-agent
claude -p "Describe the project structure in 3 sentences" \
  --output-format stream-json --verbose \
  --model claude-sonnet-4-6 --dangerously-skip-permissions \
  2>&1 | tee /tmp/a2_sessionB.jsonl
```

**计算**：

```
L0 估计 ≈ cache_read[B.turn1]    (跨项目共享的部分)
L1_A 估计 ≈ cache_creation[A.turn1] - L0  (项目A独有的部分)
         或 ≈ cache_read[A2.turn1] - cache_read[B.turn1]  (如果有A2)

L0占比 = L0 / (L0 + L1_A + L2)
L1占比 = L1_A / (L0 + L1_A + L2)

树状分支比 = L0 / (L0 + L1)  → 这个比例高说明L0是主体，树状结构共享面广
```

### 4.4 实验 B1：Codex CLI 前缀 token 精确分解

**目的**：不依赖 API，用 tiktoken 精确计算各层 token 数

```python
import tiktoken
enc = tiktoken.encoding_for_model("gpt-4")

# 1. Base Instructions
base = open("Agent/codex/codex-rs/protocol/src/prompts/base_instructions/default.md").read()
L0_base = len(enc.encode(base))

# 2. AGENTS.md（项目级）
agents_md = open("Agent/codex/AGENTS.md").read()
L1_agents = len(enc.encode(agents_md))

# 3. Permissions（按配置组合）
sandbox_ws = open("Agent/codex/codex-rs/prompts/templates/permissions/sandbox_mode/workspace_write.md").read()
approval_of = open("Agent/codex/codex-rs/prompts/templates/permissions/approval_policy/on_failure.md").read()
approval_or = open("Agent/codex/codex-rs/prompts/templates/permissions/approval_policy/on_request.md").read()
L1_perms_ws_of = len(enc.encode(sandbox_ws)) + len(enc.encode(approval_of))
L1_perms_ws_or = len(enc.encode(sandbox_ws)) + len(enc.encode(approval_or))

# 4. Hierarchical agents 指令
hierarchical = open("Agent/codex/codex-rs/prompts/templates/agents/hierarchical.md").read()
L1_hierarchical = len(enc.encode(hierarchical))

print("=== Codex CLI 前缀分解 ===")
print(f"L0 (base instructions): {L0_base} tokens")
print(f"L1 (AGENTS.md): {L1_agents} tokens")
print(f"L1 (permissions, ws+of): {L1_perms_ws_of} tokens")
print(f"L1 (permissions, ws+or): {L1_perms_ws_or} tokens")
print(f"L1 (hierarchical): {L1_hierarchical} tokens")
print(f"L0+L1 (ws+of): {L0_base + L1_agents + L1_perms_ws_of + L1_hierarchical} tokens")
print(f"L0+L1 (ws+or): {L0_base + L1_agents + L1_perms_ws_or + L1_hierarchical} tokens")
print(f"首turn复用比例估计 (L0+L1)/(L0+L1+L2):")
print(f"  假设 L2=200: {(L0_base+L1_agents+L1_perms_ws_of+L1_hierarchical)/(L0_base+L1_agents+L1_perms_ws_of+L1_hierarchical+200):.1%}")
print(f"  假设 L2=500: {(L0_base+L1_agents+L1_perms_ws_of+L1_hierarchical)/(L0_base+L1_agents+L1_perms_ws_of+L1_hierarchical+500):.1%}")
```

### 4.5 实验 B2：Codex CLI 同项目 2 session

**目的**：对比两个 session 的首 turn `input_tokens`，确认 prompt 结构一致性

```bash
# Session 1
cd /share/dai-sys/zhoulongsheng/agentkv/Agent/codex
export CODEX_ROLLOUT_TRACE_ROOT=/tmp/codex_traces
codex exec --json --model codex-mini --full-auto \
  "List all .md files in docs/" 2>&1 | tee /tmp/b2_session1.jsonl

# Session 2
codex exec --json --model codex-mini --full-auto \
  "List all .rs files in codex-rs/core/src/tools/" 2>&1 | tee /tmp/b2_session2.jsonl
```

从 JSONL 中提取 `TurnCompleted` 事件的 `usage.input_tokens` 和 `usage.cached_input_tokens`。

---

## 5. 全生命周期视角的合成

### 5.1 三种方案的 prefill 对比

```
方案1: 无缓存
  total_prefill = Σ_sessions(Σ_turns(input_tokens))

方案2: Session 内缓存（现有方案）
  total_prefill = Σ_sessions(
      input_tokens[turn0]                          # 首 turn 全价
    + Σ_{turn≥1}(input_tokens[turn] - input_tokens[turn-1])  # 后续 turn 只 prefill 增量
  )

方案3: + 跨 session 缓存
  total_prefill = Σ_sessions(
      (input_tokens[turn0] - shared_prefix)        # 首 turn 只 prefill 非共享部分
    + Σ_{turn≥1}(input_tokens[turn] - input_tokens[turn-1])
  )
  其中 shared_prefix 仅在非首个 session 中节省
```

### 5.2 用已有 mini-swe-agent 数据 + 新数据合成

| 框架 | 首 turn 复用比例 | Session 内复用率 | 跨 session 增量 | 数据来源 |
|------|-----------------|-----------------|----------------|---------|
| mini-swe-agent（传统） | ~2% | 87.7% | 4.4% | 已有 |
| mini-swe-agent（重排后） | ~71% | 87.7% | ~30%（估计） | 已有+计算 |
| SWE-agent | ~80%（6,531/8,160） | 估计~85% | 待计算 | 新采集 |
| **Codex CLI** | **待测** | **待测** | **待测** | 新采集 |
| **Claude Code** | **待测** | **待测** | **待测** | 新采集 |

### 5.3 N 个 session 的扩展

当 N 个 session 并发运行时：

```
跨session总节省 = (N-1) × 首 turn 共享前缀 tokens

N=2:  节省 = 1 × shared_prefix  → 占首turn的 (shared_prefix/first_turn_input)%
N=10: 节省 = 9 × shared_prefix  → 占总prefill的 (9 × shared_prefix / N × avg_total_input)%
N=300: 节省 = 299 × shared_prefix → 跨session复用成为主要收益
```

**关键 insight**：N 越大，跨 session 复用的增量收益越显著（线性增长）。

---

## 6. 预期结果与论文价值

### 6.1 首要 deliverable：一张表

| Agent 框架 | 架构 | 首 turn 总 input | 共享前缀 (L0+L1) | 首turn复用比例 | N=10 跨session增量 | N=300 跨session增量 |
|-----------|------|-----------------|-------------------|--------------|-------------------|-------------------|
| mini-swe-agent | 扁平 | ~1,753 | 27 | 2% | ... | ... |
| mini-swe-agent (重排) | 扁平 | ~1,753 | 1,250 | 71% | ... | ... |
| SWE-agent | 扁平 | ~8,160 | 6,531 | ~80% | ... | ... |
| Codex CLI | 树状 | 待测 | 待测 | 待测 | ... | ... |
| Claude Code | 树状 | ~19,445 | 待测 | 待测 | ... | ... |

> Claude Code 首 turn input_tokens ~19,445 来自冒烟数据（`--output-format stream-json` 的 result 消息）

### 6.2 核心论文 insight

1. **首 turn 复用比例是跨 session 缓存价值的核心指标**：比例高 → 值得做；比例低 → 不值得
2. **树状结构的复用比例与扁平结构有质的差异**：扁平架构的共享前缀受限于模板设计，树状架构通过项目级配置自然形成更大的共享前缀
3. **N 个 session 的扩展**：跨 session 复用的收益随 N 线性增长，在批量推理场景（SWE-bench 300 条）下尤其显著
4. **Session 内复用 vs 跨 session 复用是正交的、可叠加的**：两者解决不同层次的冗余

---

## 7. 执行步骤

```
Step 1: Claude Code 冒烟测试
  claude -p "say hello" --output-format stream-json --verbose --model claude-sonnet-4-6
  检查 cache_read / cache_creation 是否非零
  ├── 非零 → 继续 Step 2
  └── 全零 → 需要 Anthropic 原生 API Key，或转向 Step 4

Step 2: Claude Code A1 + A2（~6 min, ~$0.6）
  A1: 同项目 2 session → 首turn复用比例
  A2: 不同项目 2 session → L0/L1 分解

Step 3: 解析数据，计算首turn复用比例（~5 min）
  python3 scripts/analyze_claude_cache_traces.py

Step 4: Codex CLI B1 前缀分解（~5 min, $0）
  tiktoken 离线计算

Step 5: Codex CLI B2 实际运行（~3 min, ~$0.1）
  对比首 turn input_tokens

Step 6: 合成全生命周期视角
  结合已有 mini-swe-agent 数据 + 新数据
  填充上面 6.1 的表

总时间: ~30 min
总费用: ~$0.7
```
