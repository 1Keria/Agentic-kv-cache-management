# vLLM vs SGLang KV Cache 实验结果报告

> 日期: 2026-06-25
> 模型: Qwen3-8B
> GPU: NVIDIA H800 × 1
> KV 容量: vLLM 53,072 tokens (gpu_util=0.3), SGLang 59,902 tokens (mem-fraction=0.3)

---

## 1. P2: LRU 驱逐 L0

### vLLM 结果

| 实验 | 结果 | 关键数据 |
|------|------|---------|
| P2-A: 触发 L0 驱逐 | ✅ **L0 被驱逐** | 5个不共享prefix并发请求 → cached=0, 5,829 blocks被驱逐 |
| P2-B: 压力扫描 | 临界点: 4→5 requests | 4压力: cached=9,664(L1部分丢失); 5压力: cached=0(L0完全驱逐) |
| P2-B: touch对比 | touch无效 | 5压力下LRU和Aware都是cached=0; 简单touch无法保护L0 |

**核心发现**：
- vLLM 的 LRU 驱逐确实会驱逐 L0 blocks
- 驱逐是隐式的：`get_new_blocks()` 从 free_block_queue 头部弹出 blocks 时，如果 blocks 有 hash 就驱逐
- 简单的 touch 操作（发送请求刷新 L0 在 free queue 中的位置）**无法有效保护 L0**，因为压力足够大时尾部 blocks 也会被分配
- 需要系统级的 Agent-Aware 驱逐策略（区分 L0/普通 blocks 的驱逐优先级）

### SGLang 结果

| 实验 | 结果 | 关键数据 |
|------|------|---------|
| S4: L0 驱逐 | ⚠️ **L0 几乎被驱逐** | 9个不共享prefix并发请求 → cached=3 (几乎为0) |

**核心发现**：
- SGLang 的 radix tree **并没有像理论预期那样保护 L0**
- 理论预期：L0 是中间节点（有子节点），SGLang 只驱逐叶子节点，L0 应该受保护
- 实际结果：L0 几乎完全被驱逐（cached=3 vs baseline=10072）
- 可能原因：在足够大的压力下，L0 的所有子节点先被驱逐，L0 变成叶子节点后被驱逐

**vLLM vs SGLang 对比**：

| 维度 | vLLM | SGLang |
|------|------|--------|
| L0 驱逐结果 | 完全驱逐 (cached=0) | 几乎完全驱逐 (cached=3) |
| 驱逐机制 | LRU free queue (无节点类型区分) | Min-heap (叶子优先，但中间节点也会被驱逐) |
| 驱逐阈值 | 5个压力请求 | 9个压力请求 |
| 结论 | **两者都无法有效保护 L0** | SGLang 稍好但差距不大 |

---

## 2. P3: Preemption 导致 Decode 输出丢失

### vLLM 结果

| 实验 | 结果 | 关键数据 |
|------|------|---------|
| P3-A: 触发 Preemption | ❌ **未触发** | 9并发请求: 5 running + 4 waiting, KV usage 95.5%, num_preemptions=0 |
| P3-A: PRIORITY调度 | ❌ **仍未触发** | 高优先级请求只是排队等待，不会抢占 running 请求 |

**核心发现**：
- vLLM v1 调度器在内存不足时选择**排队等待**而非**抢占**
- Preemption 只在 `allocate_slots()` 对 running 请求返回 None 时触发
- Decode 阶段每个 step 只需 1 个 block，通常能分配到
- 即使 KV usage 达 95.5%，也不会 preempt
- **机制分析仍然有效**：`_preempt_request()` 确实设 `num_computed_tokens=0`，只是当前配置下很难触发

### SGLang 对比

| 维度 | vLLM | SGLang |
|------|------|--------|
| Preemption/Retraction | 难以触发（排队策略） | retraction 在 decode 内存不足时触发 |
| 恢复方式 | 完全重算（num_computed_tokens=0） | radix tree 保留共享 prefix，只需重算 decode 部分 |
| Decode 恢复 | ❌ 永久丢失 | ❌ 永久丢失（is_insert=False） |
| 结论 | vLLM 更保守（不 preempt），但一旦 preempt 恢复代价更大 | SGLang 更积极（retract），但恢复更快 |

---

## 3. P5: Block 浪费

### vLLM 结果

- Block size = 16 tokens
- 每个 turn 浪费 0-15 tokens（block 对齐）
- 实测浪费率 < 0.07%

### SGLang 结果

- Page size = 1 (token-level matching)
- S1 实测：每 turn 浪费 ~50 tokens
- **注意**：SGLang 的 50 tokens 浪费不是 page 对齐问题，而是 radix tree 匹配边界问题
- 新 turn 增加的 user/assistant 消息不在匹配范围内

**vLLM vs SGLang 对比**：

| 维度 | vLLM | SGLang |
|------|------|--------|
| 匹配粒度 | Block-level (16 tokens) | Token-level (page_size=1) |
| 每turn浪费 | 0-15 tokens (block对齐) | ~50 tokens (匹配边界) |
| 浪费率 | < 0.07% | ~0.5% |
| 结论 | **SGLang 浪费反而更大** | 原因不是 page 对齐，而是 radix tree 匹配边界 |

---

## 4. P6: Cache 层级不统一

### vLLM 结果

| 配置 | cached_tokens | offload store_bytes | offload load_bytes |
|------|--------------|--------------------|--------------------|
| **Offload ON** (8 GiB) | 0 | **14.96 GiB** | **0 bytes** |
| **Offload OFF** | 0 | 0 | 0 |

**✅ P6 证实——双层独立 LRU 驱逐**：
- Offload ON vs OFF 的 `cached_tokens` 完全相同
- Offload tier store 了 14.96 GiB 数据到 CPU，但 CPU→GPU load = 0 bytes
- **根因不是"lookup 不检查 CPU"**（实际上 KV connector 的 `_lookup()` 会检查 CPU offload tier），而是**两层都使用独立 LRU 驱逐策略且互不协调**
- GPU 层：`_maybe_evict_cached_block()` 移除 L0 hash → GPU miss
- CPU 层：CPU 容量 58,254 tokens，压力请求累计 store 111,520 tokens → CPU LRU 也驱逐了 L0 → CPU miss
- 两层都 miss → load=0，offload 形同虚设

### SGLang 对比

| 维度 | vLLM | SGLang |
|------|------|--------|
| 层级管理 | **独立 LRU**（GPU hash table + CPU offload 各自 LRU 驱逐） | **统一 radix tree**（同一 TreeNode 持有 value + host_value） |
| 驱逐后恢复 | ❌ 两层独立 LRU 导致同一 prefix 在两层同时丢失 | ✅ evicted 节点仍在 radix tree 中，可通过 load_back 恢复 |
| P6 存在？ | ✅ **存在** | ❌ **不存在** |

---

## 5. P1: 并发共享失效

### vLLM 结果（已有）

- 并发 L1 命中率 = 0%
- 同一批调度的请求看不到彼此的 prefix blocks

### SGLang 结果

| 配置 | cached_tokens | 说明 |
|------|--------------|------|
| 串行 | 10,072 | 完整 L0+L1 命中 |
| 并发 | 8,517-8,521 | L0 命中，L1 部分丢失 |

**关键发现**：
- SGLang 并发请求的 L1 命中率 **不是 0%**（vs vLLM 的 0%）
- L0 命中率 ~85%（8,517/10,072），L1 有部分丢失
- SGLang 的 **in-batch prefix caching 部分生效**

**vLLM vs SGLang 对比**：

| 维度 | vLLM | SGLang |
|------|------|--------|
| 并发 L1 命中率 | **0%** | **~15-16%** (部分命中) |
| In-batch caching | 无 | 有（但阈值=32 tokens，Agent L1 >> 32） |
| 结论 | **SGLang 略优于 vLLM** | 但仍有 ~84% 的 L1 在并发时丢失 |

---

## 6. 综合对比表

| 痛点 | vLLM 状态 | SGLang 状态 | SGLang 更优？ | 量化差距 |
|------|----------|------------|-------------|---------|
| P1: 并发共享失效 | [MEASURED] L1 命中 0% | [MEASURED] L1 命中 ~15% | ✅ 略优 | 8,517 vs 0 cached tokens |
| P2: LRU 驱逐 L0 | [MEASURED] L0 被驱逐 | [MEASURED] L0 几乎被驱逐 | ≈ 相当 | cached=0 vs cached=3 |
| P3: Preemption 丢 decode | [MECHANISM] 未触发 | [MECHANISM] retraction 更优 | ✅ 恢复更快 | 但 decode 仍丢失 |
| P4: Prefix 增长压力 | [TRACE] 3.64x | [共享数据] 3.64x | — | 同 |
| P5: Block 浪费 | [MEASURED] <0.07% | [MEASURED] ~0.5% | ❌ SGLang 反而更大 | 50 vs 0-15 tokens/turn |
| P6: Cache 层级不统一 | [MEASURED] load=0 | ✅ 不存在 | ✅ 根本不同 | vLLM offload 无效 |
| P7: 无调度感知 | [MEASURED] gap 2,384 | [待测] LPM/DFS 可缓解 | ✅ Cache-aware | 待测 |

---

## 7. 证据等级更新

| 痛点 | 原等级 | 新等级 | 关键新增数据 |
|------|--------|--------|------------|
| P2: LRU 驱逐 L0 | [SIMULATED] | **[MEASURED]** | vLLM 实测: 5,829 blocks被驱逐, cached=0 |
| P3: Preemption 丢 decode | [MECHANISM] | **[MECHANISM+]** | 未触发preemption但机制分析确认; 排队策略是额外发现 |
| P6: Cache 层级不统一 | [PENDING] | **[MEASURED]** | Offload ON: store=14.96GiB, load=0; cached_tokens无差异 |

---

## 8. 论文关键数字

| 指标 | 值 | 来源 |
|------|-----|------|
| P2: vLLM L0 驱逐后 cached_tokens | 0 (完全驱逐) | [MEASURED] P2-A |
| P2: vLLM 驱逐阈值 | 5个不共享prefix请求 (~55K KV tokens) | [MEASURED] P2-B |
| P2: vLLM 被驱逐 blocks 数 | 5,829 | [MEASURED] P2-A |
| P2: SGLang L0 驱逐后 cached_tokens | 3 (几乎完全驱逐) | [MEASURED] S4 |
| P3: vLLM max concurrent running | 5 (at 95.5% KV usage) | [MEASURED] P3-A |
| P3: vLLM preemption count | 0 (排队策略) | [MEASURED] P3-A |
| P6: vLLM offload store_bytes | 14.96 GiB | [MEASURED] P6-A |
| P6: vLLM offload load_bytes | 0 bytes | [MEASURED] P6-A |
| P6: vLLM offload ON cached_tokens | 0 | [MEASURED] P6-A |
| P6: vLLM offload OFF cached_tokens | 0 | [MEASURED] P6-A |
| P1: SGLang 并发 cached_tokens | 8,517 (vs vLLM 0) | [MEASURED] S2 |
| P5: SGLang 每 turn 浪费 | ~50 tokens | [MEASURED] S1 |
