# 优先级矩阵与论文 Motivation 建议

> 日期: 2026-06-24

---

## 优先级矩阵

| 痛点 | 机制错配 | 影响量化 | 新颖性 | 可操作性 | 证据 | 优先级 |
|------|---------|---------|--------|---------|------|--------|
| P1: 并发共享失效 | M3 调度步内无法跨请求共享 | 1,488 tokens/3请求; 并发 L1 命中=0% | **高**（首次精确量化 Agent 场景） | **高**（eager registration） | [MEASURED] | **CRITICAL** |
| P3: Preemption 丢失 decode | M8 num_computed_tokens=0 | 5,000-15,000 tokens 重算 | **高**（Agent 特有） | **高**（offload decode / partial preempt） | [MECHANISM] | **HIGH** |
| P2: LRU 驱逐 L0 | M5/M6 共享 prefix 被优先驱逐 | 6,157 tokens/请求; LRU-Opt gap 6.9% | **高**（Agent 特有病理） | **高**（priority eviction） | [SIMULATED] | **HIGH** |
| P4: Prefix 增长压力 | M4/M7 共享 blocks 累加 | 3.64x 增长; 13.6% 超容量 | 中 | 中（增长预测 + 动态 offload） | [TRACE] | MEDIUM |
| P7: 无调度感知 | M3 扩展 FCFS 不考虑 prefix | 2,384 tokens/5请求 | 中 | 高（LPM-style 调度） | [MEASURED] | MEDIUM |
| P6: Cache 层级不统一 | M9 GPU/offload 独立管理 | 6,157 tokens | 高（隐蔽但影响大） | 高（unified hierarchy） | [PENDING] | MEDIUM |
| P5: Block 浪费 | M1/M2 链式 hash + 固定 block_size | <0.07% 浪费 | 低（已知问题） | 中 | [MEASURED] | LOW |

---

## 论文 Motivation 论证建议

### 三段式论证

#### 论点 1: Agent 工作负载有极高的 KV Cache 复用潜力

**数据支撑**：
- LMCache Agentic traces: 24,880 条请求，767 个 session，**97.1% 的 tokens 是可复用 prefix**
- L0 (system prompt) = 6,157 tokens，**所有 767 个 session 共享**
- L0+L1 (项目级 examples) 占首轮输入 **71.9%**
- 串行 APC 命中率 **97.6%-99.9%**，TTFT 降低 **92%-96%**

**引用**：
> "In agentic workloads, 71.9% of prompt tokens are reusable prefix shared across sessions, yet current systems fail to exploit this potential under concurrent access."

#### 论点 2: 现有系统的 prefix cache 在并发时失效

**数据支撑**：
- 并发请求 L1 命中率 = **0%**（vs 串行 100%）
- 3 个并发请求的 cache gap = **1,488 tokens**
- 9 个并发请求的总体命中率 = **70.6%**（vs 串行 ~99%）
- 调度无感知导致额外损失 **2,384 tokens/批次**

**引用**：
> "When multiple agent sessions arrive concurrently — a common pattern in production — L1 prefix cache hit rate drops to 0%, as blocks are registered only after the scheduling step, making them invisible to concurrent requests."

#### 论点 3: 驱逐策略在 Agent 负载下有结构性缺陷

**数据支撑**：
- LRU vs Optimal gap = **6.9%** at 44K token capacity (simulation)
- 在 32K 容量下 gap 扩大到 **31.2%**
- 13.6% 的 session 单独就超出 44K GPU 容量
- Preemption 导致 decode 输出完全丢失（5,000-15,000 tokens 重算）

**引用**：
> "LRU eviction is fundamentally misaligned with agent workloads: shared system prompt blocks (L0) have the highest reuse value but may be evicted first due to temporal inactivity, while agent-specific decode outputs — the most expensive to recompute — are never preserved by current offloading mechanisms."

---

## 关键数字汇总表（论文用）

| 指标 | 值 | 类型 |
|------|-----|------|
| Agent trace 总请求数 | 24,880 | [DATA] |
| Agent trace session 数 | 767 | [DATA] |
| L0 (system prompt) tokens | 6,157 | [TRACE] |
| L0+L1 占首轮比例 | 71.9% | [TRACE] |
| 串行 APC 命中率 | 97.6%-99.9% | [MEASURED] |
| 串行 TTFT 降低 | 92%-96% | [MEASURED] |
| 并发 L1 命中率 | 0% | [MEASURED] |
| 并发 L0 命中率 | 79.7%-86.3% | [MEASURED] |
| 并发 vs 串行 cache gap | 1,488 tokens/3请求 | [MEASURED] |
| Block 对齐浪费 | <0.07% | [MEASURED] |
| LRU vs Optimal gap (44K) | 6.9% | [SIMULATED] |
| LRU vs Optimal gap (32K) | 31.2% | [SIMULATED] |
| Session 增长比中位数 | 3.64x | [TRACE] |
| Session 超出 44K 容量 | 13.6% | [TRACE] |
| 调度差距 | 2,384 tokens/5请求 | [MEASURED] |

---

## 建议的论文贡献点

### 贡献 1: Eager Prefix Registration（对应 P1）

**问题**：并发请求无法共享 L1 prefix，损失 1,488+ tokens/批次。
**方案**：在请求开始处理前，预注册已知 prefix（L0+L1）的 block hash 到 hash table。
**预期收益**：并发 L1 命中率从 0% → ~100%，节省 1,488+ tokens × 并发数的 prefill 计算。

### 贡献 2: Agent-Aware Eviction Policy（对应 P2+P3）

**问题**：LRU 可能驱逐高价值 L0 blocks；preemption 导致 decode 输出丢失。
**方案**：
- L0/L1 blocks 标记为 "protected"，即使 ref_cnt=0 也不优先驱逐
- Decode blocks offload 到 CPU，preemption 时可恢复
**预期收益**：LRU-Optimal gap 从 6.9% 降至接近 0%；preemption 恢复时间从冷启动降至 prefix cache 恢复。

### 贡献 3: Prefix-Aware Scheduling（对应 P7）

**问题**：FCFS 调度不考虑 prefix 共享，损失 2,384 tokens/批次。
**方案**：按项目分组调度，同项目请求连续处理以最大化 L1 共享。
**预期收益**：每批次节省 2,384 tokens 的 prefill 计算。
