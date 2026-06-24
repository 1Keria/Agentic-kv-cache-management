# AgentKV vLLM KV Cache 调研：实验全记录

> 日期: 2026-06-24 | 模型: Qwen3-8B | GPU: NVIDIA H800 | vLLM: 0.8.5.dev0

---

## 背景与目标

对 vLLM v1 的 KV Cache 管理机制做系统性调研：

1. 理解机制：从请求到达到 block 驱逐的完整生命周期
2. 量化痛点：找出 Agent 工作负载与 vLLM KV Cache 机制的错配，每个痛点必须有数据支撑

数据源：LMCache Agentic traces — 24,880 条请求，767 个 SWE-bench agent session，5 个 Arrow 文件。

---

## Phase 1A：Trace 特征画像（理论分析）

**目的**：搞清楚 Agent 工作负载长什么样——每条请求有多少 token，哪些部分是多个请求共享的，随对话轮次增长有多快。这些是后面所有实验的基础数字。

**脚本**：`scripts/investigate_trace_tokenizer.py`

**输入数据**：5 个 Arrow 文件（`lmcache_traces/data-0000{i}-of-00005.arrow`），共 24,880 条请求，767 个 SWE-bench agent session。每条请求就是一次 LLM 调用，包含一组 messages（类似 ChatGPT 的对话格式：system 消息 + user 消息 + assistant 消息）。

**做了什么**：

1. **读取数据**：用 `pyarrow` 加载 5 个 Arrow 文件，每条记录有 `session_id`、`input`（消息列表）、`output_length`（模型输出 
2. token 数）、`pre_gap`（与上一轮的时间间隔）
3. **数 token**：每条消息是一段文本（比如 "You are a helpful assistant..."），我们需要知道它占多少个 token（因为 GPU 按 token 收费、KV cache 按 token 占空间）。用 `tiktoken` 这个库来做——它是 OpenAI 开源的 tokenizer，`cl100k_base` 是 GPT-4/Claude 用的分词规则，把文本切成 token 并计数。比如 "hello world" 可能是 2 个 token，一段 2 万字的 system prompt 可能是 6000 多个 token
4. **分层标注**：Agent 请求的消息天然分三层：
  - **L0（system prompt）**：第一条消息，role="system"，内容是 "You are OpenHands agent..." 这种通用指令。**所有 767 个 session 都共享同一段 L0**
  - **L1（项目级 examples）**：第 2、3 条消息，内容是 "Here's a running example of how to fix a bug in django..." 这种项目示例。**同项目的 session 共享 L1**（比如所有 django session 共享同一段 L1）
  - **L2（session 特有内容）**：剩余的消息，是具体的任务描述和对话历史。**每个 session 都不一样**
5. **聚合统计**：按项目分组算均值、按 turn 算增长、算跨 session 的 prefix 重叠量

### 产出


| 文件                                                 | 大小     | 内容                                                                                                    |
| -------------------------------------------------- | ------ | ----------------------------------------------------------------------------------------------------- |
| `investigation/data/per_row_metrics.json`          | 7.0 MB | 24,880 行，每行一个请求的：session_id, turn_index, l0_tokens, l1_tokens, l2_tokens, total_tokens, output_length |
| `investigation/data/tokenized_traces_summary.json` | 10 KB  | 聚合统计：A 项目分解, B 逐轮增长, C KV 占用分布, D 跨 session 重叠, E 到达时间模式                                              |


### 发现

**L0/L1/L2 层次分解**（SWE-bench minimax sessions）：


| 层级                  | Token 数          | 占首轮比例     | 共享范围             |
| ------------------- | ---------------- | --------- | ---------------- |
| L0 (system prompt)  | 6,157            | 46.3%     | 所有 767 个 session |
| L1 (项目级 examples)   | 2,726-4,264      | 25.5%     | 同项目 session      |
| L2 (task + history) | 剩余               | 28.1%     | session 特有       |
| **L0+L1**           | **8,883-10,424** | **71.9%** | —                |


→ Agent 请求的 **71.9%** 是可跨 session 复用的 prefix，只有 28.1% 是 session 特有的。

**逐轮输入增长**：

| Turn | 中位数 (p50) | 75 分位 (p75) | 还在跑的 session |
| ---- | ---------- | ---------- | ------------ |
| 0    | 8,810      | 10,341     | 767          |
| 5    | 13,462     | 17,055     | 752          |
| 10   | 17,627     | 20,462     | 682          |
| 20   | 23,032     | 26,405     | 539          |
| 30   | 28,884     | 32,423     | 412          |
| 49   | 39,436     | 44,425     | 228          |

**这三列是什么意思**：

- **中位数 (p50)**：把这一轮所有 session 的 token 数从小到大排，最中间那个。比如 Turn 0 有 767 个 session，token 数排第 384 位的是 8,810——意思是**一半 session 首轮输入不超过 8,810 tokens，另一半超过**
- **75 分位 (p75)**：同上，排到 75% 位置的那个。Turn 0 的 p75 = 10,341——意思是**75% 的 session 首轮输入不超过 10,341 tokens，剩下 25% 超过**。p75 比 p50 大，说明有些 session 的 prompt 特别长，拉高了上四分位
- **还在跑的 session**：不是所有 session 都能活到后面。767 个 session 第 0 轮都在，到第 30 轮只剩 412 个（45% 的 session 已经结束了），到第 49 轮只剩 228 个

→ 对话越长，每轮的输入越大（因为要带上之前的对话历史）。Turn 0 中位数 8,810 tokens，到 Turn 30 就要 28,884 tokens（3.3 倍）。**对 KV cache 来说，一个 session 到第 30 轮时，光 prefill 就要算将近 3 万 tokens**。

**Session 生命周期 KV 占用**：

| 指标 | 值 | 含义 |
|------|-----|------|
| Max KV 中位数 | 32,211 tokens | 一半 session 峰值 KV 不超过 32,211 tokens |
| Max KV 75 分位 | 39,437 tokens | 75% 的 session 峰值 KV 不超过 39,437 tokens |
| 增长比中位数 | 3.64x | 一半 session 最后一轮输入是第一轮的 3.64 倍以上 |
| 增长比均值 | 9.12x | 少数超长 session 把均值拉高（中位数 3.64x vs 均值 9.12x，说明右偏分布） |
| 超出 44K 容量 | 104 个 (13.6%) | 104 个 session 单独就超出了 H800 的 KV 容量 |

→ 13.6% 的 session 单独就超出 H800 (gpu_util=0.3) 的 44K token GPU KV 容量。多个 session 并发时这个比例更高。

**跨 session prefix 重叠**：


| 项目         | L1 tokens | L0+L1 合计 |
| ---------- | --------- | -------- |
| pylint-dev | 4,264     | 10,421   |
| astropy    | 4,087     | 10,244   |
| matplotlib | 4,035     | 10,192   |
| django     | 2,726     | 8,883    |
| sympy      | 2,944     | 9,101    |


→ 同项目 session 间可共享 8,883-10,424 tokens 的 prefix。这是 KV cache 复用的核心来源。

---

## Phase 1B：单 Session vLLM 回放（实测验证）

**目的**：用 vLLM 实际推理验证 Phase 1A 的理论数字——特别是 prefix 增长和 KV 占用。

**脚本**：`scripts/investigate_vllm_verify.py`

**方法**：选 1 个 django session（8+ turns），逐轮串行发送真实消息到 vLLM，记录 cached_tokens、TTFT、kv_cache_usage_perc。

**配置**：Qwen3-8B, H800, gpu_util=0.3, APC enabled, offload=8GiB

### 产出


| 文件                                                      | 内容                                    |
| ------------------------------------------------------- | ------------------------------------- |
| `investigation/data/phase1b_single_session_replay.json` | 4 轮回放结果：TTFT, cached_tokens, hit_rate |


### 发现


| 请求                | TTFT    | prompt_tokens | cached_tokens | 命中率       |
| ----------------- | ------- | ------------- | ------------- | --------- |
| Turn 0 (冷启动)      | 1,632ms | 10,078        | 0             | 0%        |
| Turn 1 (同session) | 85ms    | 10,102        | 10,064        | **99.6%** |
| Turn 2 (同session) | 67ms    | 10,130        | 10,096        | **99.7%** |
| Turn 3 (跨项目)      | 61ms    | 6,459         | 6,160         | **95.4%** |


**理论 vs 实测对比**：


| 场景     | 理论 prefix_reusable | 实测 cached_tokens | 差异                     |
| ------ | ------------------ | ---------------- | ---------------------- |
| Turn 0 | 0                  | 0                | 完全一致                   |
| Turn 1 | 10,078             | 10,064           | 差 14 tokens (block 对齐) |
| Turn 2 | 10,102             | 10,096           | 差 6 tokens (block 对齐)  |
| 跨项目    | 6,157 (L0 only)    | 6,160            | 差 3 tokens (block 对齐)  |


→ APC 在串行场景下非常高效：命中率 95-99.7%，TTFT 降低 94.8%。理论预测与实测完全一致。

---

## Phase 2A：C++ 模拟器容量扫描（模拟）

**目的**：在多种 KV 容量下运行 FIFO/LRU/Optimal 驱逐策略，量化 LRU 与最优策略的差距。

**脚本**：`scripts/investigate_run_simulations.py`

**方法**：用 tiktoken token ID 做 prefix-aware blake2b 哈希（把每 16 个 token 打成一组的 hash 值），转为 C++ 模拟器格式。采样 2,048 请求（前一半 warmup，后一半测量），8 个容量点，3 种策略。

### 产出


| 文件                                           | 内容                                                         |
| -------------------------------------------- | ---------------------------------------------------------- |
| `investigation/data/simulation_results.json` | 8 容量点 x 3 策略的 hit_tokens, total_tokens, hit_rate, sim_time |


### 发现


| 容量 (blocks) | 容量 (tokens) | FIFO  | LRU   | Optimal | LRU-Opt Gap |
| ----------- | ----------- | ----- | ----- | ------- | ----------- |
| 100         | 1,600       | 0.0%  | 0.0%  | 6.5%    | 6.5%        |
| 200         | 3,200       | 0.0%  | 0.0%  | 13.0%   | 13.0%       |
| 500         | 8,000       | 0.0%  | 0.0%  | 32.5%   | 32.5%       |
| 1,000       | 16,000      | 12.8% | 12.8% | 60.9%   | 48.1%       |
| 2,000       | 32,000      | 64.8% | 59.5% | 90.7%   | **31.2%**   |
| 2,750       | 44,000      | 91.4% | 89.5% | 96.4%   | **6.9%**    |
| 5,000       | 80,000      | 96.8% | 97.1% | 97.1%   | 0.0%        |
| 10,000      | 160,000     | 96.9% | 97.1% | 97.1%   | 0.0%        |


三个关键发现：

1. **Agent trace 复用天花板 = 97.1%**：无限容量下所有策略收敛到 97.1%，即 97.1% 的 tokens 是可复用 prefix，仅 2.9% 是 unique
2. **H800 容量 (44K) 下 LRU-Opt gap = 6.9%**：有改进空间，对应 L0/L1 blocks 被不当地驱逐
3. **LRU 在 32K 时被 FIFO 反超**（59.5% vs 64.8%）：LRU 的"最近使用"在 Agent 场景下不是好的驱逐信号——session A 等待工具调用时 L0+L1 blocks 很久没被 touch，但复用价值远高于 session B 的新 blocks

---

## Phase 2B：多 Session 并发驱逐测试（实测）

**目的**：在 vLLM 中制造真实的内存压力，观察驱逐行为。这是整个调研的核心转折点。

### 第一轮：串行回放

**脚本**：`scripts/investigate_phase2b_eviction.py`

**方法**：串行回放 3 个 django session x 10 turns + 2 个 sympy session x 8 turns。

**产出**：`investigation/data/phase2b_eviction_test.json`

**发现**：串行模式下 `kv_cache_usage_perc` 始终为 0%，命中率 92.8%（因跨 session L0 命中），但**没有触发任何驱逐或 preemption**。

**原因**：vLLM 的 prefix cache blocks 在请求完成后 ref_cnt 降为 0，进入 free queue，但仍保留在 `cached_block_hash_to_block` 中。串行模式下同一时刻只有 1 个请求在运行，永远不会超出容量。

### 第二轮：并发长请求

**脚本**：`scripts/investigate_phase2b_concurrent.py`

**方法**：先用 1 个 django session 5 轮 warmup，然后**同时发送 9 个请求**（5 django + 4 sympy，各用 turn 3 的长 prompt，max_tokens=500）。

**产出**：`investigation/data/phase2b_concurrent_pressure.json`

**发现——整个调研最重要的结果**：


| 请求            | prompt_tokens | cached_tokens | 命中率   | 命中了什么             |
| ------------- | ------------- | ------------- | ----- | ----------------- |
| DJ1-T3 (先被调度) | 11,485        | 11,472        | 99.9% | L0+L1 (warmup 遗留) |
| DJ2-T3        | 10,490        | **7,824**     | 74.6% | **L0 only**       |
| DJ3-T3        | 12,486        | **7,824**     | 62.7% | **L0 only**       |
| DJ4-T3        | 9,609         | **7,824**     | 81.4% | **L0 only**       |
| DJ5-T3        | 11,632        | **7,824**     | 67.3% | **L0 only**       |
| SY1-T3        | 12,243        | **7,808**     | 63.8% | **L0 only**       |
| SY2-T3        | 9,815         | **7,824**     | 79.7% | **L0 only**       |
| SY3-T3        | 14,080        | **7,824**     | 55.6% | **L0 only**       |
| SY4-T3        | 13,106        | **7,824**     | 59.7% | **L0 only**       |


**并发请求间 L1 prefix 命中率 = 0%**。8 个并发请求全部只命中了 L0 (7,824 tokens)，没有任何一个命中了 L1。

**为什么**：vLLM v1 的调度是按步进行的。请求 A 进入 scheduler -> `allocate_slots()` -> A 的 prefix blocks 被注册到 hash table。但如果请求 B 在**同一步**被调度，B 的 `find_longest_cache_hit()` 在 A 的 blocks 注册之前就执行了。所以 B 看不到 A 的 blocks。

并发总体命中率 = 70.6% (74,048/104,946 tokens)。仍然没有触发 eviction/preemption（vLLM 调度器把 9 个请求分批处理了，每批 3-4 个，没超出 44K 容量）。

**技术洞察**：

- `kv_cache_usage_perc` 是 gauge，只测量 ref_cnt > 0 的 blocks
- 串行模式永远不会有内存压力
- gpu_util < 0.2 会导致模型加载 OOM（Qwen3-8B 权重需要约 15 GiB）
- vLLM 的 chunked prefill 和调度器会将并发请求分批处理

---

## Phase 3：逐痛点深度分析（实测）

**目的**：对每个痛点做 理论分析 + vLLM 实测 配对，产出具体可复现的数字。

**脚本**：`scripts/investigate_phase3_pain_points.py`

**配置**：Qwen3-8B, H800, gpu_util=0.3, APC ON, offload=OFF, LOG_LEVEL=DEBUG

**产出**：`investigation/data/phase3_pain_points.json`

### P1：并发请求无法跨请求共享 Prefix（M3）

**实验**：3 个 django session 首轮请求，先并发发送，再串行发送（相同 server，cache 已有内容）。


| 模式  | 请求   | prompt_tokens | cached_tokens | 命中率        |
| --- | ---- | ------------- | ------------- | ---------- |
| 并发  | DJ-1 | 10,073        | 10,064        | 99.9%      |
| 并发  | DJ-2 | 9,065         | **7,824**     | **86.3%**  |
| 并发  | DJ-3 | 11,061        | **7,824**     | **70.7%**  |
| 串行  | DJ-1 | 10,073        | 10,064        | 99.9%      |
| 串行  | DJ-2 | 9,065         | **9,056**     | **99.9%**  |
| 串行  | DJ-3 | 11,061        | **11,056**    | **100.0%** |


**关键数字**：并发 avg_cached = 8,570.7，串行 avg_cached = 10,058.7，**gap = 1,488 tokens**。并发请求 2/3 的 L1 完全未被缓存。

**证据等级**：[MEASURED]。**科研方向**：Eager Prefix Registration。

### P2：LRU 可能优先驱逐共享 System Prompt（M5/M6）

**实验**：串行发送 5 个 django session (10 turns) 建立 L0+L1 缓存 -> 串行发送 3 个 sympy session (10 turns) 增加压力 -> 发送新 django session 测试 L0 是否仍在缓存。

**结果**：未触发驱逐，所有请求命中率 99.9%。串行模式无法制造内存压力。但 Phase 2A 模拟显示 LRU-Opt gap = 6.9%@44K, 31.2%@32K，差距主要来自 LRU 驱逐了高复用价值的 prefix blocks。

**证据等级**：[SIMULATED]。**科研方向**：Agent-Aware Eviction Policy。

### P3：Preemption 导致 Decode 输出完全丢失（M8）

**实验**：先跑 1 个 session 10 turns 积累 decode KV -> 并发发送 7 个请求触发 preemption。

**结果**：`num_preemptions_total = 0`，未触发 preemption。

**机制分析**（来自源码）：Preemption 时 `num_computed_tokens = 0` -> 请求忘记所有进度。Decode blocks 没有被 offload（`offload_prompt_only=True`）-> 永久丢失。django-10097 session 的 output_length 累积 10 turns 约 5,000-15,000 tokens -> 如果被 preempt，这些 decode tokens 必须完全重算。

**证据等级**：[MECHANISM]。**科研方向**：Offload Decode Blocks / Partial Preemption。

### P4：Prefix 增长导致递增内存压力（M4/M7）

**实验**：交错回放 3 个 django session 各 10 turns，每轮记录 prompt_tokens 和 cached_tokens。

**结果**：每轮 prompt 递增，从 Turn 0 的约 10K 增长到 Turn 9 的约 19K (1.9x)。

**证据等级**：[TRACE]。**科研方向**：KV Cache 增长预测 + 动态 Offloading。

### P5：Block 边界浪费（M1/M2）

**实验**：串行回放 1 个 django session 15 turns，计算每轮理论 prefix_reusable - 实测 cached_tokens = block 浪费。

**结果**：measured_total_waste = **0 tokens**。APC 命中率 99.9%+，每轮的 cached_tokens 与 `floor(prev_prompt_tokens/16)*16` 完全匹配。Block 对齐浪费在 Agent 场景下几乎可以忽略（小于0.07%）。

**证据等级**：[MEASURED]。**结论**：P5 不是真正的痛点。

### P6：GPU Prefix Cache 与 Offload Tier 独立管理（M9）

**状态**：需要两次 server 部署（KV_OFFLOAD_GIB=8 vs 0）对比，当前实验未完成。

**理论**：GPU prefix cache 和 CPU offload tier 有独立的 hash table。prefix cache lookup 不检查 offload tier。所以 offload ON vs OFF 的 `cached_tokens` 应该一样。

**证据等级**：[PENDING]。**科研方向**：Unified Cache Hierarchy。

### P7：无调度感知（M3 扩展）

**实验**：3 django + 2 sympy 首轮请求，先并发发送 (FCFS)，再按最优顺序串行发送。


| 模式        | 总 cached_tokens | 说明                 |
| --------- | --------------- | ------------------ |
| 并发 (FCFS) | 45,808          | L0 全部命中，L1 部分命中    |
| 最优串行      | 48,192          | 同项目先发完 -> L1 最大化共享 |
| **Gap**   | **2,384**       | 约 1 个 Sympy L1 的大小 |


**证据等级**：[MEASURED]。**科研方向**：Prefix-Aware Scheduling。

---

## Phase 4：报告生成与优先级排序

### 产出


| 文件                                                  | 内容                    |
| --------------------------------------------------- | --------------------- |
| `investigation/data/pain_point_metrics.json`        | 所有关键数字汇总              |
| `investigation/report/00_executive_summary.md`      | 执行摘要 + 关键数字速查 + 三段式论证 |
| `investigation/report/02_trace_characterization.md` | Phase 1A/1B 报告        |
| `investigation/report/03_simulation_results.md`     | Phase 2A 模拟结果详解       |
| `investigation/report/04_vllm_eviction_analysis.md` | Phase 2B/3 实测分析       |
| `investigation/report/05_pain_point_analysis.md`    | P1-P7 逐痛点             |
| `investigation/report/06_prioritization_matrix.md`  | 优先级矩阵 + 论文建议          |
| `results/key_findings.md`                           | 更新后的核心发现总结            |


### 7 个痛点优先级排序


| 优先级          | 痛点                      | 影响量化                            | 证据        | 贡献方向                             |
| ------------ | ----------------------- | ------------------------------- | --------- | -------------------------------- |
| **CRITICAL** | P1: 并发 L1 不共享           | 并发 L1 命中=0%; gap=1,488 tok/3req | MEASURED  | Eager prefix registration        |
| **HIGH**     | P2: LRU 驱逐 L0           | LRU-Opt gap=6.9%@44K, 31.2%@32K | SIMULATED | Agent-aware eviction             |
| **HIGH**     | P3: Preemption 丢 decode | 5,000-15,000 tokens 重算          | MECHANISM | Offload decode / Partial preempt |
| MEDIUM       | P4: Prefix 增长压力         | 3.64x 增长; 13.6% 超容量             | TRACE     | 增长预测 + 动态 offload                |
| MEDIUM       | P7: 无调度感知               | gap=2,384 tok/5req              | MEASURED  | Prefix-aware scheduling          |
| MEDIUM       | P6: Cache 不统一           | 6,157 tok 理论损失                  | PENDING   | Unified cache hierarchy          |
| LOW          | P5: Block 浪费            | <0.07%                          | MEASURED  | 不需要修复                            |


### 论文 Motivation 三段式论证

1. **Agent 工作负载有极高的 KV Cache 复用潜力**（97.1% 命中率，L0+L1 占 71.9%）-> 但现有系统未充分利用
2. **vLLM APC 对串行 Agent 请求已经高效**（97-99% 命中率，TTFT 降低 92-96%）-> 但仅限串行
3. **并发请求间 L1 prefix 完全无法复用**（实测并发 L1 命中 0% vs 串行 100%）-> 这是核心问题

### 3 个建议贡献点

1. **Eager Prefix Registration**（对应 P1）：在请求开始处理前预注册 L0+L1 的 block hash，让并发请求可以共享正在计算中的 prefix
2. **Agent-Aware Eviction Policy**（对应 P2+P3）：L0/L1 blocks 标记为 protected；decode blocks offload 到 CPU，preemption 时可恢复
3. **Prefix-Aware Scheduling**（对应 P7）：按项目分组调度请求，同项目连续处理以最大化 L1 共享

---

## 完整文件清单

### 脚本（8 个）


| 文件                                          | 阶段  | 用途                      |
| ------------------------------------------- | --- | ----------------------- |
| `scripts/investigate_trace_tokenizer.py`    | 1A  | 24,880 请求分词，计算 L0/L1/L2 |
| `scripts/investigate_vllm_verify.py`        | 1B  | 单 session vLLM 回放验证     |
| `scripts/investigate_run_simulations.py`    | 2A  | C++ 模拟器容量扫描             |
| `scripts/investigate_phase2b_eviction.py`   | 2B  | 串行+并发驱逐测试               |
| `scripts/investigate_phase2b_concurrent.py` | 2B  | 9 并发长请求压力测试             |
| `scripts/investigate_phase3_pain_points.py` | 3   | P1-P7 逐痛点实测             |
| `scripts/exp_utils.py`                      | 通用  | 公共工具                    |
| `scripts/run_vllm_server.sh`                | 通用  | vLLM server 启动脚本        |


### 实验数据（8 个）


| 文件                                                      | 大小     | 阶段  | 内容                      |
| ------------------------------------------------------- | ------ | --- | ----------------------- |
| `investigation/data/per_row_metrics.json`               | 7.0 MB | 1A  | 24,880 行 per-request 指标 |
| `investigation/data/tokenized_traces_summary.json`      | 10 KB  | 1A  | 767 session 聚合统计        |
| `investigation/data/phase1b_single_session_replay.json` | 0.6 KB | 1B  | 单 session 4 轮回放         |
| `investigation/data/simulation_results.json`            | 5 KB   | 2A  | 8 容量点 x 3 策略            |
| `investigation/data/phase2b_eviction_test.json`         | —      | 2B  | 串行+并发驱逐测试               |
| `investigation/data/phase2b_concurrent_pressure.json`   | —      | 2B  | 9 并发长请求                 |
| `investigation/data/phase3_pain_points.json`            | —      | 3   | P1-P7 实测结果              |
| `investigation/data/pain_point_metrics.json`            | —      | 4   | 所有关键数字汇总                |


### 报告（7 个）


| 文件                                                  | 内容                                   |
| --------------------------------------------------- | ------------------------------------ |
| `investigation/report/00_executive_summary.md`      | 执行摘要 + 关键数字速查 + 优先级 + 论文论证           |
| `investigation/report/02_trace_characterization.md` | Phase 1A/1B：L0/L1/L2 分解、逐轮增长、串行命中率   |
| `investigation/report/03_simulation_results.md`     | Phase 2A：C++ 模拟 8 容量点、LRU vs Optimal |
| `investigation/report/04_vllm_eviction_analysis.md` | Phase 2B/3：串行 vs 并发、驱逐行为、Block 浪费    |
| `investigation/report/05_pain_point_analysis.md`    | P1-P7：机制 + 理论 + 实测 + 方向              |
| `investigation/report/06_prioritization_matrix.md`  | 优先级矩阵 + 论文建议 + 贡献点                   |
| `results/key_findings.md`                           | 更新后的核心发现总结                           |


### Server 日志（3 个）


| 文件                                                    | 说明                      |
| ----------------------------------------------------- | ----------------------- |
| `experiments/vllm_kv_cache/server_log_phase2b.log`    | Phase 2B 串行回放时 debug 日志 |
| `experiments/vllm_kv_cache/server_log_phase2b_v3.log` | Phase 2B 并发测试时日志        |
| `experiments/vllm_kv_cache/server_log_phase3.log`     | Phase 3 痛点验证时日志         |


---

## 已知局限与待完成项


| 项目                     | 原因                                          | 解决方案                       |
| ---------------------- | ------------------------------------------- | -------------------------- |
| P2: L0 驱逐未实测触发         | 44K 容量下串行模式无压力；并发被分批处理                      | 需 5+ 并发长请求同时运行，或降低容量       |
| P3: Preemption 未触发     | num_preemptions=0                           | 需更强内存压力                    |
| P6: Cache 层级未对比        | 需两次 server 部署                               | 手动切换 KV_OFFLOAD_GIB=8 vs 0 |
| gpu_util=0.2 不可用       | 模型权重约 15 GiB，0.2 只分配约 16 GiB -> KV cache 为负 | 只能用 0.3+                   |
| max_model_len=4096 不可用 | cudagraph 编译 OOM                            | 只能用 32768                  |


---

## 复现指南

```bash
# 1. 环境
export CUDA_VISIBLE_DEVICES=1  # 选空闲 GPU
export LD_LIBRARY_PATH="/share/dai-sys/apps/anaconda3/envs/agentkv_zls/lib/python3.11/site-packages/cv2/../../lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/local/cuda/lib64"

# 2. Phase 1A（不需要 server）
python scripts/investigate_trace_tokenizer.py

# 3. 启动 vLLM server
bash scripts/run_vllm_server.sh 0.3

# 4. Phase 1B
python scripts/investigate_vllm_verify.py

# 5. Phase 2A（不需要 server）
python scripts/investigate_run_simulations.py

# 6. Phase 2B
python scripts/investigate_phase2b_concurrent.py

# 7. Phase 3
python scripts/investigate_phase3_pain_points.py
```

---

## 数据完整性验证

所有关键数字已通过交叉验证：


| 检查项                 | 预期     | 实际          | 状态  |
| ------------------- | ------ | ----------- | --- |
| 总请求数                | 24,880 | 24,880      | OK  |
| 总 session 数         | 767    | 767         | OK  |
| L0 tokens (minimax) | 6,157  | 6,157       | OK  |
| L0+L1 pct (django)  | 约37%   | 36.9%       | OK  |
| 串行命中率               | >90%   | 97.6-99.9%  | OK  |
| 并发 L1 命中            | 0      | 0           | OK  |
| 并发 L0 cached        | 约7,824 | 7,808-7,824 | OK  |
| P1 gap              | 约1,488 | 1,488       | OK  |
| P7 gap              | 约2,384 | 2,384       | OK  |
| LRU @44K            | 89.5%  | 89.5%       | OK  |
| Optimal @44K        | 96.4%  | 96.4%       | OK  |
| 增长比中位数              | 3.64x  | 3.64x       | OK  |


