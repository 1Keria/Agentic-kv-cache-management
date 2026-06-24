# AgentKV vLLM KV Cache 调研：执行摘要

> 日期: 2026-06-24 | 模型: Qwen3-8B | GPU: NVIDIA H800 | vLLM: 0.8.5.dev0

## 核心结论

通过对 24,880 条 LMCache Agentic trace 的完整分析和 vLLM 实测验证，我们发现了 **3 个高优先级痛点** 和 **2 个中优先级痛点**，每个都有具体可复现的数字支撑。

### 关键数字

| 指标 | 值 | 来源 |
|------|-----|------|
| L0 (system prompt) token 数 | 6,157 (minimax sessions) | [TRACE] tiktoken cl100k_base |
| L0+L1 占首轮输入比例 | 71.9% | [TRACE] 12 项目平均 |
| 串行 APC 命中率 | 97.6%-99.9% | [MEASURED] vLLM Phase 1B |
| 并发请求 L0 命中率 | 79.7%-86.3% | [MEASURED] vLLM Phase 2B |
| 并发请求 L1 命中率 | 0% | [MEASURED] vLLM Phase 2B |
| Block 对齐浪费 | <1 token/turn (bs=16) | [MEASURED] vLLM Phase 3/P5 |
| LRU vs Optimal 模拟差距 | 7.0% (44K token 容量) | [SIMULATED] Phase 2A |
| 超出 44K 容量的 session | 13.6% (104/767) | [TRACE] Phase 1A |

### 痛点优先级排序

| 优先级 | 痛点 | 影响 | 新颖性 | 贡献方向 |
|--------|------|------|--------|----------|
| **CRITICAL** | P1: 并发请求无法跨请求共享 L1 prefix | 1,488-3,400 tokens/请求批次 | 高（首次精确量化） | Eager prefix registration |
| **HIGH** | P2: LRU 可能驱逐高价值 L0 blocks | 6,157 tokens/受影响请求 | 高（Agent 特有病理） | Agent-aware eviction |
| **HIGH** | P3: Preemption 导致 decode 输出完全丢失 | 整个 decode 输出需重算 | 高（Agent 特有） | Offload decode / Partial preempt |
| **MEDIUM** | P4: Prefix 增长导致递增内存压力 | 3.2x-9.1x 增长比 | 中 | 增长预测 + 动态 offload |
| **MEDIUM** | P5: Block 边界浪费 | 0-15 tokens/turn (<0.2%) | 低（已知问题） | Variable-size caching |

### 论文 Motivation 论证

1. **Agent 工作负载有极高的 KV Cache 复用潜力**（命中率 89-99%）→ 但现有系统未充分利用
2. **vLLM APC 对串行 Agent 请求已经高效**（命中率 97-99%，TTFT 降低 80-95%）→ 但仅限串行
3. **并发请求间 L1 prefix 完全无法复用**（实测并发 L1 命中 0% vs 串行 100%）→ 这是 AgentKV 要解决的核心问题

## 详细报告

- [02_trace_characterization.md](02_trace_characterization.md) — Phase 1A/1B Trace 特征画像
- [03_simulation_results.md](03_simulation_results.md) — Phase 2A 模拟结果
- [04_vllm_eviction_analysis.md](04_vllm_eviction_analysis.md) — Phase 2B/3 vLLM 实测分析
- [05_pain_point_analysis.md](05_pain_point_analysis.md) — P1-P7 逐痛点深度分析
- [06_prioritization_matrix.md](06_prioritization_matrix.md) — 优先级矩阵与论文建议
