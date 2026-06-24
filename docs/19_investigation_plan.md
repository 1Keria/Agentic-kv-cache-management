# AgentKV 系统性调研计划：理解 vLLM KV Cache 机制 + 挖掘科研贡献点

> 日期: 2026-06-24
> 预计运行时间: ~8 小时（可独立执行，无需人工干预）
>
> **双重目标**：
> 1. **理解 vLLM 中 KV Cache 的完整管理方式**——从请求到达到 block 驱逐的每一步
> 2. **找出痛点作为日后科研贡献点**——每个痛点必须有数据量化 + 机制解释

---

## ⚠️ 核心原则：结果导向，不是流程导向

**之前的教训**：offloading 实验跑了，数据全一样，因为根本没触发驱逐机制。机械执行计划但结果全废。

**本次必须遵守**：

1. **每一步都验证结果是否合理**——Token 化完先看 L0 是否 ~6,157 tokens，不是就查原因；模拟完先看命中率曲线是否合理，不是就调参数
2. **发现问题立即修**——模拟没触发驱逐？降低容量直到触发。某个痛点数据不支持？放弃它找新的。脚本有 bug？修了重跑
3. **目标驱动选择方法**——目标是"找到可量化的痛点"，不是"跑完 4 个 Phase"。如果 Phase 1 就发现了意外的重要发现，直接深入，不必等 Phase 2
4. **不凑数据**——如果某个痛点在数据上站不住，就承认，不硬编理由
5. **计划和脚本只是参考起点**——随着实际情况调整，不是圣经。发现更好的方法就改，发现计划中的步骤无意义就跳过
6. **最终产出是可信的、有数据支撑的痛点**——不是"跑完了所有步骤"

**验证检查点**（每步完成后必须通过，不通过就停下来修）：

| 步骤 | 验证标准 | 不通过怎么办 |
|------|---------|------------|
| Phase 1 token 化 | L0 ≈ 6,157 tokens；session 数 = 767；增长比中位数 ~3.2x | 检查 tokenizer、Arrow 读取、L0/L1 识别逻辑 |
| Phase 2 模拟 | 无限容量命中率 ~99.7%；低容量时命中率下降；LRU ≤ Optimal | 检查 block hash、容量设置、warmup |
| Phase 3 痛点量化 | 每个痛点有具体数字（不是"可能""大概"）；数字与机制解释一致 | 重新分析或放弃该痛点 |
| Phase 5 vLLM 验证 | `kv_cache_usage_perc` > 0%；驱逐/preemption 实际发生；`[MEASURED]` 数据与模拟趋势一致 | 调整负载/容量参数重跑；如果某痛点无法在 vLLM 中复现，降级为"仅模拟支持" |
| Phase 4 报告 | 每个痛点可独立验证；优先级排序有依据 | 补充数据或调整排序 |

---

## 0. 为什么需要这个调研

当前 AgentKV 只确认了一个痛点：并发请求 prefix 命中率 0%。但这只是表面现象——我们缺少对 vLLM KV Cache 管理机制的完整理解，所以无法系统性地发现更多痛点。

**正确的调研路径**：先理解机制 → 再找机制与 Agent 工作负载的错配 → 每个错配就是一个潜在贡献点。

---

## Part I：理解 vLLM KV Cache 管理机制

### KV Cache Block 的完整生命周期

基于对 vLLM v1 源码的阅读，以下是一个 KV Cache Block 从生到死的完整路径：

```
请求到达 → Block Hash 计算 → Prefix 匹配 → Block 分配 → Cache 注册
    → 引用计数管理 → 请求完成/释放 → 进入 Free Queue → 被驱逐
```

#### 步骤 1：请求到达与 Block Hash 计算

**源码**：`vllm/v1/request.py` `__init__()` → `update_block_hashes()`
**Hash 函数**：`vllm/v1/core/kv_cache_utils.py` `get_request_block_hasher()`

- 请求创建时，立即计算所有**已满 block** 的 hash
- Hash 是**链式的**（类似 Merkle Tree）：每个 block 的 hash = `hash(parent_hash + block_token_ids + extra_keys)`
- 这意味着：如果 prefix 在第 i 个 block 发散，第 i 个之后的所有 block hash 都不同

**Agent 影响**：Agent 请求共享长 system prompt，链式 hash 确保了共享 prefix 产生相同的 block hash。但如果中间有任何插入/修改（如 prompt reordering），后续全部 block hash 都会变化。

#### 步骤 2：Prefix 匹配

**源码**：`vllm/v1/core/kv_cache_manager.py` `get_computed_blocks()` → `coordinator.find_longest_cache_hit()`
**实际匹配**：`single_type_kv_cache_manager.py` `find_longest_cache_hit()` (lines 522-569)

- 从左到右遍历 `block_hashes`，在 `BlockPool.cached_block_hash_to_block` 中查找
- **第一个 miss 就停止**——因为链式 hash，miss 之后必然全 miss
- 匹配到的 blocks 调用 `touch()` 增加引用计数，防止被驱逐

**Agent 影响**：同 session 多轮请求的 prefix 完全包含上一轮，匹配可以覆盖整个历史。但并发请求间无法匹配（见步骤 4）。

#### 步骤 3：Block 分配

**源码**：`vllm/v1/core/block_pool.py` `get_new_blocks()`

- 从 `free_block_queue` 的头部取出 blocks
- 取出前调用 `_maybe_evict_cached_block()` 清除 prefix cache 中的旧映射
- 设置 `ref_cnt = 1`

**Agent 影响**：多个共享 prefix 的请求都会 `touch()` 同一批 blocks，`ref_cnt` 累加。这保护了共享 prefix 但减少了可用 blocks 数。

#### 步骤 4：Cache 注册——关键步骤

**源码**：`vllm/v1/core/kv_cache_manager.py` `allocate_slots()` (lines 444-458)
**实际注册**：`block_pool.py` `cache_full_blocks()` (lines 211-331)

**重要发现**：vLLM 的 block 是在 `allocate_slots()` 期间注册的，**不是在请求完成后**！

```python
# allocate_slots() 中的关键代码
if not self.enable_caching or delay_cache_blocks:
    return self.create_kv_cache_blocks(new_blocks)

num_tokens_to_cache = min(
    total_computed_tokens + num_new_tokens,
    request.num_tokens,
)
self.coordinator.cache_blocks(request, num_tokens_to_cache)
```

每个满 block 在 prefill/decode 过程中就注册到 `cached_block_hash_to_block`。

**那为什么并发请求还是 miss？** 因为调度是按步进行的：
1. 请求 A 进入 scheduler，`allocate_slots()` 被调用
2. A 的 prefix blocks 被注册到 hash table
3. 但如果请求 B 在**同一步**被调度，B 的 `find_longest_cache_hit()` 在 A 的 blocks 注册之前就执行了
4. 所以 B 看不到 A 的 blocks

这是**调度粒度**的问题，不是"请求完成后才注册"的问题。之前的分析不够精确。

#### 步骤 5：引用计数管理

**源码**：`vllm/v1/core/kv_cache_utils.py` `KVCacheBlock` (lines 116-163)

| 事件 | ref_cnt 变化 | 效果 |
|------|-------------|------|
| Block 分配 (`get_new_blocks`) | 设为 1 | Block 被请求持有 |
| Prefix 命中 (`touch`) | +1 | 共享 block 被多个请求持有 |
| Block 释放 (`free_blocks`) | -1 | 请求不再需要此 block |
| ref_cnt 降到 0 | — | Block 进入 free queue，成为驱逐候选 |

**关键**：ref_cnt > 0 的 block **不会**在 free queue 中，**不可能**被驱逐。只有 ref_cnt = 0 的 block 才是驱逐候选。

**Agent 影响**：如果 10 个请求共享 L0 prefix，L0 blocks 的 ref_cnt = 10。只要有一个请求还在运行，L0 就不会被驱逐。但如果所有 10 个请求同时完成或被 preempt，L0 的 ref_cnt 瞬间降为 0，立即变成驱逐候选。

#### 步骤 6：Free Queue 与驱逐

**源码**：`vllm/v1/core/kv_cache_utils.py` `FreeKVCacheBlockQueue` (lines 165-394)

- Free queue 是双向链表，**头部是最久未用的 blocks**（LRU 顺序）
- 新释放的 cached blocks 追加到尾部（低驱逐优先级）
- 新释放的 uncached blocks 插入到头部（高驱逐优先级——先重用无 cache 价值的）
- 分配时从头部取：`popleft_n()`

**驱逐逻辑**：`_maybe_evict_cached_block()` (block_pool.py lines 365-400)
- 当一个 cached block 从 free queue 头部被取出重新分配时
- 从 `cached_block_hash_to_block` 中删除
- 重置 block hash
- 该 block 的 prefix cache 映射永久丢失

**Agent 影响**：LRU 驱逐意味着最久未访问的 prefix 最先被驱逐。对于 Agent 工作负载，如果一组共享 L0 的 session 都完成了一段时间，L0 blocks 可能成为最"老"的 blocks 被优先驱逐。

#### 步骤 7：请求完成

**源码**：`scheduler.py` `_free_request()` (lines 1947-1964)

- 调用 `kv_cache_manager.free(request)` 释放所有 blocks
- ref_cnt 递减，降到 0 的 blocks 进入 free queue
- **但 blocks 保留 block_hash，仍在 `cached_block_hash_to_block` 中**
- 后续请求仍可通过 hash table 找到这些 blocks

**Agent 影响**：请求完成后，共享 prefix blocks 仍在 cache 中。但如果 GPU 内存紧张，新请求的分配会从 free queue 头部取走这些 blocks，驱逐其 prefix cache 映射。

#### 步骤 8：Offloading

**源码**：`vllm/v1/kv_offload/base.py`, `distributed/kv_transfer/kv_connector/v1/offloading/`

- Offloading 是**独立于 GPU prefix cache 的另一层**
- 有自己的 hash table（`OffloadingManager`，key 为 `OffloadKey`）
- 一个 block 可以同时在 GPU prefix cache 和 CPU offload tier 中
- **默认 `offload_prompt_only=True`**：decode 阶段的 KV blocks 不被 offload
- 加载是异步的：GPU miss → 检查 offload tier → 异步 load → 等待完成

**Agent 影响**：Agent 的推理/工具调用输出（decode tokens）不被 offload。一旦 GPU 驱逐这些 blocks，它们就永久丢失，必须完全重算。而 system prompt 可以被 offload，但 GPU prefix cache 和 offload tier 的驱逐策略独立运行，可能不同步。

#### 步骤 9：Preemption

**源码**：`scheduler.py` `_preempt_request()` (lines 1033-1054)

- 当 `allocate_slots()` 返回 None（内存不足），scheduler preempt 最低优先级的 running 请求
- **所有 blocks 立即释放**：`kv_cache_manager.free(request)`
- **`request.num_computed_tokens = 0`**——请求忘记所有进度
- 请求被放回 waiting queue，重新调度时从零开始
- 恢复依赖 prefix cache：如果 blocks 还在 cache 中（未被驱逐），可以恢复

**Agent 影响**：这是 Agent 工作负载**最严重的问题**。一个已生成数千 tokens 推理输出的 Agent 请求被 preempt 后，`num_computed_tokens` 归零。重新调度时，prefix cache 可以恢复 system prompt，但**所有 decode 输出的 blocks 必须完全重算**——因为：
1. Decode blocks 没有被 offload（`offload_prompt_only=True`）
2. Decode blocks 的 ref_cnt 降为 0，可能已被其他请求的 blocks 覆盖
3. 即使 blocks 还在 free queue 中，hash 映射已被 `_maybe_evict_cached_block()` 清除

---

### 机制理解总结：Agent 工作负载的 9 个错配点

| # | 机制 | Agent 工作负载特征 | 错配 |
|---|------|-------------------|------|
| M1 | 链式 Block Hash | Agent prompt 有 L0/L1/L2 层次 | 中间插入内容会使后续全部 block hash 失效 |
| M2 | Left-to-right break-on-miss | 多轮对话 prefix 严格递增 | 理论上匹配效果好，但并发时失效 |
| M3 | 调度步内无法跨请求共享 | Agent 经常并发启动 | 并发请求无法利用彼此的 prefix |
| M4 | ref_cnt 累加保护共享 blocks | 多请求共享 L0 | L0 占用 blocks 数 = 并发请求数 × L0 blocks |
| M5 | LRU free queue 驱逐 | L0 价值高但可能"老" | L0 可能因长时间未被新请求 touch 而被驱逐 |
| M6 | 请求完成后 blocks 保留在 cache | Session 间有长空闲 | 空闲期 L0 blocks 可能被新项目请求驱逐 |
| M7 | offload_prompt_only=True | Agent decode 输出很长 | Decode 输出被驱逐后永久丢失 |
| M8 | Preemption 时 num_computed_tokens=0 | Agent 请求运行时间长 | 被抢占后必须完全重算 decode 输出 |
| M9 | GPU prefix cache 与 offload tier 独立管理 | 两个 tier 应该协同 | 可能出现 GPU 有但 offload 没有，或反之 |

---

## Part II：用数据验证和量化痛点

> **核心方法**：每个阶段都做 **理论分析 + vLLM 实测** 配对。理论分析快速发现模式，vLLM 实测确认真实行为。
> **每次实测前重新部署 vLLM server**，确保 KV cache 完全清空，避免前次残留影响结果。

### 可用数据

| 资源 | 位置 | 说明 |
|------|------|------|
| LMCache Agentic Traces | `experiments/vllm_kv_cache/lmcache_traces/` | 24,880 条请求，767 个 session，5 个 Arrow 文件 |
| kvcache-blog precomputed.json | `kvcache-blog/data/kv_cache_lab/precomputed.json` | 7 条 trace 的容量-命中率曲线（仅 1,200/24,880 行） |
| C++ 模拟器 | `kvcache-blog/scripts/kv-cache-lab-native-sim.cc` | FIFO/LRU/Optimal + prefix-aware trie |
| vLLM 实验基础设施 | `scripts/exp_utils.py` | send_and_record, KVTimelineCollector, Prometheus |

---

### Phase 1：Trace 特征画像 — Prefix 层次与增长（0-3h）

#### 1A. 理论分析：`scripts/investigate_trace_tokenizer.py`

**目标**：对全部 24,880 条请求用 tiktoken 精确分词，建立 Agent 工作负载的精确特征画像。

**处理步骤**：
1. 用 `pyarrow.ipc.open_stream()` 加载 5 个 Arrow 文件
2. 对每条消息用 tiktoken cl100k_base 分词
3. 识别 L0/L1/L2 边界：L0=system 消息，L1=项目级共享前缀，L2=动态内容
4. 对 turn > 0：`prefix_reusable` = 前轮 total_tokens，`incremental` = 本轮新增

**聚合输出**：

| 输出 | 对应机制错配 | 量化什么 |
|------|------------|---------|
| A. L0/L1/L2 分解表 | M4 | 共享 prefix 占首轮输入的比例 |
| B. 逐轮输入增长曲线 | M7/M8 | decode 输出增长 → preemption 代价 |
| C. Session KV 占用分布 | M5/M6 | KV 占用超出容量 → 驱逐风险 |
| D. 跨 session prefix 重叠 | M4 | 共享 L0 占用的 blocks 数 |
| E. 并发到达模式 | M3 | 并发场景的频率和影响 |

#### 1B. vLLM 实测：单 session 多轮回放

**目标**：用 vLLM 实际推理验证理论分析的数字——特别是 prefix 增长和 KV 占用。

**实验设计**：
1. **重新部署 vLLM server**（gpu_util=0.3, APC enabled, offload=8GiB）
2. 从 LMCache trace 选 1 个长 session（30+ 轮），逐轮串行发送真实消息
3. 每轮记录：`cached_tokens`, `TTFT`, `kv_cache_usage_perc`
4. 绘制 KV 占用随 turn 增长的实测曲线，与 1A 的 B/C 对比
5. **验证**：实测的 `cached_tokens` 是否与理论计算的 `prefix_reusable_tokens` 一致？

**如果不符合预期**（如 cached_tokens 远小于理论值）→ 查 vLLM 源码解释原因，不凑数据。

---

### Phase 2：容量压力分析 — 驱逐行为（3-5h）

#### 2A. 理论分析：C++ 模拟器容量扫描

**脚本**：`investigate_prepare_sim_trace.py` + `investigate_run_simulations.py`

**目标**：用 tiktoken token ID 做 prefix-aware blake2b 哈希，转为 C++ 模拟器格式，在多种容量点下运行。

**容量扫描**：
- block_size=16 (vLLM)：500 到 10,000 blocks，~30 个点
- block_size=64 (SGLang)：同样扫描
- 每点跑 FIFO/LRU/Optimal
- warmup = 12,000 请求

**关键分析**：
- LRU vs Optimal 差距 → 量化 M5（LRU 是否优先驱逐高价值 prefix？）
- 逐请求命中率 → 量化 M3（并发请求的命中率缺口）
- block_size 对比 → 量化 M1/M2（block 边界浪费）
- 不同容量下命中率 → 量化 M6（容量压力下 prefix 保留率）

**⚠️ 验证**：模拟跑完必须检查——无限容量 ~99.7%；低容量命中率下降；LRU ≤ Optimal。不通过就停下来修。

#### 2B. vLLM 实测：多 session 并发触发驱逐

**目标**：在 vLLM 中制造真实的内存压力，观察驱逐行为。

**实验设计**：
1. **重新部署 vLLM server**（gpu_util=0.3, APC enabled, LOG_LEVEL=debug）
2. Phase 1: 串行发送 3 个 django session 的前 10 轮（KV 占用递增）
3. Phase 2: 串行发送 2 个 sympy session 的前 5 轮（增加 KV 占用）
4. 观察 `kv_cache_usage_perc` 是否接近 100%
5. 如果没触发驱逐 → 继续增加 session 或轮次
6. 记录 DEBUG 日志中的 evict/preempt 事件

**如果没触发驱逐** → 继续增加负载，直到 `kv_cache_usage_perc > 80%`。不记录无效数据。

---

### Phase 3：逐痛点深度分析（5-12h）

> **配对策略**：每个痛点都做 理论分析（模拟/trace 计算） + vLLM 实测（真实推理验证）
> **每次实测前重新部署 vLLM server**，确保 KV cache 完全清空

**⚠️ 痛点存活标准**：每个痛点必须通过：
- 理论分析有具体数字，可复现
- vLLM 实测能复现理论预测的行为（如果不一致，分析原因，不凑数据）
- 对比 SGLang 后确实存在差距

---

#### P1：并发请求无法跨请求共享 Prefix（M3）

**1A. 理论分析**：
- 从 pre_gap 计算并发概率：N 个 session 同时运行时，调度窗口内同时到达的概率
- 模拟：并发请求的命中率缺口 = 串行命中率 - 并发命中率
- TTFT 影响：每个 miss 的请求多算 ~6,000-8,000 tokens

**1B. vLLM 实测**：
1. **重新部署 vLLM server**（gpu_util=0.3, APC enabled）
2. asyncio.gather 同时发送 3 个同项目 session 首轮请求 → 记录 `cached_tokens`
3. **重新部署 vLLM server**（清空 KV cache）
4. 串行发送同样 3 个请求 → 记录 `cached_tokens`
5. 对比：并发 vs 串行的 cached_tokens 和 TTFT

**预期**：并发时所有请求 `cached_tokens ≈ 0`；串行时第 2/3 个 `cached_tokens ≈ L0+L1`

**科研方向**：Eager prefix registration / In-batch prefix caching

---

#### P2：LRU 可能优先驱逐共享 System Prompt（M5/M6）

**2A. 理论分析**：
- 模拟中找到 LRU vs Optimal 差距最大的容量点
- 分析"丢失的 tokens"是否集中在 L0 tokens（6,157）
- 构造场景：N 个同项目 session 完成 → M 个新项目 session 到达 → L0 是否被驱逐？

**2B. vLLM 实测**：
1. **重新部署 vLLM server**（gpu_util=0.3, APC enabled, LOG_LEVEL=debug）
2. Phase 1: 串行发送 5 个 django session 前 10 轮 → L0+L1 缓存建立
3. Phase 2: 串行发送 5 个 sympy session 前 10 轮 → 占用更多 KV
4. Phase 3: 发送 1 个新 django session 首轮 → 观察 `cached_tokens` 是否包含 L0
5. 如果 `cached_tokens < L0_tokens`，说明 L0 被驱逐

**如果没触发驱逐** → 继续 Phase 1/2 增加轮次，直到 `kv_cache_usage_perc > 80%` 再做 Phase 3

**科研方向**：Agent-aware eviction policy（保护 L0/L1）

---

#### P3：Preemption 导致 Decode 输出完全丢失（M8）

**3A. 理论分析**：
- 从 Phase 1 数据计算每个 session 的 decode 输出累积量（`output_length` 累积）
- 在不同 GPU 容量下，计算 preemption 概率和重算代价

**3B. vLLM 实测**：
1. **重新部署 vLLM server**（gpu_util=0.3, LOG_LEVEL=debug）
2. 先让一个 session 运行 10+ 轮（积累大量 decode KV）
3. 然后并发发送多个新请求，触发 preemption
4. 观察 Prometheus `num_preemptions > 0`
5. 被 preempt 的请求重新调度后，测量其 TTFT（应接近冷启动）
6. 对比：未被 preempt 的请求 TTFT vs 被 preempt 的 TTFT

**科研方向**：Offload decode blocks / Partial preemption / Progressive checkpointing

---

#### P4：Prefix 增长导致递增内存压力（M4/M7）

**4A. 理论分析**：
- 从 Phase 1 计算每个 session 在每轮的实际 KV 占用
- 计算不同并发数下的总 blocks 需求
- 对比 GPU 容量，计算何时触发驱逐

**4B. vLLM 实测**：
1. **重新部署 vLLM server**（gpu_util=0.3）
2. 同时回放 3 个 session，各跑到 10 轮
3. 每轮记录 `kv_cache_usage_perc`
4. 绘制 KV 占用增长轨迹，与理论计算对比

**科研方向**：KV cache 增长预测 / 动态 offloading / Session grouping

---

#### P5：Block 边界浪费对短 Agent Turn 的影响（M1/M2）

**5A. 理论分析**：
- 从 Phase 1 逐轮数据计算每轮 block 对齐浪费
- 累计整个 session 总浪费
- 对比 block_size=16 vs 64 vs token-level

**5B. vLLM 实测**：
1. **重新部署 vLLM server**（gpu_util=0.3, APC enabled）
2. 串行发送同一 session 的 5 轮消息
3. 每轮记录 `cached_tokens`，计算 `理论 prefix_reusable - 实测 cached_tokens` = block 浪费
4. 与理论分析的 block 对齐预期对比

**预期**：浪费量 ≈ `incremental_tokens % block_size`，不超过 15 tokens/轮 (bs=16)

**科研方向**：Variable-size block caching（类似 SGLang radix tree）

---

#### P6：GPU Prefix Cache 与 Offload Tier 独立管理（M9）

**6A. 理论分析**：
- 模拟 offloading 场景：GPU 容量有限，L0 blocks 被驱逐后能否从 offload 恢复？
- 对比：integrated offloading vs 独立管理

**6B. vLLM 实测**：
1. **重新部署 vLLM server**（gpu_util=0.3, APC enabled, **offload=8GiB**）
2. 制造驱逐场景（同 P2B）
3. Phase 3: 发送新 django 请求 → 观察 `cached_tokens`
4. **重新部署 vLLM server**（gpu_util=0.3, APC enabled, **offload=0GiB**）
5. 同样场景 → Phase 3: 发送新 django 请求 → 观察 `cached_tokens`
6. 对比：offload on vs offload off 的 prefix 命中率是否一样？

**预期**：如果 offload 与 prefix cache 不集成，on 和 off 的 `cached_tokens` 应一样

**科研方向**：Unified cache hierarchy（类似 SGLang HiCache）

---

#### P7：无调度感知导致混合项目负载下 Prefix 复用降低（M3 扩展）

**7A. 理论分析**：
- 构造混合项目场景：3 个 django + 2 个 sympy 请求同时到达
- 对比 FCFS vs LPM 调度的总 prefill tokens

**7B. vLLM 实测**：
1. **重新部署 vLLM server**（gpu_util=0.3, APC enabled）
2. asyncio.gather 同时发送 3 个 django + 2 个 sympy 首轮请求 → 记录 `cached_tokens`
3. **重新部署 vLLM server**（清空 KV cache）
4. 串行发送：先 3 个 django，再 2 个 sympy（最大化 prefix 复用的调度顺序）→ 记录 `cached_tokens`
5. 对比：并发 vs 最优调度顺序的总 prefill tokens

**科研方向**：Prefix-aware scheduling

---

### Phase 4：优先级排序与报告生成（12-13h）

#### 脚本：`scripts/investigate_generate_report.py`

#### 优先级矩阵

| 痛点 | 机制错配 | 影响 | 新颖性 | 可操作性 | 优先级 |
|------|---------|------|--------|---------|--------|
| P1: 并发共享失效 | M3 调度步内无法跨请求共享 | 6,000-8,000 tokens/请求 | 高（首次精确量化） | 高（eager registration） | **CRITICAL** |
| P3: Preemption 丢失 decode | M8 num_computed_tokens=0 | 整个 decode 输出重算 | 高（Agent 特有） | 高（offload decode / partial preempt） | **HIGH** |
| P2: LRU 驱逐 L0 | M5/M6 共享 prefix 被优先驱逐 | 6,157 tokens/受影响请求 | 高（Agent 特有病理） | 高（priority eviction） | **HIGH** |
| P4: Prefix 增长压力 | M4/M7 共享 blocks 累加 | 22,000+ tokens (3.2x) | 中 | 中（增长预测 + 动态 offload） | HIGH |
| P6: Cache 层级不统一 | M9 GPU/offload 独立管理 | 6,157 tokens | 高（隐蔽但影响大） | 高（unified hierarchy） | MEDIUM-HIGH |
| P7: 无调度感知 | M3 扩展 FCFS 不考虑 prefix | 2,000-4,000 tokens/批次 | 中 | 高（LPM-style 调度） | MEDIUM |
| P5: Block 边界浪费 | M1/M2 链式 hash + 固定 block_size | 465-1,333 tokens/session | 低（已知问题） | 中（variable-size caching） | MEDIUM |

#### 输出结构

```
investigation_report/
  00_executive_summary.md              # 执行摘要
  01_vllm_kv_cache_mechanics.md        # Part I：vLLM KV Cache 机制完整解析
  02_trace_characterization.md         # Phase 1：Trace 特征分析 [理论]
  03_vllm_single_session.md            # Phase 1：单 session 回放 [MEASURED]
  04_simulation_results.md             # Phase 2：模拟结果 [SIMULATED]
  05_vllm_eviction_trigger.md          # Phase 2：驱逐触发 [MEASURED]
  06_pain_point_1_concurrent.md        # 每个痛点：机制 → 理论量化 → vLLM 实测 → SGLang 对比 → 贡献方向
  07_pain_point_2_lru_evicts_l0.md
  08_pain_point_3_preemption_decode.md
  09_pain_point_4_prefix_growth.md
  10_pain_point_5_block_waste.md
  11_pain_point_6_cache_hierarchy.md
  12_pain_point_7_scheduling.md
  13_prioritization_matrix.md          # 优先级矩阵 + 论文 Motivation 建议
  figures/
    fig1_l0_l1_l2_breakdown.pdf
    fig2_input_growth_by_turn.pdf
    fig3_hit_rate_vs_capacity.pdf
    fig4_lru_vs_optimal.pdf
    fig5_block_waste_comparison.pdf
    fig6_concurrent_hit_rate_gap.pdf
    fig7_session_kv_footprint.pdf
    fig8_vllm_kv_usage_over_turns.pdf   # vLLM 验证：KV 占用随轮次增长
    fig9_vllm_eviction_impact.pdf        # vLLM 验证：驱逐对 prefix 命中率的影响
  data/
    tokenized_traces_summary.json
    simulation_results.json
    pain_point_metrics.json
    vllm_verification_results.json       # vLLM 验证数据 [MEASURED]
```

---

## 时间预算

| 时段 | 活动 | 产出 |
|------|------|------|
| 0.0-0.5 | 编写 `investigate_trace_tokenizer.py` | 脚本就绪 |
| 0.5-2.0 | 运行 tokenizer 处理全部 24,880 行 | `tokenized_traces_summary.json` |
| 2.0-2.5 | **1B vLLM 实测**：单 session 多轮回放 | 实测 KV 增长曲线 [MEASURED] |
| 2.5-3.0 | 编写 `investigate_prepare_sim_trace.py` | 脚本就绪 |
| 3.0-3.5 | 运行 trace 准备 + 编译 C++ 模拟器 | 模拟器就绪 |
| 3.5-4.5 | 编写 `investigate_run_simulations.py` + 运行容量扫描 | `simulation_results.json` |
| 4.5-5.0 | **2B vLLM 实测**：多 session 触发驱逐 | 实测驱逐行为 [MEASURED] |
| 5.0-5.5 | 编写 `investigate_pain_points.py` + `investigate_vllm_verify.py` | 脚本就绪 |
| 5.5-7.0 | P1-P7 理论分析 | `pain_point_metrics.json` |
| 7.0-12.0 | P1-P7 vLLM 实测（**每个痛点前重新部署 server**） | 各痛点的 [MEASURED] 数据 |
| 12.0-12.5 | 更新报告：整合理论 + 实测结果 | 最终报告 |

**⚠️ 时间预算是参考，不是硬约束**：
- 如果某个痛点的实测结果与理论不符，花时间分析原因
- 如果某个痛点在 vLLM 中无法复现，如实记录，降级为"仅模拟支持"
- **最终目标是产出可信的痛点，不是跑完所有步骤**

---

## 实验配置

### 硬件

| 组件 | 规格 |
|------|------|
| GPU | 8× NVIDIA H800 (80GB each)，当前全部空闲 |
| CPU | 可用（tiktoken 多进程） |
| 磁盘 | 43TB 可用（Lustre FS） |
| C++ 编译器 | g++ 13.3.0 |

### 模型

| 参数 | 值 |
|------|-----|
| 模型 | Qwen3-8B |
| 路径 | `/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/...` |
| num_layers | 36 |
| num_kv_heads | 8 |
| head_dim | 128 |
| KV bytes/token | 147,456 (144 KB) |
| block_size | 16 (vLLM 默认) |

### GPU KV Cache 容量

| gpu_memory_utilization | 可用 KV 容量 | blocks (bs=16) | 说明 |
|------------------------|------------|---------------|------|
| 0.3 | ~44,000 tokens | ~2,750 | 之前实验用的配置，短请求不够触发驱逐 |
| 0.5 | ~174,000 tokens | ~10,922 | 更大，需要更多并发请求 |

**触发驱逐策略**：gpu_util=0.3 时 44K tokens 容量，3-5 个 session 各跑 10+ 轮即可超出容量（每个 session 后期 ~15-20K tokens）。用真实 LMCache trace 的多轮消息回放。

### vLLM Server 部署约定

**每次实测前**：
```bash
# 1. Kill 旧 server
lsof -ti :8000 | xargs kill -9 2>/dev/null; sleep 3

# 2. 重新部署（根据需要调整参数）
bash scripts/run_vllm_server.sh [gpu_util] [port]
# 环境变量控制：
#   KV_OFFLOAD_GIB=8      # offloading 大小（0=关闭）
#   LOG_LEVEL=debug        # 调试日志（看 evict/preempt 事件）

# 3. 等待 server 就绪
python -c "import openai; c=openai.Client(base_url='http://localhost:8000/v1'); c.models.list()"
```

### Python 环境

| 包 | 状态 |
|----|------|
| tiktoken | ✅ |
| pyarrow | ✅ |
| matplotlib | ✅ |
| numpy | ✅ |
| scipy | ✅ |
## 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 分词器 | tiktoken cl100k_base | 已验证 L0 = 6,157 tokens |
| Block 哈希 | prefix-aware blake2b | 参考 `sglang-log-to-kvcache-trace.py` |
| Block 大小 | 16 (vLLM) + 64 (SGLang) | 对比两种粒度 |
| 容量模型 | 100-10,000 blocks (bs=16) | 覆盖从严重压力到充足容量 |
| Warmup | 12,000 请求 | 匹配 JS 模拟的 0.5 warmup fraction |

---

## 验证检查

| 检查项 | 预期值 |
|--------|--------|
| L0 token 数 | 6,157 ± 10 tokens |
| Session 数 | 767 sessions, 24,880 total rows |
| 增长比 | 中位数 last/first ~3.2x |
| 模拟命中率上限 | 无限容量时 ~99.7% |
| Block 浪费 | block_size=16 时每增量浪费 0-15 tokens |

---

## 关键文件索引

| 文件 | 用途 |
|------|------|
| `Engine/vllm/vllm/v1/core/kv_cache_manager.py` | KV Cache 管理器入口 |
| `Engine/vllm/vllm/v1/core/single_type_kv_cache_manager.py` | 单类型 KV Cache 管理（prefix 匹配、block 分配） |
| `Engine/vllm/vllm/v1/core/block_pool.py` | Block 池（分配、释放、驱逐、cache 注册） |
| `Engine/vllm/vllm/v1/core/kv_cache_utils.py` | Block hash、Free queue、工具函数 |
| `Engine/vllm/vllm/v1/core/sched/scheduler.py` | 调度器（preempt、free request） |
| `Engine/vllm/vllm/v1/request.py` | Request 类（block hash 计算） |
| `Engine/vllm/vllm/v1/kv_offload/base.py` | Offloading 基类 |
| `experiments/vllm_kv_cache/lmcache_traces/data-*.arrow` | 主数据源 |
| `kvcache-blog/scripts/kv-cache-lab-native-sim.cc` | C++ 模拟器 |
| `kvcache-blog/scripts/sglang-log-to-kvcache-trace.py` | blake2b 哈希参考 |
| `scripts/exp_utils.py` | 现有实验基础设施 |
