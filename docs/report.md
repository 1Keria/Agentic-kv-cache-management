# vLLM KV Cache 管理调研汇报

> 日期: 2026-06-26 | 模型: Qwen3-8B | GPU: NVIDIA H800 | vLLM: 0.8.5.dev0
> 数据源: LMCache Agentic traces — 24,880 条请求，767 个 SWE-bench agent session

---

## 导读

本文档汇总 AgentKV 项目对 vLLM KV Cache 管理的系统性调研，按**「问题 → 负载特征 → 机制 → 逐实验验证 → 总结」**组织：


| 章节         | 内容                    | 证据类型                 |
| ---------- | --------------------- | -------------------- |
| **§1**     | 并发导致 prefix 不命中（核心问题） | MEASURED             |
| **§2**     | Agent Trace 特征画像      | TRACE                |
| **§3**     | vLLM KV 管理机制          | 源码分析                 |
| **§4**     | 串行场景 APC 验证           | MEASURED             |
| **§5**     | 容量与驱逐策略模拟             | SIMULATED            |
| **§6–§11** | P2–P7 逐痛点实测/分析        | MEASURED / MECHANISM |
| **§12**    | 优先级与 AgentKV 方向       | —                    |
| **附录 C**  | 并发优化价值量化（L1 部分复用）   | MEASURED / 推断        |


**实验环境**（所有 vLLM 实测共用）：gpu_util=0.3，KV 容量 **53,072 tokens**（3,317 blocks × 16），APC ON (xxhash)，chunked prefill ON，watermark 0.02。

---

## §1 并发导致 KV Cache 不命中

> 优先级：**CRITICAL (P1)** | 脚本: `investigate_phase3_pain_points.py`, `investigate_phase2b_concurrent.py`

### 1.1 问题现象

当多个 Agent 请求并发到达时，它们本应共享的 prefix（L0 system prompt、同项目 L1）无法被充分命中，导致重复 prefill，TTFT 显著升高。

**实验 A — P1 控制实验**（3 个不同 django session，turn 0）：

- Session: `10097` / `10554` / `10914`，L1 规模 **3,790 / 2,754 / 4,737 tokens**
- 流程：**先并发发送，再串行重发**（server 已有 L0 预热）
- 数据: `investigation/data/phase3_pain_points.json`


| 模式  | S1 cached / prompt | S2 cached / prompt | S3 cached / prompt  |
| --- | ------------------ | ------------------ | ------------------- |
| 并发  | 10,064 / 10,073    | **7,824** / 9,065  | **7,824** / 11,061  |
| 串行  | 10,064 / 10,073    | **9,056** / 9,065  | **11,056** / 11,061 |



| 汇总指标          | 值                |
| ------------- | ---------------- |
| 并发 avg cached | 8,570.7          |
| 串行 avg cached | 10,058.7         |
| **Cache gap** | **1,488 tokens** |
| 并发 avg TTFT   | 215.6 ms         |
| 串行 avg TTFT   | 41.9 ms          |


**实验 B — Phase 2B 大规模并发**（9 请求，turn 3）：

- Warmup 1 个 django session 5 轮后，同时发送 5 django + 4 sympy（各 turn 3 长 prompt）
- 数据: `investigation/data/phase2b_concurrent_pressure.json`


| 请求      | prompt       | cached      | 命中内容             |
| ------- | ------------ | ----------- | ---------------- |
| DJ1-T3  | 11,485       | 11,472      | L0+L1（warmup 遗留） |
| DJ2–DJ5 | 9,609–12,486 | **7,824**   | 仅 L0             |
| SY1–SY4 | 9,815–14,080 | 7,808–7,824 | 仅 L0             |


→ 9 个请求中 **8 个只命中 L0**；总体命中率 **70.6%**（74,048 / 104,946），远低于串行 ~99%。


| 对比              | L1 跨请求命中 | 每 3 请求浪费  | TTFT          |
| --------------- | -------- | --------- | ------------- |
| 串行              | ~100%    | 0         | ~44 ms        |
| 并发 (vLLM)       | **≈0%**  | **1,488** | ~215 ms (avg) |
| 并发 (SGLang，同设计) | **~15%** | ~1,552    | —             |


### 1.2 根因：两个独立因素

**因素 A — Prefix 内容发散（链式 hash）**

vLLM 的 block hash 是链式的：`hash(parent_hash, block_token_ids)`。L0 相同则前若干 block 相同；**L1/L2 任一处不同，后续 hash 全部不同**。P1 三个 session 的 L1 长度不同；Phase 2B turn 3 时各 session L2（对话历史）已不同 → 跨 session 并发最长公共 prefix 收敛到 **L0（block 对齐值 7,824 = 489×16）**。

**因素 B — 同调度步内注册时序**

Block 在 `allocate_slots()` 期间注册（非请求结束后），但同一调度步内，后处理请求的 `find_longest_cache_hit()` 可能在先请求完成 `cache_blocks()` **之前**执行 → **同内容 prefix 在同批内不可见**。

```
schedule() 处理一批 waiting 请求:

  对每个请求依次:
    ① get_computed_blocks() → find_longest_cache_hit()   ← 只读
    ② allocate_slots() → cache_blocks()                  ← 注册

  → 因素 B: B 的 ① 可能在 A 的 ② 之前 → 同内容也无法同批共享
  → 因素 A: 不同内容即使可见也无法 hash 匹配
```

**实验解读注意**：P1 串行阶段 S2/S3 近满命中，主要因为并发轮已各自算完并注册（**自缓存**），不是干净的跨请求对照。1,488 gap 混合了因素 A + 实验 confound。

### 1.3 AgentKV 方向

**Eager Prefix Registration**：对已知共享的 L0 / 项目级 L1，在调度前预注册 block hash，使同批并发请求可共享正在计算的 prefix。

---

## §2 Agent Trace 特征画像

> Phase 1A | 脚本: `investigate_trace_tokenizer.py` | 证据: **[TRACE]**

### 2.1 数据概况


| 指标                | 值                                         |
| ----------------- | ----------------------------------------- |
| 总请求数              | 24,880                                    |
| 总 session 数       | 767                                       |
| SWE-bench session | 665（minimax=490, claude=110, deepseek=65） |
| GAIA / WildClaw   | 94 / 8                                    |


方法：5 个 Arrow 文件，`tiktoken cl100k_base` 分词，逐消息标注 L0/L1/L2 层级。

### 2.2 L0/L1/L2 层次分解

（SWE-bench minimax, 490 sessions）


| 层级                      | Token 数   | 占首轮比例     | 共享范围        |
| ----------------------- | --------- | --------- | ----------- |
| L0 (system prompt)      | 6,156     | 46.3%     | 所有 session  |
| L1 (examples + runtime) | 3,394     | 25.5%     | 同项目 session |
| L2 (task + history)     | 3,736     | 28.1%     | session 特有  |
| **L0+L1**               | **9,550** | **71.9%** | —           |


→ Agent 首轮 **71.9%** 的 token 具有跨 session 复用潜力；C++ 模拟显示复用天花板 **97.1%**（§5）。

### 2.3 逐轮输入增长


| Turn | p50 (tokens) | p75 (tokens) | 仍在跑的 session |
| ---- | ------------ | ------------ | ------------ |
| 0    | 8,810        | 10,341       | 767          |
| 5    | 13,462       | 17,055       | 752          |
| 10   | 17,627       | 20,462       | 682          |
| 20   | 23,032       | 26,405       | 539          |
| 30   | 28,884       | 32,423       | 412          |
| 49   | 39,436       | 44,425       | 228          |


→ Turn 0 中位数 8,810 tokens，Turn 30 增长到 28,884（**3.3×**）。对话越长，每轮 prefill 越大。

### 2.4 Session 生命周期 KV 占用


| 指标                     | 值               |
| ---------------------- | --------------- |
| Max KV p50             | 32,211 tokens   |
| Max KV p75             | 39,437 tokens   |
| 增长比 p50 / mean         | 3.64× / 9.12×   |
| 超出 44K GPU 容量的 session | **104 (13.6%)** |
| 超出 80K 容量的 session     | 0.4%            |


→ **13.6%** 的 session 单独就超出 H800 (gpu_util=0.3) 的 KV 容量；多 session 并发时比例更高。

### 2.5 跨 session prefix 重叠（按项目）


| 项目         | L1 tokens | L0+L1 合计 |
| ---------- | --------- | -------- |
| astropy    | 4,087     | 10,244   |
| matplotlib | 4,035     | 10,194   |
| django     | 2,726     | 8,883    |
| sympy      | 2,944     | 9,101    |


### 2.6 到达模式


| 指标                  | 值       | 含义               |
| ------------------- | ------- | ---------------- |
| Inter-turn gap p50  | 0.708 s | 半数 turn 间隔 < 1 秒 |
| Inter-turn gap mean | 2.084 s | 多 session 可能重叠运行 |


→ Agent 负载天然**多 session 并发**，与 §1 的问题场景一致。

---

## §3 vLLM KV 管理机制

> 源码分析 | 详见 `docs/19_investigation_plan.md`

### 3.1 生命周期

```
请求到达 → 预计算 block_hashes（链式 hash）
  ↓
① Prefix 查找   find_longest_cache_hit() — 查 cached_block_hash_to_block，首 miss 即停
  ↓
② Block 分配    get_new_blocks() — 从 free_block_queue 头部取，可能 _maybe_evict_cached_block()
  ↓
③ Cache 注册    cache_blocks() — 在 allocate_slots() 期间，非请求结束后
  ↓
④ Prefill/Decode → 完成 → ref_cnt=0 → 回 free queue（hash 映射仍保留）
  ↓
⑤ 驱逐          free queue 头部 cached block 被重分配 → hash 映射永久丢失
```

### 3.2 关键机制点


| 机制                  | 行为                                           | Agent 影响                  |
| ------------------- | -------------------------------------------- | ------------------------- |
| 链式 hash             | parent_hash 传递，prefix 中途发散则后续全 miss          | 跨 session 只能共享到 L0/L1 公共段 |
| ref_cnt             | >0 不被驱逐；全部请求完成后 L0 ref_cnt→0                 | L0 可能成为 LRU 驱逐候选          |
| free queue          | 头部=最久未用；cached block 释放到尾部                   | LRU 可能驱逐高价值 L0            |
| kv_cache_usage_perc | 只统计 ref_cnt>0                                | 串行时 usage≈0 但 cache 仍有效   |
| offload             | GPU/CPU 独立 hash table；默认 offload_prompt_only | decode blocks 不被 offload  |
| preemption          | num_computed_tokens=0，全部 blocks 释放           | decode 输出需完全重算            |


---

## §4 串行场景：APC 已经很好

> Phase 1B | 脚本: `investigate_vllm_verify.py` | 证据: **[MEASURED]**

Session: `swebench__django__django-10097__minimax`（L0=6,156, L1=3,394）


| 请求               | TTFT     | prompt | cached | 命中率            |
| ---------------- | -------- | ------ | ------ | -------------- |
| Turn 0 冷启动       | 1,632 ms | 10,078 | 0      | 0%             |
| Turn 1 同 session | 85 ms    | 10,102 | 10,064 | **99.6%**      |
| Turn 2 同 session | 67 ms    | 10,130 | 10,096 | **99.7%**      |
| Turn 3 跨项目       | 61 ms    | 6,459  | 6,160  | **95.4%** (L0) |


**理论 vs 实测**（差异 ≤ 14 tokens，block 对齐）：


| 场景         | 理论可复用       | 实测 cached | 差异        |
| ---------- | ----------- | --------- | --------- |
| Turn 1     | ≈10,078     | 10,064    | 14 tokens |
| Turn 3 跨项目 | ≈6,156 (L0) | 6,160     | 4 tokens  |


**Phase 2B 串行回放**（3 django × 10 turns + 2 sympy × 8 turns）：

- 同 session 后续轮次命中率 **99.6%–99.9%**
- 跨 session（同项目）首轮 **86.3%–95.5%**（L0+L1）
- 跨 session（跨项目）首轮 **79.7%–95.1%**（L0 only）
- TTFT：冷启动 ~1,019 ms → 热启动 40–80 ms，**降低 92%–96%**

→ **vLLM APC 对串行 Agent 请求已高效**；痛点在 §1 并发与 §6–§10 内存压力，不在 APC 本身。

---

## §5 容量与驱逐策略模拟

> Phase 2A | 脚本: `investigate_run_simulations.py` | 证据: **[SIMULATED]**

C++ 模拟器，block_size=16，prefix-aware blake2b hash，2,048 请求（50% warmup），8 个容量点，FIFO / LRU / Optimal 三策略。


| 容量 (tokens) | FIFO  | LRU   | Optimal | LRU-Opt Gap |
| ----------- | ----- | ----- | ------- | ----------- |
| 16,000      | 12.8% | 12.8% | 60.9%   | 48.1%       |
| 32,000      | 64.8% | 59.5% | 90.7%   | **31.2%**   |
| **44,000**  | 91.4% | 89.5% | 96.4%   | **6.9%**    |
| 80,000+     | 96.8% | 97.1% | 97.1%   | 0.0%        |


**关键发现**：

1. Agent trace 复用天花板 = **97.1%**（与 §2 的 71.9% L0+L1 比例一致量级）
2. H800 实际容量 (44K) 下 LRU-Opt gap = **6.9%** → LRU 可能驱逐高价值 L0/L1
3. 32K 时 LRU (59.5%) **低于** FIFO (64.8%) → 「最近使用」在 Agent 场景不是好的驱逐信号

数据: `investigation/data/simulation_results.json`

---

## §6 内存压力：LRU 驱逐 L0

> P2 | 优先级: **HIGH** | 脚本: `run_p2a_l0_eviction.py`, `run_p2b_lru_vs_aware.py` | 证据: **[MEASURED]**

### 6.1 为什么早期实验未触发驱逐


| 策略            | 失败原因                             |
| ------------- | -------------------------------- |
| 串行多 session   | 请求完成后 blocks 释放，free pool 充足     |
| 并发共享 prefix   | prefix cache 共享 L0，实际 KV 占用远低于总量 |
| max_tokens 过小 | decode KV 瞬间释放                   |


### 6.2 实验 P2-A：强制 L0 驱逐

```
Phase 1: 串行 1 个 django turn 0 → 建立 L0+L1 基线
Phase 2: 并发 9 个 UUID 前缀请求 (max_tokens=2000)，~99K KV >> 53K 容量
Phase 3: 新 django turn 0 → 探测 L0 是否存活
```


| Phase      | 指标              | 值                 |
| ---------- | --------------- | ----------------- |
| Phase 1    | baseline cached | **10,064**（L0+L1） |
| Phase 2    | 估算总 KV          | ~99,926 tokens    |
| Phase 3    | test cached     | **0**（L0 完全驱逐）    |
| Prometheus | blocks 被驱逐      | **5,829**         |


### 6.3 实验 P2-B：压力临界点


| 压力请求数 | 估算 KV | cached | L0 状态             |
| ----- | ----- | ------ | ----------------- |
| 3     | ~33K  | 10,064 | ✅ 完整              |
| 4     | ~44K  | 9,664  | ⚠️ L1 部分丢失 (-400) |
| 5     | ~55K  | **0**  | ❌ 完全驱逐            |
| 6     | ~66K  | **0**  | ❌ 完全驱逐            |


Touch 请求无法保护 L0（cached 仍为 0）。

→ 与 §5 模拟一致：LRU 在 Agent 负载下会驱逐 **6,157 tokens** 的高价值 L0。

**AgentKV 方向**：Agent-Aware Eviction — L0/L1 blocks 标记 protected。

---

## §7 Preemption 与 Decode 输出丢失

> P3 | 优先级: **HIGH** | 脚本: `run_p3a_trigger_preempt.py` | 证据: **[MECHANISM+]**

### 7.1 机制（源码确认）

```
allocate_slots() 返回 None → preempt 最低优先级 running 请求
  → num_computed_tokens = 0
  → 全部 blocks 释放
  → offload_prompt_only=True → decode blocks 不 offload → 永久丢失
  → 重调度时 prefix cache 可恢复 prompt，decode 必须完全重算
```

**理论代价**：10 turns 累计 decode 输出 **5,000–15,000 tokens**；重算 TTFT ≈ 冷启动 (1000 ms+)。

### 7.2 实测：Preemption 极难触发


| 尝试                          | 观察                                    | num_preemptions |
| --------------------------- | ------------------------------------- | --------------- |
| 9 并发 UUID (max_tokens=4000) | 5 running + 4 waiting, KV usage 95.5% | **0**           |
| PRIORITY 调度 + 高优先级插入        | 高优先级进 waiting queue                   | **0**           |


**原因**：Preemption 只在 running 请求 `allocate_slots()` 失败时触发。Decode 每 step 只需 1 block，watermark 保留 ~66 blocks → running 请求几乎总能分配到 blocks。新请求分配失败时 scheduler **选择排队而非抢占**。

→ 机制风险真实，但当前实验条件难复现。vLLM 比预期更保守：宁可等待也不抢占；一旦触发 preempt，代价更大。

**AgentKV 方向**：Offload decode blocks / Partial preemption。

---

## §8 Prefix 增长与内存压力

> P4 | 优先级: **MEDIUM** | 证据: **[TRACE]** + **[MEASURED]**

### 8.1 Trace 量化（Phase 1A）

见 §2.3、§2.4。关键数字：

- 增长比中位数 **3.64×**，13.6% session 单独超 44K
- 3 session 并发到 turn 9：同时占用 ≈ 3 × 20K = **60K > 44K** → 将触发驱逐

### 8.2 vLLM 实测（Phase 3 P4）

串行交错回放 3 django session 各 10 turns：

- Turn 0 ~10K tokens → Turn 9 ~19K tokens（**1.9×**）
- 3 session 交错：总 prompt_tokens 从 30K 增长到 63K

**AgentKV 方向**：KV 增长预测 / 动态 Offloading / Session Grouping。

---

## §9 Block 对齐浪费

> P5 | 优先级: **LOW（非痛点）** | 证据: **[MEASURED]**


| 指标                   | 值                 |
| -------------------- | ----------------- |
| Block size           | 16 tokens         |
| 理论最大浪费/turn          | 15 tokens         |
| 实测浪费/turn            | 0–14 tokens，中位数 7 |
| 15 轮串行实测 total waste | **0 tokens**      |
| 占 prompt 比例          | **< 0.07%**       |


→ block_size=16 对 6K–25K token 的 Agent prompt 已足够精细，**不需要修复**。

---

## §10 GPU/CPU 双层 Cache

> P6 | 优先级: **MEDIUM** | 脚本: `exp_p6a_offload_ab/` | 证据: **[MEASURED]**

### 10.1 机制

GPU prefix cache（`cached_block_hash_to_block`）与 CPU offload tier（`CPUOffloadingManager._policy`）有**独立 hash table**，均使用 LRU 驱逐。

### 10.2 Offload ON vs OFF 对比（相同请求序列）

```
Phase 1: 串行 5 django turns → 建立 L0+L1
Phase 2: 并发 9 UUID 前缀 → 触发驱逐
Phase 3: 新 django turn 0 → 探测恢复
```


| 指标                    | Offload ON (8 GiB) | Offload OFF |
| --------------------- | ------------------ | ----------- |
| Phase 3 cached_tokens | **0**              | **0**       |
| Phase 3 TTFT          | 314.2 ms           | 309.0 ms    |
| GPU→CPU store         | **14.96 GiB**      | 0           |
| CPU→GPU load          | **0 bytes**        | 0           |
| 被驱逐 blocks            | 5,829+             | 5,829+      |


**生命周期**：

1. Phase 1：L0 在 GPU + CPU 两层同时注册
2. Phase 2：GPU `_maybe_evict_cached_block()` 移除 L0；CPU 累计 store 111,520 tokens >> 容量 58,254 → CPU LRU 也驱逐 L0
3. Phase 3：两层 lookup 均 miss → load=0

→ CPU offload **存了 14.96 GiB 但 0 bytes 被加载回来**；双层独立 LRU 互不协调。

**AgentKV 方向**：Unified Cache Hierarchy（类似 SGLang HiRadixCache）。

---

## §11 调度感知：FCFS 的额外损失

> P7 | 优先级: **MEDIUM** | 证据: **[MEASURED]**

3 django + 2 sympy 首轮请求：


| 模式          | 总 cached_tokens  | 说明               |
| ----------- | ---------------- | ---------------- |
| 并发 (FCFS)   | 45,808           | 混合项目，L1 未充分预热    |
| 最优串行（同项目分组） | 48,192           | 同项目连续 → L1 最大化共享 |
| **Gap**     | **2,384 tokens** | ≈ 1 个 Sympy L1   |


→ FCFS 不考虑 prefix 共享，混合项目负载下有额外 **2,384 tokens/批次** 的 prefill 浪费。

**AgentKV 方向**：Prefix-Aware Scheduling（LPM-style，按项目分组）。

---

## §12 总结：痛点优先级与 AgentKV 方向

### 12.1 三段式论证


| #   | 论点                | 关键数据                                                |
| --- | ----------------- | --------------------------------------------------- |
| 1   | Agent 有极高 KV 复用潜力 | L0+L1 占 71.9%；串行命中率 97–99%；模拟天花板 97.1%              |
| 2   | 并发时 prefix 共享失效   | P1 gap 1,488 tok；Phase 2B 8/9 仅 L0；成因=内容发散+注册时序     |
| 3   | 压力与驱逐策略有结构性缺陷     | L0 被驱逐 5,829 blocks；LRU-Opt gap 6.9%；offload load=0 |


### 12.2 痛点优先级


| 优先级          | 痛点                     | 影响量化                    | 证据         | 方向                        |
| ------------ | ---------------------- | ----------------------- | ---------- | ------------------------- |
| **CRITICAL** | P1 并发共享失效              | 1,488 tok/3req          | MEASURED   | Eager prefix registration |
| **HIGH**     | P2 LRU 驱逐 L0           | 6,157 tok; 5,829 blocks | MEASURED   | Agent-aware eviction      |
| **HIGH**     | P3 Preemption 丢 decode | 5K–15K tok 重算           | MECHANISM+ | Offload decode            |
| MEDIUM       | P4 Prefix 增长           | 3.64×; 13.6% 超容量        | TRACE      | 增长预测 + offload            |
| MEDIUM       | P7 无调度感知               | 2,384 tok/5req          | MEASURED   | Prefix-aware scheduling   |
| MEDIUM       | P6 双层 Cache            | store 14.96GiB, load 0  | MEASURED   | Unified hierarchy         |
| LOW          | P5 Block 浪费            | <0.07%                  | MEASURED   | 不需要修复                     |


### 12.3 三个贡献方向

1. **Eager Prefix Registration**（P1）— 项目级 L0/L1 预注册
2. **Agent-Aware Eviction**（P2+P3）— 保护 L0/L1；offload decode
3. **Prefix-Aware Scheduling**（P7）— 同项目分组调度

---

## §13 关键数字速查


| #   | 指标                   | 值               | 来源        |
| --- | -------------------- | --------------- | --------- |
| 1   | Trace 总请求 / session  | 24,880 / 767    | TRACE     |
| 2   | L0 tokens            | 6,157           | TRACE     |
| 3   | L0+L1 占首轮            | 71.9%           | TRACE     |
| 4   | 串行 APC 命中率           | 97.6%–99.9%     | MEASURED  |
| 5   | 并发 L1 跨请求命中          | ≈0%             | MEASURED  |
| 6   | 并发 vs 串行 gap         | 1,488 tok/3req  | MEASURED  |
| 7   | Phase 2B 9并发仅 L0     | 8/9 请求          | MEASURED  |
| 8   | LRU-Opt gap @44K     | 6.9%            | SIMULATED |
| 9   | L0 被驱逐 blocks        | 5,829           | MEASURED  |
| 10  | 驱逐临界点                | 5 并发独立请求        | MEASURED  |
| 11  | Offload store / load | 14.96 GiB / 0 B | MEASURED  |
| 12  | Session 超 44K        | 13.6%           | TRACE     |
| 13  | 调度 gap               | 2,384 tok/5req  | MEASURED  |
| 14  | Block 浪费             | <0.07%          | MEASURED  |


---

## 附录 A：SGLang 简要对比

> 详见 `docs/24_sglang_experiment_report.md`

SGLang 调度三阶段分离（全部 match → forward → 全部 insert），同批查找在注册前完成；`in-batch prefix caching`（阈值 32 tokens）对 Agent 长 L1 仅部分缓解。


| 实验                 | vLLM                  | SGLang          |
| ------------------ | --------------------- | --------------- |
| 串行 3 django turn 0 | ~10,064 cached        | 10,072 cached   |
| 并发 3 django turn 0 | avg **8,571**         | avg **8,520**   |
| 并发 L1 额外收益         | ≈0                    | ~15% 部分命中       |
| L0 驱逐 (9 UUID 并发)  | cached=0, 5829 blocks | cached=0        |
| P6 双层 Cache        | 独立 LRU，load=0         | HiRadixCache 统一 |


---

## 附录 B：实验材料索引

### 报告文档


| 文档          | 路径                                                  |
| ----------- | --------------------------------------------------- |
| 实验全记录       | `experiments/vllm_kv_cache/investigation/README.md` |
| 执行摘要        | `investigation/report/00_executive_summary.md`      |
| Trace 画像    | `investigation/report/02_trace_characterization.md` |
| 模拟结果        | `investigation/report/03_simulation_results.md`     |
| 并发实测        | `investigation/report/04_vllm_eviction_analysis.md` |
| 痛点分析        | `investigation/report/05_pain_point_analysis.md`    |
| 优先级矩阵       | `investigation/report/06_prioritization_matrix.md`  |
| P2/P3/P6 补强 | `docs/23_vllm_experiment_report.md`                 |
| SGLang 实验   | `docs/24_sglang_experiment_report.md`               |
| vLLM 机制     | `docs/19_investigation_plan.md`                     |


### 实验脚本


| 阶段       | 脚本                                                                  |
| -------- | ------------------------------------------------------------------- |
| Phase 1A | `scripts/investigate_trace_tokenizer.py`                            |
| Phase 1B | `scripts/investigate_vllm_verify.py`                                |
| Phase 2A | `scripts/investigate_run_simulations.py`                            |
| Phase 2B | `scripts/investigate_phase2b_concurrent.py`                         |
| Phase 3  | `scripts/investigate_phase3_pain_points.py`                         |
| P2 补强    | `scripts/run_p2a_l0_eviction.py`, `scripts/run_p2b_lru_vs_aware.py` |
| P3 补强    | `scripts/run_p3a_trigger_preempt.py`                                |


### 原始数据


| 数据             | 路径                                                      |
| -------------- | ------------------------------------------------------- |
| Per-request 指标 | `investigation/data/per_row_metrics.json`               |
| Trace 汇总       | `investigation/data/tokenized_traces_summary.json`      |
| Phase 1B       | `investigation/data/phase1b_single_session_replay.json` |
| 模拟结果           | `investigation/data/simulation_results.json`            |
| Phase 2B 并发    | `investigation/data/phase2b_concurrent_pressure.json`   |
| Phase 3 痛点     | `investigation/data/phase3_pain_points.json`            |
| P2/P6 JSON     | `experiments/vllm_kv_cache/exp_p2a_*/`, `exp_p6a_*/`    |
| SGLang         | `experiments/sglang_kv_cache/exp_s*/`                   |


---

## 附录 C：并发优化价值量化（L1 部分复用）

> 问题：L1 无法 100% 跨 session 复用，但仍有公共段值得复用；串行实验已证明 APC 有效，AgentKV 实现后提升空间多大？

### C.1 串行实验已证明的可复用部分

| 场景 | 命中率 | 复用内容 | 证据 |
| ---- | ------ | -------- | ---- |
| 同 session 多轮 | **99.6%–99.9%** | L0+L1+历史 | Phase 1B |
| **跨 session、同项目、Turn 0** | **86.3%–95.5%** | **L0 + 大部分 L1** | Phase 2B 串行回放 |
| 跨项目 Turn 0 | 79.7%–95.1% | 主要是 L0 | Phase 2B |
| 模拟天花板 | **97.1%** | 几乎全部可复用 prefix | Phase 2A |

Trace：首轮 **71.9%** token 属于 L0+L1，具有跨 session 复用潜力。痛点不在 APC 能力，而在**并发时 prefix 不可见**。

### C.2 L1 结构：哪一段值得复用

```
[L0 system] → [L1 公共: Flask 示例等] → [L1 特有: 任务/端口] → [L2 历史]
  ✅ 全 session 相同      ✅ 同项目大多相同         ❌ session 不同      ❌ turn 越深越分叉
```

链式 hash 在首个不同 block 处断裂。并发时 8/9 请求仅命中 **7,824 tokens（489×16）** = 跨 session 仍 block 对齐的 **L0 公共段**；串行可额外命中 **L1 公共段**。

P1（3 django Turn 0）量化：


| 请求 | prompt | 并发 cached | 串行 cached | 少复用部分 |
| ---- | ------ | ----------- | ----------- | ---------- |
| DJ-2 | 9,065 | 7,824 | 9,056 | **~1,232 tok** |
| DJ-3 | 11,061 | 7,824 | 11,056 | **~3,232 tok** |
| 批次平均 | — | 8,571 | 10,059 | **gap ≈ 1,488 tok/req** |


### C.3 实现 AgentKV 的价值与 TTFT

| 指标 | 并发 | 串行（可见性恢复） | 差距 |
| ---- | ---- | ------------------ | ---- |
| avg cached | 8,571 | 10,059 | **+1,488 tok/req** |
| avg TTFT | **215 ms** | **42 ms** | **约 5×** |

Turn 0、多 session 同项目并发冷启动场景下，少 prefill ~1,500 tokens 可显著降低 TTFT。

### C.4 提升空间：上限 / 现实 / 下限


| 层级 | 场景 | 空间 | 说明 |
| ---- | ---- | ---- | ---- |
| **上限** | Turn 0、同项目、串行式可见性 | +1,200–3,200 tok/req | 接近 86%–99% 命中率 |
| **现实** | 仅 in-batch / 注册时序（SGLang 参考） | ~700 tok/req（~15% L1） | 因素 A（内容分叉）仍限制 |
| **现实** | + 调度分组（P7） | ~477 tok/req（2,384/5req） | 混合项目负载 |
| **现实** | Eager 预注册 L0/L1 模板 | 接近串行 86%–95% | AgentKV 主方向 |
| **下限** | Turn 3+、长历史并发 | 小 | 公共 prefix 收敛到 L0；Phase 2B 总体 70.6% vs 串行 ~99% |

SGLang 同实验（3 django Turn 0 并发）：avg cached **8,520** vs vLLM **8,571**；L1 跨请求额外命中 **~15%**（in-batch prefix caching），仍有 **~84% L1 在并发时丢失**——说明单靠时序修复有收益但有限。

### C.5 场景价值矩阵


| 场景 | 价值 | 预期提升 |
| ---- | ---- | -------- |
| Turn 0、多 session **同项目**并发 | **高** | +1.5K tok/req，TTFT ~5×，目标 86%–99% |
| 仅 in-batch / 时序修复 | 中 | ~700 tok/req（SGLang 参考） |
| + Prefix-Aware 调度（P7） | 中 | +~500 tok/req（混合 5 req 批次） |
| Turn 3+、长历史并发 | 低–中 | 优化 L1 边际小，转向 P2/P3 |

**结论**：Agent 负载 **71.9% prefix 值得复用**，串行已验证 vLLM APC 能吃到；并发丢失的主要是**同项目 L1 公共段**。AgentKV 在 **Turn 0 同项目并发**提升空间最大；Turn 加深后收益收窄，应结合 L0 驱逐保护（P2）与 decode 保护（P3）。


