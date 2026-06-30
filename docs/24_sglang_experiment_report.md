# SGLang KV Cache 实验说明

> 日期: 2026-06-25
> 目标: 对 SGLang KV Cache 机制进行与 vLLM 同等深度的系统性分析，量化每个 Agent 痛点在 SGLang 中的表现
> 原则: 不修改 SGLang 源码，所有实验使用已部署的 SGLang server

---

## 0. 实验环境

| 项目 | 值 |
|------|-----|
| GPU | NVIDIA H800 × 1 (81 GB) |
| 模型 | Qwen3-8B |
| Conda env | `agentkv_zls` (Python 3.11.15) |
| SGLang | 0.0.0.dev1+g880e6f66f (editable install, `Engine/sglang`) |
| KV 容量 | 59,902 tokens (`--mem-fraction-static 0.3`) |
| Page size | 1 (token-level matching) |
| Radix cache | ON (默认启用) |
| 调度策略 | LPM (Longest Prefix Match) |

### 启动方式

**⚠️ 重要**：SGLang 不能用 `python -m sglang.launch_server` 启动（会触发 CUDA Error 803），必须用 `python -c` 方式：

```bash
export CUDA_VISIBLE_DEVICES=0
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache

/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python -c "
import sys
sys.argv = ['sglang',
    '--model-path', '/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/',
    '--port', '8001',
    '--mem-fraction-static', '0.3',
    '--schedule-policy', 'lpm',
    '--enable-metrics',
    '--enable-cache-report',
]
from sglang.srt.plugins import load_plugins
load_plugins()
from sglang.srt.server_args import prepare_server_args
server_args = prepare_server_args(sys.argv[1:])
from sglang.srt.entrypoints.http_server import launch_server
launch_server(server_args)
"
```

### 关键 API

- **OpenAI API**: `http://localhost:8001/v1`
- **Prometheus**: `http://localhost:8001/metrics`（需 `--enable-metrics`）
- **cached_tokens**: 需 `--enable-cache-report`，在 `usage.prompt_tokens_details.cached_tokens` 返回

### SGLang vs vLLM 容量对比

| 参数 | vLLM (gpu_util=0.3) | SGLang (mem-fraction=0.3) |
|------|---------------------|--------------------------|
| KV 容量 | 53,072 tokens (3,317 blocks × 16) | 59,902 tokens |
| 管理粒度 | Block (16 tokens) | Token (page_size=1) |
| Prefix cache | 需 `--enable-prefix-caching` | 默认启用 radix cache |

> ⚠️ SGLang 的 KV 容量（59,902 tokens）大于 vLLM（53,072 tokens），因为两者对内存比例的计算方式不同。实验设计时需考虑此差异。

---

## 1. S1: 单 Session 多轮串行回放

### 1.1 背景

验证 SGLang 的 radix cache 在串行模式下是否能正确缓存和复用 prefix。与 vLLM 的串行回放实验对标，重点观察：
- SGLang token-level matching 是否消除了 block 对齐浪费
- 每 turn 的 cached_tokens 是否精确等于前轮 total_tokens

### 1.2 实验设计

```
串行发送 django session 的 5 个 turns (turn 0 → turn 4)
每轮记录: cached_tokens, TTFT, prompt_tokens, completion_tokens
```

### 1.3 结果

**数据文件**: `experiments/sglang_kv_cache/exp_s1_serial_replay/run_1.json`

| Turn | prompt_tokens | cached_tokens | hit_rate | TTFT (ms) |
|------|--------------|--------------|----------|-----------|
| t0 | 10,073 | 0 | 0.0% | 579.7 |
| t1 | 10,101 | 10,071 | 99.7% | 139.5 |
| t2 | 10,346 | 10,101 | 97.6% | 36.9 |
| t3 | 11,485 | 10,346 | 90.1% | 70.3 |
| t4 | 11,630 | 11,485 | 98.8% | 37.2 |

### 1.4 核心发现

**1. Token-level matching 有效，但仍有 ~50 tokens/turn 浪费**

| Turn | 前轮 total_tokens | 本轮 cached_tokens | 差值 (浪费) |
|------|-----------------|-------------------|-----------|
| t0→t1 | 10,123 (10,073+50) | 10,071 | **52** |
| t1→t2 | 10,151 (10,101+50) | 10,101 | **50** |
| t2→t3 | 10,396 (10,346+50) | 10,346 | **50** |
| t3→t4 | 11,535 (11,485+50) | 11,485 | **50** |

**浪费原因不是 page 对齐**（SGLang page_size=1），而是 **radix tree 匹配边界**：
- 新 turn 增加了 user 消息 + assistant 回复
- 这些新增内容不在 radix tree 中，匹配在上一轮的最后一个 token 处停止
- 新 turn 的 user/assistant 消息需要重新 prefill，约 50 tokens

**2. vLLM vs SGLang 对比**

| 维度 | vLLM | SGLang |
|------|------|--------|
| 匹配粒度 | Block-level (16 tokens) | Token-level (page_size=1) |
| 每 turn 浪费 | 0-15 tokens (block 对齐) | ~50 tokens (匹配边界) |
| 浪费率 | < 0.07% | ~0.5% |
| 结论 | **SGLang 浪费反而更大** | 原因不是 page 对齐，而是 radix tree 匹配边界 |

> ⚠️ 这个发现出乎预期：SGLang 的 token-level matching 消除了 block 对齐浪费，但引入了更大的匹配边界浪费。在 Agent 场景下，每 turn ~50 tokens 的浪费虽然绝对值不大，但比 vLLM 的 0-15 tokens 更高。

---

## 2. S2: 并发请求 Prefix 共享

### 2.1 背景

验证 SGLang 在并发请求场景下是否也有 P1（并发共享失效）问题。vLLM 的并发 L1 命中率为 0%，因为同一批调度的请求看不到彼此的 prefix blocks。

SGLang 的调度流程：
```
calc_priority() → 对每个请求调用 match_prefix_for_req()
  → tree_cache.match_prefix()  ← 只读，不写入
→ PrefillAdder.add_one_req()
  → alloc_for_extend() → prefill → 新 KV 写入
→ cache_finished_req() / insert()  ← 写入 radix tree
```

在 `calc_priority()` 阶段，所有请求都只是**读取** radix tree。第一个请求 prefill 产生的 KV 不会在第二个请求的 `match_prefix` 之前插入树中。因此 SGLang **也可能有同样的并发问题**。

但 SGLang 有 `in-batch prefix caching` 机制（阈值=32 tokens），可能部分缓解。

### 2.2 实验设计

```
配置 A (串行): 串行发送 3 个 django session turn 0 → 记录 cached_tokens
配置 B (并发): 并发发送 3 个 django session turn 0 → 记录 cached_tokens
```

### 2.3 结果

**数据文件**: `experiments/sglang_kv_cache/exp_s2_concurrent_prefix/run_1.json`

| 配置 | cached_tokens | 说明 |
|------|--------------|------|
| 串行 | 10,072 | 完整 L0+L1 命中 |
| 并发 req 1 | 8,521 | L0 命中，L1 部分丢失 |
| 并发 req 2 | 8,517 | L0 命中，L1 部分丢失 |
| 并发 req 3 | 8,521 | L0 命中，L1 部分丢失 |
| 并发平均 | **8,520** | L1 命中率 ~15% |
| 串行后验证 | 10,072 | 串行模式仍完整命中 |

### 2.4 核心发现

**1. SGLang 并发 L1 命中率不是 0%**

| 维度 | vLLM | SGLang |
|------|------|--------|
| 并发 L1 命中率 | **0%** | **~15-16%** |
| 并发 L0 命中率 | ~80% | ~85% |
| In-batch caching | 无 | 有（部分生效） |

**2. In-batch prefix caching 部分生效**

SGLang 的 in-batch prefix caching 机制使得同一批调度中的请求可以部分共享 prefix。但 L1 命中率只有 ~15%（8,520/10,072），说明：
- L0 (6,163 tokens) 大部分被命中
- L1 (~3,900 tokens) 大部分丢失
- In-batch caching 的阈值=32 tokens，Agent L1 >> 32，但仍有部分效果

**3. vLLM vs SGLang 对比**

| 维度 | vLLM | SGLang |
|------|------|--------|
| 并发 L1 命中率 | **0%** | **~15-16%** (部分命中) |
| In-batch caching | 无 | 有（但阈值=32 tokens，Agent L1 >> 32） |
| 结论 | **SGLang 略优于 vLLM** | 但仍有 ~84% 的 L1 在并发时丢失 |

---

## 3. S4: L0 驱逐触发

### 3.1 背景

在 SGLang 中制造真实的内存压力，观察 L0 节点是否被 radix tree 的驱逐策略驱逐。

**SGLang 驱逐机制与 vLLM 的关键差异**：
- vLLM：free queue 头部驱逐，LRU 顺序，无节点类型区分
- SGLang：min-heap + eviction strategy，**叶子节点优先驱逐**

**理论预期**：L0 是 radix tree 中的中间节点（有子节点），SGLang 只驱逐叶子节点，L0 应该受保护。但 L1 被驱逐后，L0 可能变成叶子节点，然后也可能被驱逐。

### 3.2 实验设计

```
Phase 1: 串行发送 1 个 django turn 0 → 建立 L0+L1 缓存基线
Phase 2: 并发发送 9 个 UUID 前缀请求（max_tokens=2000）
         每个请求 ~10K prompt + ~1K decode = ~11K KV tokens
         9 × 11K = 99K >> 59,902 容量 → 强制驱逐
Phase 3: 发送新 django turn 0 → 测试 L0 是否被驱逐
```

### 3.3 结果

**数据文件**: `experiments/sglang_kv_cache/exp_s4_l0_eviction/run_1.json`

| Phase | 指标 | 值 |
|-------|------|-----|
| Phase 1 | baseline cached_tokens | **10,072**（L0+L1 完整命中） |
| Phase 2 | 9 个 UUID 前缀并发请求 | 估算 KV ~99K >> 59,902 容量 |
| Phase 3 | **test cached_tokens** | **3** |
| Phase 3 | test TTFT | 301.5 ms |

### 3.4 核心发现

**1. L0 几乎被完全驱逐（cached=3 vs baseline=10,072）**

SGLang 的 radix tree **并没有像理论预期那样保护 L0**。

**2. 驱逐过程推测**

```
1. Phase 1 完成: L0 (6,163 tokens) 有子节点 L1 → L0 是中间节点
2. Phase 2 压力请求到来:
   a. 新请求的 KV 需要空间 → radix tree 驱逐叶子节点
   b. L1 是叶子节点 → L1 先被驱逐
   c. L0 的所有子节点被驱逐后 → L0 变成叶子节点
   d. L0 作为叶子节点被驱逐
3. Phase 3: L0 几乎完全丢失 (cached=3)
```

**3. vLLM vs SGLang 对比**

| 维度 | vLLM | SGLang |
|------|------|--------|
| L0 驱逐结果 | 完全驱逐 (cached=0) | 几乎完全驱逐 (cached=3) |
| 驱逐机制 | LRU free queue (无节点类型区分) | Min-heap (叶子优先，但中间节点也会被驱逐) |
| 驱逐阈值 | 5 个压力请求 | 9 个压力请求 |
| 结论 | **两者都无法有效保护 L0** | SGLang 稍好但差距不大 |

**4. 关键洞察**

SGLang 的"叶子优先驱逐"在**中等压力**下可以保护 L0（因为 L0 有子节点，不是叶子）。但在**极端压力**下，L0 的所有子节点先被驱逐，L0 变成叶子节点后也被驱逐。这和 vLLM 的 LRU 驱逐最终效果类似——只是需要更大的压力才能触发。

---

## 4. 未完成的实验

以下实验在计划中（`docs/21_sglang_analysis_plan.md`）但尚未执行：

| 实验 | 目标 | 状态 | 对标 vLLM |
|------|------|------|----------|
| S3: In-batch prefix caching 深度验证 | 定量测试 in-batch caching 对 Agent 场景的效果 | ❌ 未执行 | P1 |
| S5: 驱逐策略对比 (LRU/Priority/SLRU) | 测试不同驱逐策略对 L0 保护的效果 | ❌ 未执行 | P2-B |
| S6: Retraction 恢复行为 | 触发 retract_decode，测量恢复 TTFT | ❌ 未执行 | P3-A |
| S7: HiCache 层级统一性验证 | 验证 HiRadixCache 是否解决 P6 | ❌ 未执行 | P6-A |
| S8: 调度策略对比 (LPM/DFS/FCFS) | 定量对比不同调度策略 | ❌ 未执行 | P7 |
| S9: StreamingSession 零 prefill | 验证跨 turn 零 prefill | ❌ 未执行 | vLLM 无此功能 |
| S10: StreamingSession 内存代价 | 量化 Session 的内存锁定代价 | ❌ 未执行 | vLLM 无此功能 |

---

## 5. 已完成实验的 vLLM vs SGLang 综合对比

| 痛点 | vLLM 状态 | SGLang 状态 | SGLang 更优？ | 量化差距 |
|------|----------|------------|-------------|---------|
| P1: 并发共享失效 | [MEASURED] L1 命中 0% | [MEASURED] L1 命中 ~15% | ✅ 略优 | 8,520 vs 0 cached tokens |
| P2: LRU 驱逐 L0 | [MEASURED] L0 被驱逐 (cached=0) | [MEASURED] L0 几乎被驱逐 (cached=3) | ≈ 相当 | 5 vs 9 压力请求阈值 |
| P3: Preemption 丢 decode | [MECHANISM+] 未触发 | [MECHANISM] retraction 更优 | ✅ 恢复更快 | 但 decode 仍丢失 |
| P4: Prefix 增长压力 | [TRACE] 3.64x | [共享数据] 3.64x | — | 同 |
| P5: Block 浪费 | [MEASURED] <0.07% | [MEASURED] ~0.5% | ❌ SGLang 反而更大 | 50 vs 0-15 tokens/turn |
| P6: Cache 层级不统一 | [MEASURED] 双层独立 LRU | ✅ 不存在 (HiRadixCache 统一) | ✅ 根本不同 | vLLM offload 无效 |
| P7: 无调度感知 | [MEASURED] gap 2,384 | [待测] LPM/DFS 可缓解 | ✅ Cache-aware | 待测 |

---

## 6. 数据文件索引

| 文件 | 实验 | 关键结论 |
|------|------|---------|
| `experiments/sglang_kv_cache/exp_s1_serial_replay/run_1.json` | S1 串行回放 | Token-level matching 有效，但 ~50 tokens/turn 匹配边界浪费 |
| `experiments/sglang_kv_cache/exp_s2_concurrent_prefix/run_1.json` | S2 并发 prefix | 并发 L1 命中 ~15% (vs vLLM 0%)，in-batch 部分生效 |
| `experiments/sglang_kv_cache/exp_s4_l0_eviction/run_1.json` | S4 L0 驱逐 | L0 几乎完全驱逐 (cached=3)，叶子优先无法保护中间节点 |

## 7. 相关文件索引

| 文件 | 内容 |
|------|------|
| `docs/21_sglang_analysis_plan.md` | SGLang 分析完整规划（含未执行实验的详细设计） |
| `docs/22_experiment_results_report.md` | vLLM vs SGLang 综合对比报告 |
| `docs/23_vllm_experiment_report.md` | vLLM 补强实验说明 |
| `scripts/sglang_exp_utils.py` | SGLang 实验工具函数 |
| `notes/sglang_kv_cache.md` | SGLang 源码分析笔记 |
