# Phase 2B/3: vLLM 多 Session 并发实测与痛点验证

> 日期: 2026-06-24 | 配置: Qwen3-8B, H800, gpu_util=0.3, APC ON, no offloading
> 所有数字来自 vLLM 实际推理，可复现

---

## 1. 核心发现：串行 vs 并发 prefix 命中率差距

### 1.1 串行回放：近 100% 命中率

**[MEASURED]** 串行回放 3 个 django session × 10 turns + 2 个 sympy session × 8 turns：

| 请求类型 | 平均命中率 | 平均 TTFT | 说明 |
|----------|-----------|----------|------|
| 首轮 (T0, 冷启动) | 0% | 1018.9ms | 无 prefix 可命中 |
| 首轮 (T0, 热启动, 跨 session) | 86.3%-95.5% | 49-74ms | L0+L1 全部命中 |
| 后续轮次 (T1+) | 97.6%-99.9% | 40-80ms | 前轮 prefix 几乎全部命中 |

**关键数字**：
- 串行模式下，同 session 后续轮次命中率 **99.6%-99.9%**
- 跨 session（同项目）首轮命中率 **86.3%-95.5%**（命中 L0+L1）
- 跨 session（跨项目）首轮命中率 **79.7%-95.1%**（命中 L0 only）
- TTFT 降低：冷启动 1018ms → 热启动 40-80ms，**降低 92%-96%**

### 1.2 并发请求：L1 prefix 完全无法共享

**[MEASURED]** 并发 9 个请求（5 django + 4 sympy），使用 turn 3 的消息：

| 请求 | prompt_tokens | cached_tokens | 命中率 | 命中了什么 |
|------|-------------|-------------|--------|----------|
| DJ1-T3 | 11,485 | 11,472 | 99.9% | L0+L1 (warmup 遗留) |
| DJ2-T3 | 10,490 | 7,824 | 74.6% | L0 only |
| DJ3-T3 | 12,486 | 7,824 | 62.7% | L0 only |
| DJ4-T3 | 9,609 | 7,824 | 81.4% | L0 only |
| DJ5-T3 | 11,632 | 7,824 | 67.3% | L0 only |
| SY1-T3 | 12,243 | 7,808 | 63.8% | L0 only |
| SY2-T3 | 9,815 | 7,824 | 79.7% | L0 only |
| SY3-T3 | 14,080 | 7,824 | 55.6% | L0 only |
| SY4-T3 | 13,106 | 7,824 | 59.7% | L0 only |

**关键发现**：
1. 只有 DJ1-T3 命中了 L0+L1（因为 Phase 1 warmup 已缓存）
2. 其余 8 个并发请求 **全部只命中 L0 (7,824 tokens)** — 跨请求 L1 完全无法共享
3. L0 block 对齐值 = 7,824 tokens = 489 × 16（含 L0 的 6,157 + 部分 L1 对齐填充）

### 1.3 串行 vs 并发：精确对比

**[MEASURED]** 同 3 个 django session 首轮请求：

| 模式 | 请求 | prompt | cached | 命中率 |
|------|------|--------|--------|--------|
| 并发 | DJ-1 | 10,073 | 10,064 | 99.9% |
| 并发 | DJ-2 | 9,065 | 7,824 | 86.3% |
| 并发 | DJ-3 | 11,061 | 7,824 | 70.7% |
| 串行 | DJ-1 | 10,073 | 10,064 | 99.9% |
| 串行 | DJ-2 | 9,065 | 9,056 | 99.9% |
| 串行 | DJ-3 | 11,061 | 11,056 | 100.0% |

**量化差距**：
- 并发 avg_cached = 8,570.7 tokens
- 串行 avg_cached = 10,058.7 tokens
- **Gap = 1,488.0 tokens**（= 并发请求丢失的 L1 prefix）

---

## 2. 模拟结果与实测一致性

### Phase 2A 模拟结果

**[SIMULATED]** C++ 模拟器，block_size=16，2048 请求（50% warmup）：

| 容量 (tokens) | FIFO | LRU | Optimal | LRU-Opt Gap |
|-------------|------|-----|---------|-------------|
| 16,000 | 12.8% | 12.8% | 60.9% | 48.1% |
| 32,000 | 64.8% | 59.5% | 90.7% | 31.2% |
| 44,000 | 91.4% | 89.5% | 96.4% | **6.9%** |
| 80,000 | 96.8% | 97.1% | 97.1% | 0.0% |
| 160,000 | 96.9% | 97.1% | 97.1% | 0.0% |

---

## 3. Block 对齐浪费分析

**[MEASURED]** 串行回放 django-10097 session 15 turns：

- Block 对齐浪费 **0-14 tokens/turn**，中位数约 7 tokens
- 占 prompt 比例 **<0.07%** — 几乎可以忽略
- 理论预测 waste = `total_tokens % 16`，实测完全匹配

---

## 4. 调度感知分析

**[MEASURED]** 3 django + 2 sympy 首轮请求：

| 模式 | 总 cached_tokens | Gap |
|------|----------------|-----|
| 并发 (FCFS) | 45,808 | - |
| 最优串行 | 48,192 | 2,384 tokens |

**2,384 tokens ≈ 1 个 L1 的大小** — 来自调度顺序不当导致的 L1 未被预热

---

## 5. 驱逐行为分析

### 为什么没有触发驱逐？

vLLM 的 `kv_cache_usage_perc` 测量的是**当前 ref_cnt > 0 的 blocks** 比例。

- **串行模式**：请求完成后 blocks 释放 (ref_cnt=0) → KV usage 降为 0 → 但 blocks 仍在 hash table 中可命中
- **并发模式**：9 个请求的 prompt_tokens 总和 = 104,946 → 但 vLLM 调度器分批处理 → 同时运行 3-4 个 → ~40K tokens → 未超 44K 容量

**触发驱逐的理论条件**（基于 Phase 1A 数据）：
- 5+ 并发请求各使用 turn 5+ 的长 prompt（~18K tokens/请求）= ~90K tokens → 超出 44K
- 或降低 GPU KV 容量（但 gpu_util<0.2 会导致模型加载 OOM）

---

## 6. 数据完整性验证

| 检查项 | 预期 | 实际 | 状态 |
|--------|------|------|------|
| L0 token 数 | 6,157 | 6,157 | ✅ |
| 串行命中率 | >90% | 97.6%-99.9% | ✅ |
| 并发 L0 命中 | ≈7,824 | 7,808-7,824 | ✅ |
| 并发 L1 命中 | 0 | 0 | ✅ |
| Block waste ≤ 16 | true | 0-14 | ✅ |
| LRU ≤ Optimal | true | 每点 LRU ≤ Opt | ✅ |

所有数据可通过以下脚本复现：
- `scripts/investigate_phase2b_concurrent.py` → `investigation/data/phase2b_concurrent_pressure.json`
- `scripts/investigate_phase3_pain_points.py` → `investigation/data/phase3_pain_points.json`
