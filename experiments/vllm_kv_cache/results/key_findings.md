# vLLM KV Cache 实验关键发现

> 最后更新: 2026-06-24 | Phase 1A/1B/2A/2B/3 全部完成

---

## 核心结论

通过对 24,880 条 LMCache Agentic trace 的完整分析、C++ 模拟和 vLLM 实测验证，发现 **3 个高优先级痛点** 和 **3 个中优先级痛点**。

### 一句话总结

> Agent 工作负载有 97% 的 KV 复用潜力，但并发请求间 L1 prefix 完全无法共享（命中率 0%），LRU 驱逐策略在高负载下与最优策略差 6.9%-31.2%，现有 preemption 机制导致 decode 输出完全丢失。

---

## 关键数字速查

| # | 指标 | 值 | 来源 |
|---|------|-----|------|
| 1 | L0 (system prompt) tokens | 6,157 | [TRACE] Phase 1A |
| 2 | L0+L1 占首轮输入比例 | 71.9% | [TRACE] Phase 1A |
| 3 | 串行 APC 命中率 | 97.6%-99.9% | [MEASURED] Phase 1B/2B |
| 4 | 串行 TTFT 降低 | 92%-96% | [MEASURED] Phase 1B |
| 5 | **并发 L1 命中率** | **0%** | [MEASURED] Phase 2B/3 |
| 6 | 并发 vs 串行 cache gap | 1,488 tokens/3请求 | [MEASURED] Phase 3/P1 |
| 7 | LRU vs Optimal gap (44K) | 6.9% | [SIMULATED] Phase 2A |
| 8 | LRU vs Optimal gap (32K) | 31.2% | [SIMULATED] Phase 2A |
| 9 | 超出 44K 容量的 session | 13.6% (104/767) | [TRACE] Phase 1A |
| 10 | Session 增长比中位数 | 3.64x | [TRACE] Phase 1A |
| 11 | Block 对齐浪费 | <0.07% | [MEASURED] Phase 3/P5 |
| 12 | 调度差距 | 2,384 tokens/5请求 | [MEASURED] Phase 3/P7 |

---

## 痛点优先级

| 优先级 | 痛点 | 机制 | 影响 | 证据 | 方向 |
|--------|------|------|------|------|------|
| **CRITICAL** | P1: 并发 L1 不共享 | M3 调度步内无法跨请求 | 1,488 tok/3req | MEASURED | Eager registration |
| **HIGH** | P2: LRU 驱逐 L0 | M5/M6 共享 prefix 被优先驱逐 | 6,157 tok/risk | SIMULATED | Agent-aware eviction |
| **HIGH** | P3: Preemption 丢 decode | M8 num_computed_tokens=0 | 5-15K tok 重算 | MECHANISM | Offload decode |
| MEDIUM | P4: Prefix 增长 | M4/M7 累加 | 3.64x growth | TRACE | Growth prediction |
| MEDIUM | P7: 无调度感知 | M3 扩展 FCFS | 2,384 tok/5req | MEASURED | Prefix-aware sched |
| MEDIUM | P6: Cache 不统一 | M9 GPU/offload 独立 | 6,157 tok | PENDING | Unified hierarchy |
| LOW | P5: Block 浪费 | M1/M2 固定 block_size | <0.07% | MEASURED | 不需要修复 |

---

## 实验数据文件

| 阶段 | 数据文件 | 说明 |
|------|---------|------|
| Phase 1A | `investigation/data/per_row_metrics.json` | 24,880 行 per-request 指标 |
| Phase 1A | `investigation/data/tokenized_traces_summary.json` | 767 session 统计 |
| Phase 2A | `investigation/data/simulation_results.json` | C++ 模拟器容量扫描 |
| Phase 2B | `investigation/data/phase2b_eviction_test.json` | 串行 + 并发驱逐测试 |
| Phase 2B | `investigation/data/phase2b_concurrent_pressure.json` | 9 并发请求压力测试 |
| Phase 3 | `investigation/data/phase3_pain_points.json` | P1-P7 逐痛点实测 |
| 汇总 | `investigation/data/pain_point_metrics.json` | 所有关键数字汇总 |

## 实验脚本

| 阶段 | 脚本 |
|------|------|
| Phase 1A | `scripts/investigate_trace_tokenizer.py` |
| Phase 2A | `scripts/investigate_run_simulations.py` |
| Phase 2B | `scripts/investigate_phase2b_eviction.py`, `scripts/investigate_phase2b_concurrent.py` |
| Phase 3 | `scripts/investigate_phase3_pain_points.py` |

## 报告文件

| 文件 | 说明 |
|------|------|
| `report/00_executive_summary.md` | 执行摘要 |
| `report/02_trace_characterization.md` | Phase 1A/1B Trace 特征画像 |
| `report/03_simulation_results.md` | Phase 2A 模拟结果 |
| `report/04_vllm_eviction_analysis.md` | Phase 2B/3 vLLM 实测分析 |
| `report/05_pain_point_analysis.md` | P1-P7 逐痛点深度分析 |
| `report/06_prioritization_matrix.md` | 优先级矩阵与论文建议 |
