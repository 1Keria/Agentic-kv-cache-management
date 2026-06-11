# AgentKV 源码分析任务上下文

> 本文档用于任务执行期间的上下文恢复。当上下文溢出或会话中断时，先读此文件。

---

## 项目背景

**AgentKV** 是一个研究项目，研究 Agent 推理场景下的跨 session KV Cache 复用。目标投稿 OSDI/SOSP/NSDI 级别系统论文。

### 核心发现（已确认）

- Claude Code 首 turn prompt ~20,200 tokens，其中 L0+L1 ≈ 18,990 (94%) 可跨 session 复用
- L0 = 全局共享前缀（system prompt + tools schema），L1 = 项目级前缀（CLAUDE.md + memory + skills）
- L2 = session 级动态内容（problem_statement + skill_listing + 时间戳），约 1,150-1,226 tokens
- 同任务 LCP ≈ 20,100 (99.8%)，不同任务 LCP ≈ 18,990 (94.0%)
- Prompt 重排可将不同任务 LCP 从 94.0% 提升到 99.2%
- 详见 `docs/11_precise_lcp_calculation.md`、`docs/10_L0_L1_decomposition.md`

### 系统设计方案（待定）

方案尚未最终确定，取决于源码分析的结论。当前候选方向：

- **方案 A**：基于 SGLang 扩展（利用 RadixTree 天然支持 L0/L1/L2）
- **方案 B**：分布式架构层（类似 Mooncake 的 disaggregated 架构）
- **方案 C**：独立 KV Cache 管理池（类似 LMCache，但增加 agent-aware 能力），让 SGLang 和 vLLM 都能接入
- **组合方案**：以上方案的组合

三个候选核心创新点：
1. **Agent-Aware Scheduling** — agent 组感知调度
2. **Agent Group Aware Eviction** — 组感知驱逐
3. **Cross-Session Prefix Pinning** — 跨 session prefix 锁定

源码分析的目的之一就是确定最终方案选型。特别关注：
- LMCache 的架构是否适合作为基础做 agent-aware 优化
- 如何设计一个通用的 KV cache 管理池，同时支持 SGLang 和 vLLM 接入
- SGLang/vLLM 内部 KV 管理与外部 KV 存储（LMCache/Mooncake）的边界在哪里

详见 `~/.claude/plans/keen-gliding-lantern.md`

---

## 当前任务：四大框架 KV Cache 源码分析

### 任务规划

详见 `docs/12_kv_cache_source_analysis_plan.md`

### 源码位置

| 框架 | 路径 | 语言 | 安装状态 |
|------|------|------|---------|
| SGLang | `/share/dai-sys/zhoulongsheng/agentkv/Engine/sglang/` | Python | ✅ 已安装 (dev mode) |
| vLLM | `/share/dai-sys/zhoulongsheng/agentkv/Engine/vllm/` | Python | ❌ 未安装（源码可读） |
| Mooncake | `/share/dai-sys/zhoulongsheng/agentkv/Engine/Mooncake/` | C++ | ❌ 不可 pip 安装（源码可读） |
| LMCache | `/share/dai-sys/zhoulongsheng/agentkv/Engine/LMCache/` | Python+CUDA | ❌ CUDA driver 太旧（源码可读） |

### 工作流程

1. 产出文件索引 → `docs/13_kv_cache_file_index.md`
2. 并行分析 4 个框架（4 个 agent）：
   - Agent 1: SGLang → `notes/sglang_kv_cache.md`
   - Agent 2: vLLM → `notes/vllm_kv_cache.md`
   - Agent 3: Mooncake → `notes/mooncake_kv_cache.md`
   - Agent 4: LMCache → `notes/lmcache_kv_cache.md`
3. 汇总 → `docs/14_kv_cache_source_analysis.md`

### 时间

- 总工作量 ~24h，4 agent 并行，墙钟 ~6h
- SGLang ~8h, vLLM ~6h, Mooncake ~6h, LMCache ~4h

---

## 产出物清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `docs/12_kv_cache_source_analysis_plan.md` | ✅ 已完成 | 分析规划 |
| `docs/13_kv_cache_file_index.md` | ⬜ 待产出 | 关键文件索引 |
| `notes/sglang_kv_cache.md` | ⬜ 待产出 | SGLang 分析笔记 |
| `notes/vllm_kv_cache.md` | ⬜ 待产出 | vLLM 分析笔记 |
| `notes/mooncake_kv_cache.md` | ⬜ 待产出 | Mooncake 分析笔记 |
| `notes/lmcache_kv_cache.md` | ⬜ 待产出 | LMCache 分析笔记 |
| `docs/14_kv_cache_source_analysis.md` | ⬜ 待产出 | 最终汇总报告 |

---

## 分析维度（每个框架都要覆盖）

1. **KV cache 基本抽象** — key/value 是什么、引用计数
2. **生命周期** — allocate → write → append → reuse → evict
3. **内存层级** — GPU/CPU/disk/remote，层级间迁移
4. **Prefix reuse 机制** — 匹配算法、粒度、partial hit、跨请求/跨节点
5. **调度器与 KV cache 关系** — cache-aware 调度、preemption
6. **Agent 场景差距** — 为什么不适合 agent、扩展改动量

---

## 环境信息

- Conda 环境：`/share/dai-sys/apps/anaconda3/envs/agentkv_zls/`
- Rust：`/share/dai-sys/zhoulongsheng/rust/`
- pip cache：`/share/dai-sys/zhoulongsheng/pip_cache/`
- build tmp：`/share/dai-sys/zhoulongsheng/tmp_build/`
- Qwen3-8B tokenizer：`/share/dai-sys/.cache/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/`
- **不要用 `/home/zhoulongsheng/` 下的空间**

---

## 已有文档索引

| 文件 | 内容 |
|------|------|
| `docs/04_agent_framework_comparison.md` | 四框架初步对比 |
| `docs/05_claude_code_prompt_structure.md` | Claude Code prompt 结构 |
| `docs/09_sympy_trace_study_results.md` | Sympy trace study 结果 |
| `docs/10_L0_L1_decomposition.md` | L0/L1/L2 分解 |
| `docs/11_precise_lcp_calculation.md` | 精确 LCP 计算 |
| `docs/12_kv_cache_source_analysis_plan.md` | 本次分析规划 |
| `docs/ref.md` | 参考分析框架（有对有不合适，取其精华） |

---

## 恢复指令

如果上下文溢出或会话中断：

1. 先读本文件（`docs/CONTEXT_kv_cache_analysis.md`）
2. 读规划文件（`docs/12_kv_cache_source_analysis_plan.md`）
3. 检查产出物清单，看哪些已完成
4. 读已完成的 notes 文件，了解分析进度
5. 继续未完成的工作
