# Phase 1: Trace 特征画像

> 数据来源: [理论] tiktoken cl100k_base 分词 24,880 条请求 + [实测] vLLM Qwen3-8B 单 session 回放

## 1A. 理论分析结果

### 数据概况

| 指标 | 值 |
|------|-----|
| 总请求数 | 24,880 |
| 总 session 数 | 767 |
| SWE-bench session | 665 (minimax=490, claude=110, deepseek=65) |
| GAIA session | 94 |
| WildClaw session | 8 |

### L0/L1/L2 层次分解（SWE-bench minimax, 490 sessions）

| 层级 | Token 数 | 占首轮比例 | 共享范围 |
|------|---------|-----------|---------|
| L0 (system prompt) | 6,156 | 46.3% | 所有 session |
| L1 (examples + runtime) | 3,394 | 25.5% | 同项目 session |
| L2 (task + history) | 3,736 | 28.1% | session 特有 |
| **L0+L1** | **9,550** | **71.9%** | — |

**核心结论**：Agent 请求的 71.9% 是可跨 session 复用的 prefix（L0+L1），只有 28.1% 是 session 特有的。

### 逐轮输入增长

| Turn | p50 (tokens) | p75 (tokens) | Session 数 |
|------|------------|------------|-----------|
| 0 | 8,810 | 10,341 | 767 |
| 5 | 13,462 | 17,055 | 752 |
| 10 | 17,627 | 20,462 | 682 |
| 20 | 23,032 | 26,405 | 539 |
| 30 | 28,884 | 32,423 | 412 |

### Session 生命周期 KV 占用

| 指标 | 值 |
|------|-----|
| Max KV p50 | 32,211 tokens |
| Max KV p75 | 39,437 tokens |
| 增长比 p50 | 3.64x |
| 增长比 mean | 9.12x |
| 超出 44K 的 session | 104 (13.6%) |

**关键发现**：13.6% 的 session 单独就会超出 H800 (gpu_util=0.3) 的 44K tokens KV 容量。当 2+ 个 session 并发时，这个比例会大幅增加。

### 跨 session prefix 重叠

| 项目 | L1 tokens | 与 L0 合计 |
|------|----------|-----------|
| astropy | 4,087 | 10,244 |
| matplotlib | 4,035 | 10,194 |
| mwaskom | 3,600 | 9,757 |
| sympy | 2,944 | 9,101 |
| django | 2,726 | 8,883 |

### 并发到达模式

| 指标 | 值 |
|------|-----|
| Inter-turn gap p50 | 0.708s |
| Inter-turn gap mean | 2.084s |

---

## 1B. vLLM 实测结果

> 配置: Qwen3-8B, H800, gpu_util=0.3, APC enabled, offload=8GiB
> Session: swebench__django__django-10097__minimax (L0=6,156t, L1=3,394t)

| 请求 | TTFT (ms) | prompt_tokens | cached_tokens | 命中率 |
|------|----------|--------------|---------------|--------|
| Turn 0 (冷启动) | 1,632 | 10,078 | 0 | 0% |
| Turn 1 (同session) | 85 | 10,102 | 10,064 | **99.6%** |
| Turn 2 (同session) | 67 | 10,130 | 10,096 | **99.7%** |
| Turn 3 (跨项目) | 61 | 6,459 | 6,160 | **95.4%** |

### 理论 vs 实测对比

| 场景 | 理论 prefix_reusable | 实测 cached_tokens | 差异 |
|------|---------------------|-------------------|------|
| Turn 0 | 0 | 0 | ✅ 完全一致 |
| Turn 1 | ≈10,078 (前轮 total) | 10,064 | ✅ 差 14 tokens (block 对齐) |
| Turn 2 | ≈10,102 (前轮 total) | 10,096 | ✅ 差 6 tokens (block 对齐) |
| 跨项目 | ≈6,156 (L0 only) | 6,160 | ✅ 差 4 tokens (block 对齐) |

### 关键结论

1. **APC 在串行场景下非常高效**：命中率 95-99.7%，TTFT 降低 94.8%
2. **L0 跨项目复用验证**：跨项目请求命中 6,160 tokens (95.4%)，精确对应 L0 prefix
3. **Block 对齐浪费极小**：理论 vs 实测差异 ≤ 14 tokens (< 0.2%)
4. **tiktoken chars/3 粗估偏高**：L0 实测 6,160 tokens，而 chars/3 估算 9,793 tokens（偏差 59%）。需要用 vLLM 实际 tokenizer 或 tiktoken 精确计算
