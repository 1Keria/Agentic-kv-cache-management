# vLLM KV Cache 补强实验说明

> 日期: 2026-06-25
> 目标: 将 P2、P3、P6 的证据等级从 [SIMULATED]/[MECHANISM]/[PENDING] 提升至 [MEASURED]
> 原则: 不修改 vLLM 源码，所有实验使用已部署的 vLLM server

---

## 0. 实验环境


| 项目              | 值                                                             |
| --------------- | ------------------------------------------------------------- |
| GPU             | NVIDIA H800 × 1 (81 GB)                                       |
| 模型              | Qwen3-8B                                                      |
| Conda env       | `agentkv_zls` (Python 3.11.15)                                |
| vLLM            | 0.8.5.dev0 (editable install)                                 |
| KV 容量           | 3,317 blocks = **53,072 tokens** (gpu_memory_utilization=0.3) |
| Block size      | 16 tokens                                                     |
| Prefix cache    | ON (xxhash)                                                   |
| Chunked prefill | ON (max_num_batched_tokens=8192)                              |
| Watermark       | 0.02 (~66 blocks 预留)                                          |


### 启动方式

```bash
CUDA_VISIBLE_DEVICES=0 \
LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64 \
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python -m vllm.entrypoints.openai.api_server \
  --model <MODEL_PATH> \
  --served-model-name Qwen3-8B \
  --block-size 16 \
  --enable-prefix-caching --prefix-caching-hash-algo xxhash \
  --enable-prompt-tokens-details \
  --kv-cache-metrics --kv-cache-metrics-sample 1.0 \
  --watermark 0.02 --enable-chunked-prefill \
  --gpu-memory-utilization 0.3 \
  --max-model-len 32768 \
  --port 8000
```

> ⚠️ **不要**添加 `/usr/local/cuda-13.0/compat` 到 `LD_LIBRARY_PATH`！该目录包含旧版 libcuda.so (580.95.05)，会覆盖系统驱动 (595.58.03) 导致 CUDA Error 803。

### 关键 API

- **OpenAI API**: `http://localhost:8000/v1`
- **Prometheus**: `http://localhost:8000/metrics`
- **cached_tokens**: 需 `--enable-prompt-tokens-details`，在 `usage.prompt_tokens_details.cached_tokens` 返回
- **驱逐指标**: `kv_block_lifetime_seconds_count`（累计被驱逐 block 数）
- **Offload 指标**: `kv_offload_store_bytes_total` / `kv_offload_load_bytes_total`

---

## 1. P2: LRU 驱逐 L0 的实测验证

### 1.1 背景

**L0** 是 Agent 的 system prompt（6,163 tokens），所有项目共享。在 vLLM 的 prefix cache 中，L0 被注册为一系列 hash blocks。当 KV cache 容量不足时，vLLM 从 `free_block_queue` 头部（LRU 顺序）分配 blocks，如果弹出的 blocks 有 hash 就隐式驱逐。

之前的实验（exp5/exp6）**从未触发真实驱逐**，因为串行模式下请求完成后 blocks 释放回 free pool，但 prefix cache blocks 仍在 hash table 中。

### 1.2 关键洞察：为什么之前的实验失败


| 之前的策略             | 为什么失败                                           |
| ----------------- | ----------------------------------------------- |
| 串行发送多个 session    | 请求完成后 blocks 释放，free pool 充足，不需要驱逐              |
| 并发发送共享 prefix 的请求 | vLLM 通过 prefix cache 共享 L0 blocks，实际 KV 占用远低于总量 |
| max_tokens=5      | Decode 输出太短，KV 占用瞬间释放                           |


**新策略**：并发发送**不共享 prefix** 的长输出请求，让每个请求的 KV 占用完全独立。

### 1.3 实验 P2-A：触发 L0 驱逐

**实验设计**：

```
Phase 1: 串行发送 1 个 django turn 0 → 建立 L0+L1 缓存基线
Phase 2: 并发发送 9 个 UUID 前缀的请求（max_tokens=2000）
         每个请求 ~10K prompt + ~1K decode = ~11K KV tokens
         9 × 11K = 99K >> 53K 容量 → 强制驱逐
Phase 3: 发送新 django turn 0 → 测试 L0 是否被驱逐
```

**为什么用 UUID 前缀**：`make_text_with_token_count(seed)` 不同 seed 产生相同文本开头（BPE 重复填充），vLLM 会通过 prefix cache 命中。必须用 UUID 开头确保每个请求的 prefix 完全不同。

**结果**（`run_5_u9_mt2000.json`）：


| Phase   | 指标                     | 值                      |
| ------- | ---------------------- | ---------------------- |
| Phase 1 | baseline cached_tokens | **10,064**（L0+L1 完整命中） |
| Phase 1 | baseline TTFT          | 677.3 ms               |
| Phase 2 | 总 prompt tokens        | 89,901                 |
| Phase 2 | 总 completion tokens    | 10,025                 |
| Phase 2 | 估算总 KV tokens          | ~99,926（远超 53,072 容量）  |
| Phase 3 | **test cached_tokens** | **0**                  |
| Phase 3 | test TTFT              | 329.5 ms（冷启动重算）        |


**Prometheus 驱逐指标**：


| 指标                                         | 值         | 含义                     |
| ------------------------------------------ | --------- | ---------------------- |
| `kv_block_lifetime_seconds_count`          | **5,829** | 累计 5,829 个 blocks 被驱逐  |
| `kv_block_idle_before_evict_seconds_count` | **5,829** | 5,829 个 blocks 从空闲到被驱逐 |
| `kv_cache_usage_perc`（运行时峰值）               | 95.5%     | 从 server 日志确认          |


**结论**：✅ **L0 被完全驱逐**。5,829 个 prefix cache blocks 在 9 个并发请求的压力下被 LRU 驱逐。Phase 3 的新请求 cached_tokens=0，需要完全冷启动重算全部 10,073 个 prompt tokens。

### 1.4 实验 P2-B：压力扫描——驱逐临界点

**目的**：找到 L0 被驱逐的精确压力阈值。

**方法**：依次发送 N=3,4,5,6 个不共享 prefix 的并发请求，每次测试后检查 L0 存活状态。

**结果**（`run_3_pressure_sweep.json`）：


| 压力请求数 | 估算 KV 需求 | cached_tokens | L0 状态            | TTFT     |
| ----- | -------- | ------------- | ---------------- | -------- |
| 3     | ~33K     | **10,064**    | ✅ 完整保留           | 191.6 ms |
| 4     | ~44K     | **9,664**     | ⚠️ L1 部分丢失（-400） | 55.7 ms  |
| 5     | ~55K     | **0**         | ❌ 完全驱逐           | 319.3 ms |
| 6     | ~66K     | **0**         | ❌ 完全驱逐           | 317.8 ms |


**关键发现**：

- **4 个压力请求**是临界点：L0+L1 大部分保留（10,064 → 9,664，L1 丢失 400 tokens = 25 blocks）
- **5 个压力请求**导致 L0 完全被驱逐
- 驱逐是"全有或全无"的：要么 L0 基本保留，要么完全丢失

### 1.5 实验 P2-B：Touch 操作能否保护 L0

**目的**：测试通过"touch"（发送请求刷新 L0 在 free queue 中的位置）能否在压力下保护 L0。

**方法**：

- 配置 A（LRU）：Phase 1 建缓存 → Phase 2 施压 → Phase 3 测试
- 配置 B（Aware）：Phase 1 建缓存 → **Phase 1.5 touch L0** → Phase 2 施压 → Phase 3 测试

**结果**（`run_4_touch_vs_lru.json`）：


| 配置               | cached_tokens | TTFT     |
| ---------------- | ------------- | -------- |
| LRU（无 touch）     | 0             | 318.0 ms |
| Aware（有 touch）   | 0             | 442.7 ms |
| 对照（4 压力，无 touch） | 10,064        | 326.5 ms |


**关键发现**：❌ **Touch 操作无法保护 L0**。原因：

1. Touch 只在请求进行时将 L0 blocks 的 ref_cnt 从 0 提升到 1
2. 请求完成后 ref_cnt 回到 0，blocks 回到 free queue 尾部
3. 5 个压力请求需要的 blocks 数量（~~55K）远超可用空间（~~53K），连尾部 blocks 也被分配
4. Aware 配置的 TTFT 反而更高（442.7 ms vs 318.0 ms），因为 touch 请求本身也消耗了 KV 空间

**结论**：简单的请求调度策略无法有效保护 L0，需要系统级的 Agent-Aware 驱逐优先级机制。

---

## 2. P3: Preemption 导致 Decode 输出丢失

### 2.1 背景

vLLM 的 `_preempt_request()` 会设 `num_computed_tokens=0`，释放所有 blocks（包括 decode 输出）。`offload_prompt_only=True` 使得 decode blocks 不被 offload 到 CPU。理论上，preemption 会导致 decode 输出永久丢失。

### 2.2 实验 P3-A：尝试触发 Preemption

**尝试 1**：9 个不共享 prefix 的并发请求（max_tokens=4000）

从 server 日志观察到：

```
Running: 5 reqs, Waiting: 4 reqs, GPU KV cache usage: 95.5%
```

**关键发现**：vLLM 将 9 个请求分为 5 running + 4 waiting，而非抢占 running 请求来容纳 waiting 请求。`num_preemptions=0`。

**尝试 2**：PRIORITY 调度 + 高优先级请求

启用 `--scheduling-policy priority`，发送 5 个低优先级长请求 + 1 个高优先级请求。结果：`num_preemptions=0`，高优先级请求被放入 waiting queue 等待。

### 2.3 为什么 Preemption 无法触发

通过源码分析（`scheduler.py:474-522`）：

```
for each running request:
    new_blocks = allocate_slots(request, num_new_tokens)
    if new_blocks is None:
        → preempt the lowest-priority running request  ← 只在这里触发
    else:
        → schedule normally
```

**Preemption 只在 `allocate_slots()` 对 running 请求返回 None 时触发**。但：

- Decode 阶段每 step 只需 **1 个 block**
- Watermark 保留 ~66 blocks
- 即使 KV usage=95.5%，仍有 ~165 free blocks
- 5 个 running 请求 × 1 block/step = 5 blocks << 165 free blocks
- **所以 decode 阶段的 running 请求永远能分配到 blocks**

新请求（waiting queue）分配失败时，调度器只是**不调度它**，不会 preempt running 请求来腾出空间。

### 2.4 结论


| 发现             | 说明                                                                                             |
| -------------- | ---------------------------------------------------------------------------------------------- |
| Preemption 未触发 | vLLM v1 调度器选择排队而非抢占                                                                            |
| 机制分析仍有效        | `_preempt_request()` 确实设 `num_computed_tokens=0`，`offload_prompt_only=True` 确实不 offload decode |
| 新发现            | vLLM 比预期更保守：宁可让请求等待也不抢占。但这意味着一旦触发 preempt（如更极端的内存压力），代价更大                                      |


**证据等级**：[MECHANISM+]——机制分析确认，加上排队策略的新发现。Preemption 仍可能在其他场景触发（如超长 context 请求耗尽内存），但在当前实验条件下极难复现。

---

## 3. P6: Cache 层级不统一的实测验证

### 3.1 背景

vLLM 的 GPU prefix cache（`cached_block_hash_to_block`）和 CPU offload tier（`CPUOffloadingManager._policy`）有**独立的 hash table**，且都使用 LRU 驱逐策略。`find_longest_cache_hit()` 只查 GPU hash table，但 KV connector 的 `get_num_new_matched_tokens()` → `_lookup()` 会**独立检查 CPU offload tier**。理论上，即使 GPU 层 miss，如果 CPU 层仍有数据，应该能 load 回来。

### 3.2 实验 P6-A：Offload ON vs OFF 对比

**方法**：两次独立部署 vLLM server，使用相同的请求序列，对比 cached_tokens。

**配置 A：Offload ON**

```bash
--kv-offloading-size 8 --kv-offloading-backend native
```

**配置 B：Offload OFF**

无 offload 相关参数。

**两种配置使用相同的请求序列**：

```
Phase 1: 串行发送 5 个 django session turns（建立 L0+L1 缓存）
Phase 2: 并发发送 9 个 UUID 前缀请求（触发驱逐）
Phase 3: 发送新 django turn 0（测试 L0 恢复）
```

**结果**：


| 指标                        | Offload ON (8 GiB) | Offload OFF | 对比             |
| ------------------------- | ------------------ | ----------- | -------------- |
| Phase 3 **cached_tokens** | **0**              | **0**       | **完全相同**       |
| Phase 3 TTFT              | 314.2 ms           | 309.0 ms    | 几乎相同           |
| GPU→CPU store bytes       | **14.96 GiB**      | 0           | ON 时确实在存储      |
| CPU→GPU load bytes        | **0 bytes**        | 0           | ❌ **ON 时也未加载** |
| 被驱逐 blocks 数              | 5,829+             | 5,829+      | 类似             |


### 3.3 核心发现

**Offload tier 的完整生命周期**：

```
1. Phase 1: L0 blocks 在 GPU + CPU 两层同时注册
   → GPU: cached_block_hash_to_block 中有 L0 hash ✅
   → CPU: _policy (LRU OrderedDict) 中有 L0 hash ✅
   → CPU 占用: ~11,616 tokens / 58,254 容量

2. Phase 2: 压力请求到来
   → GPU: get_new_blocks() → _maybe_evict_cached_block() → L0 hash 从 GPU 移除 ❌
   → CPU: 压力请求的 prompt blocks 也在被 store 到 CPU（增量式，每 step 都 store）
   → CPU 占用增长:
     req 1-4: ~51,616 tokens → 接近容量
     req 5+:  ~61,616+ tokens → 超过 58,254 容量！
   → CPU LRU eviction: 最老的 entries（Phase 1 的 L0+L1）被驱逐 ❌
   → CPU 的 _policy 中 L0 hash 也被移除

3. Phase 3: 新请求到来
   → GPU lookup (find_longest_cache_hit): cached_block_hash_to_block 无 L0 → miss ❌
   → CPU lookup (_lookup → manager.lookup): _policy 中 L0 已被 LRU 驱逐 → miss ❌
   → 两层都 miss → load=0, cached_tokens=0
```

**为什么 load=0**：不是"lookup 不检查 CPU"（实际上 `_lookup()` 会检查），而是**两层都在压力下独立驱逐了 L0**。GPU 层的 `_maybe_evict_cached_block()` 移除了 GPU hash 中的 L0，CPU 层的 LRU policy 为了给新请求腾空间也驱逐了 L0。两层使用独立的 LRU 策略，互不协调，导致同一个热点 prefix 在两层中同时丢失。

**数据验证**：

| 指标 | 值 | 含义 |
|------|-----|------|
| CPU 容量 | 58,254 tokens (8 GiB) | 只能存约 5.8 个请求的 prompt |
| Phase 1 store | 11,616 tokens (1.60 GiB) | L0+L1 存入 CPU |
| 累计 store 总量 | 111,520 tokens (15.31 GiB) | 远超 CPU 容量 |
| CPU 必须驱逐 | ~53,266 tokens | LRU 下最老的（L0+L1）首先被驱逐 |

### 3.4 结论

✅ **P6 证实——双层独立 LRU 驱逐**：

| 判断标准 | 预期 | 实际 |
|---------|------|------|
| `cached_tokens_ON == cached_tokens_OFF` | → 证实 P6 | ✅ 0 == 0 |
| `store_bytes > 0`（ON 时有 store 操作） | → offload 在工作 | ✅ 14.96 GiB |
| `load_bytes == 0`（ON 时无 load 操作） | → offload 无法恢复 L0 | ✅ 0 bytes |

**论文关键数字**：
- Offload store 14.96 GiB 数据到 CPU，但 **0 bytes** 被加载回来
- CPU 容量 58,254 tokens，累计 store 111,520 tokens → CPU LRU 驱逐 ~53,266 tokens
- L0 在 GPU 和 CPU 两层都被 LRU 驱逐，导致两层 lookup 都 miss

**P6 的正确表述**：vLLM 的 GPU prefix cache 和 CPU offload tier 虽然有独立的 hash table 且 lookup 路径会依次检查两层，但**两层都使用 LRU 驱逐策略且互不协调**。当压力足够大时，L0 在两层中都会被驱逐——GPU 层因为 `_maybe_evict_cached_block()` 从 free queue 弹出，CPU 层因为 LRU policy 给新请求腾空间。结果是两层都 miss，CPU offload 形同虚设。

**对比 SGLang HiRadixCache**：同一个 TreeNode 同时持有 `value`（GPU）和 `host_value`（CPU），`load_back` 从 CPU 恢复是 radix tree 遍历的一部分。CPU 层的 eviction 不会移除 TreeNode 本身（只清除 `host_value`），而 GPU 层的 eviction 也不会移除 TreeNode（只清除 `value`）。因此即使 GPU 层 miss，radix tree 仍能发现 evicted 节点并触发 `load_back`。

---

## 4. 证据等级更新


| 痛点                          | 原等级         | 新等级              | 关键数据                                                 |
| --------------------------- | ----------- | ---------------- | ---------------------------------------------------- |
| **P2: LRU 驱逐 L0**           | [SIMULATED] | **[MEASURED]**   | 5,829 blocks 被驱逐；5 个压力请求是临界点；touch 无法保护              |
| **P3: Preemption 丢 decode** | [MECHANISM] | **[MECHANISM+]** | Preemption 未触发（排队策略），但机制确认 + 排队发现                    |
| **P6: Cache 层级不统一**         | [PENDING]   | **[MEASURED]**   | Offload ON: store=14.96GiB, load=0；cached_tokens 无差异 |


---

## 5. 数据文件索引


| 文件                                               | 实验                | 关键结论                             |
| ------------------------------------------------ | ----------------- | -------------------------------- |
| `exp_p2a_l0_eviction/run_1_mt500.json`           | P2-A 串行（v1）       | ❌ 无驱逐，串行模式无效                     |
| `exp_p2a_l0_eviction/run_2_c5_mt2000.json`       | P2-A 5并发共享prefix  | ❌ 无驱逐，prefix cache 共享了 L0        |
| `exp_p2a_l0_eviction/run_3_c9_mt2000.json`       | P2-A 9并发共享prefix  | ❌ 无驱逐，同上                         |
| `exp_p2a_l0_eviction/run_4_u9_mt2000.json`       | P2-A 9并发不共享prefix | ✅ **L0 被驱逐**（但不同seed文本开头相同）      |
| `exp_p2a_l0_eviction/run_5_u9_mt2000.json`       | P2-A 9并发UUID前缀    | ✅ **L0 被驱逐**（5,829 blocks）       |
| `exp_p2b_lru_vs_aware/run_3_pressure_sweep.json` | P2-B 压力扫描        | 临界点=4→5 请求                       |
| `exp_p2b_lru_vs_aware/run_4_touch_vs_lru.json`   | P2-B touch对比      | Touch 无法保护 L0                    |
| `exp_p3a_trigger_preempt/run_1_c9_mt4000.json`   | P3-A 9并发长输出       | ❌ 未触发，5 running + 4 waiting      |
| `exp_p3a_trigger_preempt/p3a_analysis.json`      | P3-A 分析结论         | 排队策略 + 机制分析                      |
| `exp_p6a_offload_ab/run_2_on_correct.json`       | P6-A Offload ON   | store=14.96GiB, load=0, cached=0 |
| `exp_p6a_offload_ab/run_3_off.json`              | P6-A Offload OFF  | cached=0（与 ON 相同）                |


