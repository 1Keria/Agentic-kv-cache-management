# 精确 LCP 计算文档

> 日期：2026-06-12
> 方法：提取三个 session 的首次输入文本，用 Qwen3-8B tokenizer 精确 tokenize，结合 API 返回的 `input_tokens` 计算 LCP
> 关联文档：[09_sympy_trace_study_results.md](09_sympy_trace_study_results.md)、[10_L0_L1_decomposition.md](10_L0_L1_decomposition.md)

---

## 1. 目的

之前的 LCP 分析基于首 turn `input_tokens` 的数值近似，存在两个问题：

1. **L2 的组成和大小不准确**：之前估计 L2 ≈ 150-300 tokens，但实际上 L2 包含了 skill_listing（1022 tokens）等大块内容
2. **S1 的首 turn input 不准确**：S1 因 API error 导致第一次调用失败，记录到的 `input_tokens=20233` 包含了第一轮对话历史

本文档通过：
- 提取三个 session 的实际首次输入文本
- 用 Qwen3-8B tokenizer 精确 tokenize
- 结合 API 返回的 `input_tokens` 精确计算 LCP

---

## 2. 三个 Session 的首次输入

### 2.1 S1 (sympy-12481): Permutation 构造函数 bug

**完整首次输入文本**：

```
Fix this bug in sympy: `Permutation` constructor fails with non-disjoint cycles. Calling `Permutation([[0,1],[0,1]])` raises a `ValueError` instead of constructing the identity permutation. If the cycles passed in are non-disjoint, they should be applied in left-to-right order and the resulting permutation should be returned. This should be easy to compute. I don't see a reason why non-disjoint cycles should be forbidden.
```

- 字符数：425 chars
- Qwen3-8B tokenizer：**95 tokens**

### 2.2 S2 (sympy-12481): 同一任务

**完整首次输入文本**：与 S1 完全相同

- 字符数：425 chars
- Qwen3-8B tokenizer：**95 tokens**

### 2.3 S3 (sympy-13480): coth(log(tan(x))) NameError

**完整首次输入文本**：

```
Fix this bug in sympy: .subs on coth(log(tan(x))) errors for certain integral values.
    >>> from sympy import *
    >>> x = Symbol('x')
    >>> e = coth(log(tan(x)))
    >>> print(e.subs(x, 2))
    ...
    File "sympy/functions/elementary/hyperbolic.py", line 590, in eval
        if cotm is S.ComplexInfinity:
    NameError: name 'cotm' is not defined

Fails for 2, 3, 5, 6, 8, 9, 11, 12, 13, 15, 18, ... etc.
```

- 字符数：412 chars
- Qwen3-8B tokenizer：**154 tokens**

### 2.4 Skill Listing 附件

所有三个 session 的首 turn prompt 中都注入了相同的 skill_listing 附件：

```
- deep-research: Deep research harness — fan-out web searches, fetch sources, ...
- update-config: Use this skill to configure the Claude Code harness via settings.json. ...
- keybindings-help: Use when the user wants to customize keyboard shortcuts, ...
- verify: Verify that a code change actually does what it's supposed to ...
- code-review: Review the current diff for correctness bugs and ...
- simplify: Review the changed code for reuse/simplification/efficiency ...
- fewer-permission-prompts: Scan your transcripts for common read-only Bash ...
- loop: Run a prompt or slash command on a recurring interval ...
- claude-api: Reference for the Claude API / Anthropic SDK ...
- run: Launch and drive this project's app to see a change working. ...
- init: Initialize a new CLAUDE.md file with codebase documentation
- review: Review a pull request
- security-review: Complete a security review of a pending changes on the current branch
```

- 字符数：4,399 chars
- Qwen3-8B tokenizer：**1,022 tokens**（三个 session 完全相同）

---

## 3. Problem Statement 之间的 LCP

### 3.1 逐 token 比较

用 Qwen3-8B tokenizer 对 S1 和 S3 的 problem_statement 编码后，逐 token 比较求 LCP：

| Session 对 | PS LCP (tokens) | LCP 文本 | S1 unique | S3 unique |
|-----------|----------------|---------|-----------|-----------|
| S1 vs S2 | **95** (完全相同) | 全文 | 0 | 0 |
| S1 vs S3 | **7** | `Fix this bug in sympy:` | 88 | 147 |
| S2 vs S3 | **7** | `Fix this bug in sympy:` | 88 | 147 |

### 3.2 S1 vs S3 的分叉点

```
S1: Fix this bug in sympy: `Permutation` constructor fails ...
S3: Fix this bug in sympy: .subs on coth(log(tan(x))) ...
                            ^
                         第 8 个 token 处分叉
```

公共前缀 `Fix this bug in sympy:` 占 7 tokens，之后 S1 描述 Permutation 问题，S3 描述 coth/subs 问题。

---

## 4. 首 turn Prompt 的完整组成

### 4.1 API 格式下的 Prompt 结构

Claude Code 发送给 Anthropic API 的首 turn prompt 结构：

```
{
  system: [system_prompt_text],    ← L0 (全局) + L1 (项目级)
  tools: [tool_schema_1, ..., tool_schema_26],  ← L0
  messages: [
    {
      role: "user",
      content: [
        {type: "text", text: problem_statement},              ← L2 (session 级)
        {type: "text", text: "<system-reminder>Skills: ..."}  ← L1 (项目级，同项目相同)
        // ... 其他附件 (task_reminder, date_change 等)       ← L2 (session 级)
      ]
    }
  ]
}
```

### 4.2 input_tokens 的组成

```
input_tokens = L0 + L1 + L2

其中:
  L0 = system_prompt + tools_schema（所有 session 相同）
  L1 = CLAUDE.md + memory + skill_listing + git/env（同项目相同）
  L2 = problem_statement + 其他动态内容（每 session 不同）
```

### 4.3 可精确测量的组件

| 组件 | S1 | S2 | S3 | 测量方式 |
|------|-----|-----|-----|---------|
| **API 首 turn input_tokens** | 20,233* | 20,147 | 20,212 | API 返回 |
| **Problem Statement** | 95 tokens | 95 tokens | 154 tokens | Qwen3-8B tokenizer |
| **Skill Listing** | 1,022 tokens | 1,022 tokens | 1,022 tokens | Qwen3-8B tokenizer |

> *S1 的 20,233 不是纯首 turn input，详见 §4.4

### 4.4 S1 首 turn input 的修正

分析 S1 的 JSONL 事件序列发现：

```
Line 2: user message (PS)
Line 3: attachment (skill_listing)
Line 4-5: assistant response (text + Agent tool_use), input=0 ← 首次 API 调用，usage 未记录
Line 6: user tool_result (Agent subagent 返回)
Line 7: assistant API Error: "Content block is not a input_json block" ← API 错误
Line 8: assistant Agent tool_use, input=20233 ← 重试后的调用，包含了第一轮对话历史
```

**S1 的 `input_tokens=20233` 包含了第一轮对话历史**（assistant 回复 + tool_result），不是纯首 turn input。

S2 的结构正常：
```
Line 4: assistant text (input=0)
Line 5: assistant Agent tool_use, input=20147 ← 纯首 turn input
```

**修正后的纯首 turn input**：

| Session | API 返回值 | 是否纯首 turn | 修正值 |
|---------|-----------|-------------|--------|
| S1 | 20,233 | ❌ (含对话历史) | ≈ 20,147 |
| S2 | 20,147 | ✅ | 20,147 |
| S3 | 20,212 | ✅ | 20,212 |

S1 和 S2 使用相同的 problem_statement、相同的项目、相同的 skill_listing，纯首 turn input 应非常接近（差异仅来自时间戳等微小动态内容）。

---

## 5. 精确 LCP 计算

### 5.1 计算方法

```
首 turn input = L0 + L1 + PS_tokens + skill_tokens + L2_other

其中 L2_other = 时间戳 + 日期 + 格式标记等无法从 JSONL 提取的动态内容
```

从 S2 和 S3 的纯首 turn input 计算：

```
input(S3) - input(S2) = 20212 - 20147 = 65
PS(S3) - PS(S2) = 154 - 95 = 59
skill(S3) - skill(S2) = 0
L2_other(S3) - L2_other(S2) = 65 - 59 = 6
```

L2_other 的差异仅 6 tokens，说明 L2_other 本身很小。

### 5.2 L0+L1 的估计

```
L0+L1 = 首 turn input - PS_tokens - skill_tokens - L2_other

S2: L0+L1 = 20147 - 95 - 1022 - L2_other = 19030 - L2_other
S3: L0+L1 = 20212 - 154 - 1022 - L2_other = 19036 - L2_other

L2_other ≈ 30-50 tokens（时间戳 + 日期 + API 格式标记）

L0+L1 ≈ 18,980 ~ 19,000 tokens
```

### 5.3 LCP 的精确值

**关键洞察**：LCP 是从头开始的连续相同前缀。在首 turn prompt 中，PS（problem_statement）出现在 user message 的开头，skill_listing 在 PS 之后。因此：

- **同任务 session**（S1 vs S2）：PS 完全相同，skill_listing 相同，L2_other 差异极小
  - LCP = L0+L1 + PS(95) + skill(1022) + L2_other_common
  - LCP ≈ 20,097 ~ 20,117 tokens
  - **占比 ≈ 99.8%**

- **不同任务 session**（S1/S2 vs S3）：PS 在第 8 个 token 处分叉
  - LCP = L0+L1 + PS_LCP(7)
  - LCP ≈ 18,987 ~ 19,007 tokens
  - **占比 ≈ 93.9%**

| Session 对 | LCP (tokens) | 较大首 turn input | LCP 占比 | 说明 |
|-----------|-------------|-----------------|---------|------|
| S1 vs S2 | ≈ 20,100 | 20,147 | **99.8%** | 同任务，PS 完全相同 |
| S1 vs S3 | ≈ 18,990 | 20,212 | **94.0%** | 不同任务，PS 7 tokens 后分叉 |
| S2 vs S3 | ≈ 18,990 | 20,212 | **94.0%** | 不同任务，PS 7 tokens 后分叉 |

### 5.4 LCP 分叉的原因

```
首 turn prompt 结构:
  [L0+L1] [PS] [skill_listing] [L2_other]

S1: [L0+L1] [Fix this bug in sympy: `Permutation` constructor ...] [skill] [other]
S3: [L0+L1] [Fix this bug in sympy: .subs on coth(log(tan(x))) ...] [skill] [other]
                      ↑
                  第 8 个 token 处分叉

LCP = [L0+L1] + "Fix this bug in sympy:" (7 tokens)
    ≈ 18,990 tokens
```

分叉后，即使 skill_listing 完全相同（1022 tokens），它也不在连续前缀中，无法计入 LCP。

---

## 6. Prompt 重排对 LCP 的影响

### 6.1 当前结构（PS 在前）

```
[L0+L1] [PS] [skill_listing] [L2_other]
```

- 同任务 LCP: ≈ 20,100 (99.8%)
- 不同任务 LCP: ≈ 18,990 (94.0%)
- **分叉点**：PS 的第 8 个 token

### 6.2 重排结构（PS 移到末尾）

```
[L0+L1] [skill_listing] [L2_other] [PS]
```

- 同任务 LCP: ≈ 20,100 (99.8%) — 不变
- **不同任务 LCP**: ≈ L0+L1 + skill + L2_other_common ≈ 20,050 (99.2%)
- **分叉点**：PS 的第 1 个 token（即 LCP 延伸到 PS 之前）

### 6.3 重排的收益

| 结构 | 不同任务 LCP | LCP 占比 |
|------|------------|---------|
| 当前（PS 在前） | ≈ 18,990 | 94.0% |
| 重排（PS 在末尾） | ≈ 20,050 | 99.2% |
| **重排收益** | **+1,060 tokens** | **+5.2%** |

将动态内容（PS）移到 prompt 末尾，可以将不同任务的 LCP 从 94.0% 提升到 99.2%，增加约 1,060 tokens 的可复用前缀。

---

## 7. 与之前报告的对比

### 7.1 之前报告的问题

| 问题 | 之前的值 | 修正后的值 | 说明 |
|------|---------|-----------|------|
| S1 首 turn input | 20,233 | ≈ 20,147 | S1 含对话历史，非纯首 turn |
| L2 大小 | 150-300 tokens | ≈ 1,150-1,226 tokens | 遗漏了 skill_listing (1,022 tokens) |
| LCP(S1,S3) 占比 | ≥ 98.6% | ≈ 94.0% | 之前高估了 LCP |
| LCP(S1,S2) 占比 | ≥ 99.6% | ≈ 99.8% | 基本一致 |

### 7.2 关键修正

1. **L2 比之前估计的大得多**：之前只考虑了 PS（~100 tokens），忽略了 skill_listing（1,022 tokens）。L2 总计约 1,150-1,226 tokens，占首 turn input 的 5.7-6.1%。

2. **不同任务的 LCP 显著低于之前估计**：因为 PS 在 prompt 中的位置较早（在 skill_listing 之前），PS 的分叉导致 LCP 无法延伸到 skill_listing。之前估计 LCP ≥ 98.6%，实际约 94.0%。

3. **同任务的 LCP 仍然很高**：S1 和 S2 使用相同的 PS，LCP ≈ 99.8%，与之前估计基本一致。

---

## 8. 总结

### 8.1 精确数据

| 指标 | 值 | 来源 |
|------|-----|------|
| L0+L1 | ≈ 18,980-19,000 tokens | 计算：首 turn input - PS - skill - L2_other |
| PS tokens | S1/S2: 95, S3: 154 | Qwen3-8B tokenizer |
| Skill listing tokens | 1,022 | Qwen3-8B tokenizer |
| L2_other | ≈ 30-50 tokens | 估计 |
| **LCP(同任务)** | **≈ 20,100 (99.8%)** | L0+L1 + PS + skill |
| **LCP(不同任务)** | **≈ 18,990 (94.0%)** | L0+L1 + PS_LCP(7) |

### 8.2 核心发现

1. **L0+L1 占首 turn input 的 94.1-94.3%**，是跨 session 复用的主要部分
2. **Skill listing 占首 turn input 的 5.1%**，是 L2 的最大组件
3. **PS 在 prompt 中的位置影响 LCP**：PS 放在前面时，不同任务的 LCP 仅为 94.0%；将 PS 移到末尾可提升至 99.2%
4. **Prompt 重排是提升 LCP 的有效手段**：移动 1,060 tokens 的动态内容到末尾，可增加 5.2% 的 LCP 占比

---

## 参考

- [docs/09_sympy_trace_study_results.md](09_sympy_trace_study_results.md) — Sympy trace study 结果
- [docs/10_L0_L1_decomposition.md](10_L0_L1_decomposition.md) — L0/L1/L2 分解
- [docs/05_claude_code_prompt_structure.md](05_claude_code_prompt_structure.md) — Claude Code prompt 结构
- Qwen3-8B tokenizer (`/share/dai-sys/.cache/hub/models--Qwen--Qwen3-8B/`)
