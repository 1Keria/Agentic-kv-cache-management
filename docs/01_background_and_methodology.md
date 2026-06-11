# Agent KV Cache 跨 Session 复用 — 研究背景与方法

> 最后更新：2026-06-10

---

## 1. 研究背景与动机

### 1.1 问题

在 SWE-bench 等 agent 推理场景下，通常会批量运行多个 agent session 来并行解决不同的 issue。每个 session 的 prompt 包含大量相同内容（system prompt、指令模板、工具定义等），但现有 LLM serving 框架按 request 粒度调度，**无法跨 session 复用 KV Cache**。

具体而言，当一个 serving 系统同时处理 N 个 agent session 时：

- 每个 session 的**首次 prefill** 都要独立计算完整的 prompt（system + instance template + tools）
- 即使这些 session 共享相同的 system prompt、指令模板和工具定义，这些部分的 KV Cache 也会被重复计算 N 次
- 这造成了大量的**冗余 prefill 计算**和**显存浪费**

### 1.2 现有工作与局限

| 工作 | 复用范围 | 核心机制 | 局限 |
|------|---------|---------|------|
| Anthropic Prompt Caching | Session 内跨 turn | `cache_control: ephemeral` 标记 | 缓存仅在同一请求序列内有效，跨 session 失效 |
| Sarathi/Serve | Session 内跨 turn | Chunked prefill + interleaving | 关注调度优化，不涉及跨 session 前缀共享 |
| vLLM Automatic Prefix Caching | 跨 request（自动前缀匹配） | Block 级别哈希匹配 | 需要请求时间上接近才有效；无 agent 语义感知 |
| CacheGen | 跨 request（KV Cache 压缩传输） | KV Cache 压缩 + 流式传输 | 面向边缘场景，未考虑 agent 批量推理特征 |

**关键差距**：现有工作要么只关注 session 内复用，要么提供的是通用的前缀匹配机制（缺乏 agent 场景的语义感知）。没有一个工作系统性地分析和利用 **agent 批量推理场景下的跨 session 前缀共享特征**。

### 1.3 我们的创新点

**Agent-Aware 跨 Session KV Cache 复用**：

1. **问题建模**：将 agent 批量推理抽象为"多 session 共享前缀"问题，形式化分析共享前缀的长度分布、复用频率、时间局部性
2. **特征分析**：通过 trace study 量化 agent 场景下跨 session 的 KV Cache 复用机会（共享前缀长度、复用频率、节省量）
3. **优化方案**：基于特征分析结果，设计 agent-aware 的前缀感知调度策略和 KV Cache 管理方案

---

## 2. Agent Prompt 结构分析

### 2.1 一个 Session 的 Prompt 是怎么组成的

一个 session 对应 agent 解决**一个** SWE-bench 问题（一个 GitHub issue）的完整过程。session 内部是多轮对话（turn），每轮包含一次 LLM 推理 + 一次命令执行。

以 `astropy__astropy-12907` 为例，Turn 0 发送给 LLM API 的完整 prompt 由以下部分组成：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 【A】System Message                                                  │
│   "You are a helpful assistant that can interact with a computer    │
│    shell to solve programming tasks."                               │
│   tiktoken: 17 tokens                                               │
├─────────────────────────────────────────────────────────────────────┤
│ 【B】User Message — Instance Template 渲染后的完整内容               │
│                                                                     │
│   【B1】静态前缀                                                     │
│     "<pr_description>\nConsider the following PR description:\n"    │
│     tiktoken: 10 tokens                                             │
│                                                                     │
│   【B2】动态部分 (problem_statement / task)                          │
│     "Modeling's `separability_matrix` does not compute              │
│      separability correctly for nested CompoundModels               │
│      Consider the following model:                                  │
│      from astropy.modeling import models as m                       │
│      ..."                                                           │
│     tiktoken: 322 tokens  (每个 instance 不同！)                    │
│                                                                     │
│   【B3】静态后缀                                                     │
│     "\n</pr_description>\n\n<instructions>\n                        │
│      # Task Instructions\n                                          │
│      ## Overview\n                                                  │
│      You're a software engineer interacting continuously...\n       │
│      ## Important Boundaries\n  ...\n                               │
│      ## Recommended Workflow\n  ...\n                               │
│      ## Command Execution Rules\n  ...\n                            │
│      ## Environment Details\n  ...\n                                │
│      ## Submission\n  ...\n                                         │
│      </instructions>"                                               │
│     tiktoken: 967 tokens                                            │
├─────────────────────────────────────────────────────────────────────┤
│ 【C】Tools 参数 — BASH_TOOL 定义                                    │
│   {"type": "function", "function": {                                │
│     "name": "bash",                                                 │
│     "description": "Execute a bash command",                        │
│     "parameters": {"type": "object", ...}                           │
│   }}                                                                │
│   tiktoken: 63 tokens                                               │
├─────────────────────────────────────────────────────────────────────┤
│ 【D】API 格式开销                                                    │
│   role 标签、消息分隔符、tool schema 编码、message 格式化等          │
│   估算: ~245 tokens                                                 │
└─────────────────────────────────────────────────────────────────────┘

Turn 0 总计: 1,623 tokens (API 精确值)
```

**Turn 1 及之后的 prompt 在 Turn 0 基础上追加**：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 【A】System Message                    ← 与 Turn 0 完全相同         │
│ 【B】User Message (Instance Template)  ← 与 Turn 0 完全相同         │
│ 【C】BASH_TOOL 定义                    ← 与 Turn 0 完全相同         │
│ 【D】API 格式开销                      ← 与 Turn 0 完全相同         │
├─────────────────────────────────────────────────────────────────────┤
│ 【E】Turn 0 的 Assistant 回复          ← 新增 (107 tokens)         │
│   "Let me start by understanding the issue..."                      │
│   + tool_call: bash({"command": "cd /testbed && find ..."})        │
├─────────────────────────────────────────────────────────────────────┤
│ 【F】Turn 0 的 Tool 输出 (observation) ← 新增 (43 tokens)          │
│   "<exception>An error occurred...</exception>"                     │
│   "<returncode>-1</returncode>"                                     │
│   "<output></output>"                                               │
└─────────────────────────────────────────────────────────────────────┘

Turn 1 总计: 1,768 tokens (API 精确值)
增量: 145 tokens (只需 prefill 新增的 E + F)
```

### 2.2 每个部分的复用能力分析

关键问题：**哪些部分可以在不同 session 之间复用？复用范围是什么？**

| 部分 | 内容 | 跨 Session 复用？ | 复用范围 | 能否形成连续前缀？ |
|------|------|------------------|---------|------------------|
| **【A】System Message** | Agent 角色描述 | ✅ 完全相同 | **所有 300 条 session** | ✅ 位于 prompt 最开头 |
| **【B1】Instance 静态前缀** | `<pr_description>` 标签 + 引导语 | ✅ 完全相同 | **所有 300 条 session** | ✅ 紧接 System 之后 |
| **【B2】Instance 动态部分** | problem_statement (issue 描述) | ❌ 每个 instance 不同 | 仅本 session | ❌ 阻断前缀连续性 |
| **【B3】Instance 静态后缀** | `</pr_description>` + `<instructions>` 完整指令模板 | ⚠️ 内容完全相同，但**位置不连续** | **所有 300 条 session** | ❌ 被 B2 阻断，无法作为前缀匹配 |
| **【C】BASH_TOOL** | bash 工具的 JSON schema | ⚠️ 内容完全相同，但**位置不连续** | **所有 300 条 session** | ❌ 被 B2 阻断 |
| **【D】API 格式开销** | role 标签、分隔符等 | ✅ 完全相同 | **所有 300 条 session** | ⚠️ 分散在各消息之间 |
| **【E】Assistant 回复** | 模型生成的推理和工具调用 | ❌ 每个 turn 不同 | 仅本 turn | ❌ 动态生成 |
| **【F】Tool 输出** | 命令执行结果 | ❌ 每个 turn 不同 | 仅本 turn | ❌ 动态生成 |

### 2.3 跨 Session 复用的核心困境：前缀断裂

传统 KV Cache 前缀复用（prefix caching）要求**从 prompt 开头连续匹配**。由于动态的 `problem_statement`（【B2】）插在中间，共享内容被切断了：

```
Session A (astropy-12907):              Session B (astropy-14182):
┌─────────────────────────────┐         ┌─────────────────────────────┐
│ 【A】System prompt           │ ← 相同 →│ 【A】System prompt           │
│ 【B1】<pr_description>...    │ ← 相同 →│ 【B1】<pr_description>...    │
│ ┌─────────────────────────┐ │         │ ┌─────────────────────────┐ │
│ │【B2】Modeling's separa-  │ │ ← 不同 →│ │【B2】Please support     │ │
│ │    bility_matrix does...│ │         │ │    header rows in RST...│ │
│ └─────────────────────────┘ │         │ └─────────────────────────┘ │
│ 【B3】</pr_description>...   │ ← 相同 →│ 【B3】</pr_description>...   │  ← 内容相同
│ 【C】BASH_TOOL               │ ← 相同 →│ 【C】BASH_TOOL               │  ← 但位置不连续！
└─────────────────────────────┘         └─────────────────────────────┘
```

**前缀缓存只能复用到 B2 之前**：

```
可复用的连续前缀:  【A】+【B1】  = 17 + 10 = 27 tokens (tiktoken)
被阻断的部分:      【B3】+【C】  = 967 + 63 = 1,030 tokens (tiktoken)
                   ↑ 内容完全相同，但因 B2 阻断无法作为前缀匹配
```

### 2.4 三种复用方案及其覆盖范围

| 方案 | 可复用内容 | 复用范围 | tiktoken 估计 | API 校准后 | 占首 turn 比例 |
|------|-----------|---------|-------------|-----------|--------------|
| **方案1：传统前缀缓存** | 【A】+【B1】 | 从开头连续匹配 | 27 tokens | ~33 tokens | ~2.0% |
| **方案2：Prompt 重排** | 【A】+【B1】+【B3】+【C】 | 把 B2 移到末尾，恢复前缀连续性 | 1,057 tokens | ~1,300 tokens | ~80.1% |
| **方案3：非连续 KV Cache 复用** | 【A】+【B1】+【B3】+【C】+【D】 | 跳过 B2，复用后续相同内容的 KV Cache | 1,302 tokens | ~1,302 tokens | ~80.2% |

> **Prompt 重排**：修改 `swebench.yaml` 的 `instance_template`，将 `{{task}}` 放到模板末尾：
> ```
> 原模板:  <pr_description>{{task}}</pr_description><instructions>...</instructions>
> 重排后:  <pr_description></pr_description><instructions>...</instructions><task>{{task}}</task>
> ```
> 这样所有静态内容形成完整前缀，传统 prefix caching 即可复用。

> **非连续 KV Cache 复用**：更激进的方案，允许 KV Cache 跳过动态部分，复用后续相同内容的 cache block。需要新的系统设计（block-level 匹配 + 逻辑位置映射）。

### 2.5 同 Repo 内的额外复用（L3 层级）

同一 repo 的不同 issue，`problem_statement` 中是否有额外共享内容？

**实测结论：几乎没有**。

对 SWE-bench_Lite 全部 300 条数据的分析：

| Repo | Issue 数 | Task 间最长公共前缀 | 含 Traceback 比例 | 含 repo import 比例 |
|------|---------|-------------------|------------------|-------------------|
| django/django | 114 | 0 tokens | 16% | 17% |
| sympy/sympy | 77 | 0 tokens | 18% | 38% |
| matplotlib/matplotlib | 23 | 0 tokens | 35% | 26% |
| scikit-learn/scikit-learn | 23 | 0 tokens | 17% | - |
| astropy/astropy | 6 | 0 tokens | 33% | 83% |
| 其余 7 个 repo | 57 | 0 tokens | 0-33% | 0-33% |

- **所有 repo 内，task 之间的最长公共前缀都是 0 tokens**——不同 issue 的描述从第一个词就不同
- 同 repo 内的共同内容是**零散的片段**（如 Traceback header、import 语句），不形成连续前缀
- L3 层级的额外复用收益极小（最大 django ~144 tokens），且需要非连续复用机制

**结论**：跨 session 复用的主要收益来自 L1+L2（模板级共享），而非 L3（repo 级共享）。

### 2.6 Session 内的 KV Cache 增长模式

在一个 session 的生命周期中，KV Cache 的增长模式为：

```
Turn 0:  Prefill(【A】+【B1】+【B2】+【B3】+【C】+【D】)        → Cache size = 首turn全部
Turn 1:  Prefill(【E0】+【F0】)                                  → Cache size += 145
Turn 2:  Prefill(【E1】+【F1】)                                  → Cache size += 99
...
Turn N:  Prefill(【E_{N-1}】+【F_{N-1}】)                        → Cache size += 增量
```

**Session 内复用**：Turn N 只需 prefill 新增的【E_{N-1}】+【F_{N-1}】，前缀部分直接复用已有 KV Cache。这是**现有 serving 框架已支持**的。

**跨 Session 复用**：Session 2 的 Turn 0 可以复用 Session 1 已计算的【A】+【B1】的 KV Cache（传统前缀缓存），或【A】+【B1】+【B3】+【C】的 KV Cache（prompt 重排 / 非连续复用）。这是**现有框架不支持**的，也是本研究的核心贡献。

---

## 3. Trace Study 方法论

### 3.1 Trace 采集

利用 mini-swe-agent 的内置 trajectory 保存机制（`.traj.json` 文件），无需修改框架源码：

- 每个 session 自动保存 `{instance_id}.traj.json`
- `messages` 列表包含完整对话历史（含 `extra` 元数据）
- 剥离 `extra` 字段即可还原发送给 API 的 messages
- `extra.response.usage` 包含 API 报告的实际 token 数

### 3.2 前缀精确分离

从渲染后的 instance template 中精确分离静态/动态部分：

1. 识别 `<pr_description>` 和 `</pr_description>` 标签
2. 标签内的 `Consider the following PR description:\n{{task}}` 中，只有 `{{task}}` 是动态的
3. 标签外的 `<instructions>...</instructions>` 全部是静态的
4. System prompt 和 BASH_TOOL 定义全部是静态的

### 3.3 Token 计数方案

| 方案 | 精度 | 速度 | 费用 | 用途 |
|------|------|------|------|------|
| tiktoken `cl100k_base` | 近似（误差 10-18%） | 快 | 免费 | 日常分析 |
| API `usage.prompt_tokens` | 精确 | 慢 | 已含在请求中 | 校准和论文数据 |

### 3.4 分析维度

| 分析项 | 方法 | 意义 |
|--------|------|------|
| 共享前缀长度分布 | 所有 session 的 L1+L2 token 数分布 | 量化可复用的 KV Cache 大小 |
| 前缀复用频率 | 按相同 config 分组统计 session 数 | 量化跨 session 复用潜力 |
| 同 repo 内额外共享 | 同 repo instance 间的 task 相似度 | 量化 L3 层级的复用 |
| 时间局部性 | batch 运行中 instance 的到达时间差 | 判断缓存时间窗口有效性 |
| KV Cache 节省量 | 无缓存 vs 跨 session 缓存的总 prefill token 数 | 量化总体收益 |
| 每 turn 增量 token | 每 turn 新增 token vs 前缀复用 token | session 内 vs 跨 session 复用比例 |

---

## 4. 实验设置

### 4.1 框架与配置

- **Agent 框架**：mini-swe-agent v2.3.0
- **配置文件**：`swebench.yaml`（tool-call 模式）
- **环境**：LocalEnvironment（避免 Docker 镜像下载开销）
- **模型**：DeepSeek V4 Flash（via 讯飞星火 Maas，OpenAI 兼容接口）

### 4.2 数据集

- **SWE-bench_Lite** test split：300 条 instance，12 个 repo
- Repo 分布：django(114), sympy(77), scikit-learn(23), matplotlib(23), pytest(17), ...

### 4.3 运行命令

```bash
# 设置环境变量
export OPENAI_API_KEY="<from model.txt>"
export OPENAI_API_BASE="https://maas-coding-api.cn-huabei-1.xf-yun.com/v2"
export MSWEA_COST_TRACKING=ignore_errors

# 单条运行
mini-extra swebench-single \
  --subset /share/dai-sys/zhoulongsheng/agentkv/Dataset/SWE-bench_Lite \
  --split test -i 0 \
  -m openai/xopdeepseekv4flash \
  --environment-class local \
  -c swebench.yaml -c agent.step_limit=30 -c model.cost_tracking=ignore_errors \
  -y -o results/single_session/instance_0.traj.json

# 批量运行
mini-extra swebench \
  --subset /share/dai-sys/zhoulongsheng/agentkv/Dataset/SWE-bench_Lite \
  --split test \
  -m openai/xopdeepseekv4flash \
  --environment-class local \
  -c swebench.yaml -c agent.step_limit=30 -c model.cost_tracking=ignore_errors \
  -o results/lite_trace -w 4

# 分析
python scripts/trace_single_session.py results/single_session/instance_0.traj.json
python scripts/analyze_kv_cache_traces.py results/lite_trace/ -o results/lite_trace/analysis
```

### 4.4 工具脚本

| 脚本 | 用途 |
|------|------|
| `scripts/trace_single_session.py` | 单条 session 的 turn-by-turn trace 可视化 |
| `scripts/analyze_kv_cache_traces.py` | 跨 session 批量分析（共享前缀、复用频率、节省量） |
