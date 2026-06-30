# P2/P3/P6 补强实验计划

> 日期: 2026-06-25
> 状态: 计划（未执行）
> 目标: 将 P2、P3、P6 的证据等级从 [SIMULATED]/[MECHANISM]/[PENDING] 提升至 [MEASURED]
> ⚠️ 原则：不修改 vLLM 源码，所有实验使用已部署的 vLLM server

---

## 0. 实验环境

### Python 环境

vLLM 和实验脚本共用同一个 Conda 环境：

| 项目 | 值 |
|------|-----|
| Conda env | `agentkv_zls` (`/share/dai-sys/apps/anaconda3/envs/agentkv_zls`) |
| Python | 3.11.15 |
| vLLM | 0.8.5.dev0 (editable install, `Engine/vllm`) |
| 模型 | Qwen3-8B (`/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/`) |
| 关键依赖 | torch, transformers, tiktoken, pyarrow, openai, matplotlib, numpy |

### vLLM Server 启动方式

```bash
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python -m vllm.entrypoints.openai.api_server
```

通过 `scripts/run_vllm_server.sh` 调用，该脚本已配置好所有实验参数。注意需设置 `LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH`。

### 实验脚本运行方式

```bash
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python scripts/run_exp*.py
```

所有脚本通过 `sys.path.insert(0, os.path.dirname(...))` 引用 `exp_utils.py`。

### ⚠️ SGLang 环境备注

SGLang 也安装在同一个 `agentkv_zls` 环境中（editable install 指向 `Engine/sglang`），但启动方式不同：
- **不能用** `python -m sglang.launch_server`（会触发 CUDA Error 803）
- **必须用** `python -c` 方式启动（先初始化 CUDA 再导入 SGLang）
- 需设置 `TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache`（避免 `~/.cache/tvm-ffi` 权限问题）
- 需加 `--enable-metrics` 和 `--enable-cache-report` 参数
- SGLang 的 KV 容量（mem-fraction=0.3 时 ~60K tokens）大于 vLLM（gpu_util=0.3 时 ~44K tokens）
- 详见 `docs/21_sglang_analysis_plan.md`

---

## 1. 核心问题：为什么之前的实验失败了

**所有三个痛点共享同一个根本原因**：在 gpu_util=0.3（44K token 容量）下，vLLM 的调度器分批处理请求，实际同时 KV 占用从未超过容量，因此**从未触发真正的驱逐或抢占**。

| 实验 | 痛点 | 结果 | 失败原因 |
|------|------|------|---------|
| exp5_lru / exp5_aware | P2 | 无驱逐发生 | 5 个 session 串行发送，请求间释放 blocks |
| exp6_default / recompute / swap | P3 | num_preemptions=0 | 请求串行处理，同时占用 < 44K |
| exp3_offload_on / off | P6 | aggregated={} | 实验未完成，无有效数据 |
| investigate_phase2b_eviction | P2 | 无驱逐 | 3+2 session 串行，同时占用不足 |
| investigate_phase3 run_p3 | P3 | 0 preemptions | 8 并发请求仍被分批调度 |

**关键洞察**：vLLM v1 的调度器在每一步（step）中，会尝试将所有 waiting 请求一起调度。但 `allocate_slots()` 在内存不足时不会抢占——它只是跳过无法分配的请求。**抢占只在 running 请求占用内存导致新请求无法调度时才发生**。因此，必须让 running 请求的 KV 占用接近容量，再发送新请求。

---

## 1. 触发驱逐/抢占的新策略

### 策略 A：长输出 + 并发新请求（推荐）

**原理**：让一个请求运行足够长时间（生成大量 decode tokens），使其 KV 占用接近容量，然后并发发送新请求触发抢占。

**具体方案**：
1. 发送 1 个请求，`max_tokens=2000`（decode 输出 ~2000 tokens，加上 prompt ~8K = ~10K KV 占用）
2. 等待其完成
3. 发送第 2 个请求，`max_tokens=2000`（此时 KV 占用 ~10K + ~10K = ~20K）
4. 等待其完成
5. 发送第 3 个请求，`max_tokens=2000`（KV 占用 ~30K）
6. **关键**：在第 3 个请求仍在 running 时（decode 阶段），并发发送第 4、5 个请求
7. 此时 running 请求占用 ~30K + 新请求需要 ~10K = ~40K → 接近 44K 容量 → 触发抢占

**为什么这次能成功**：
- 之前的实验用 `max_tokens=5`，decode 输出极短，请求很快完成并释放 blocks
- 新策略用 `max_tokens=2000`，请求在 decode 阶段持续占用 KV blocks
- 多个 running 请求的 KV 占用会累积，最终超出容量

### 策略 B：降低 gpu_util（备选）

**原理**：降低 GPU KV cache 容量，使驱逐更容易触发。

**限制**：
- gpu_util < 0.2 会导致 OOM（模型权重 + KV cache 超出 GPU 内存）
- gpu_util = 0.2 → ~29K tokens 容量，可能勉强可行
- gpu_util = 0.25 → ~36K tokens 容量

**方案**：先尝试策略 A，如果仍无法触发，再尝试 gpu_util=0.25。

### 策略 C：多 session 多轮并发回放（最接近真实场景）

**原理**：同时回放多个 session 的多轮对话，让 KV 占用自然增长超出容量。

**方案**：
1. 并发发送 3 个 django session 的 turn 0-5（每个 session ~15K tokens at turn 5）
2. 3 个 session 同时 running → 总 KV 占用 ~45K > 44K → 触发驱逐/抢占

**实现挑战**：需要精确控制请求时序，确保多个请求同时处于 running 状态。

---

## 2. P2 补强实验：LRU 驱逐 L0 的实测验证

### 当前证据状态

| 证据 | 等级 | 内容 |
|------|------|------|
| C++ 模拟 LRU vs Optimal | [SIMULATED] | 44K 容量 gap=6.9%, 32K gap=31.2% |
| Trace 分析 | [TRACE] | 13.6% session 单独超 44K 容量 |
| 机制分析 | [MECHANISM] | L0 ref_cnt=0 后进入 free queue，可能被驱逐 |
| vLLM 实测 | **缺失** | 从未触发真实驱逐 |

### 目标

将 P2 证据等级从 [SIMULATED] 提升至 [MEASURED]，具体：
1. **在 vLLM 中触发真实的 L0 block 驱逐**
2. **测量驱逐后 L0 命中率下降的幅度**
3. **量化 LRU vs Agent-Aware 驱逐策略的差异**

### 实验 P2-A：触发 L0 驱逐

**前置条件**：vLLM server, gpu_util=0.3, APC enabled, offload=0

**步骤**：

```
Phase 1: 建立 L0+L1 缓存
  - 串行发送 3 个 django session 的 turn 0（每个 ~10K tokens）
  - 验证：第 2/3 个请求 cached_tokens ≈ L0+L1 ≈ 7,824-10,064

Phase 2: 填充 KV cache 至接近容量
  - 串行发送 3 个 django session 的 turn 1-5（每个 session 增长到 ~15K tokens）
  - 关键：使用 max_tokens=500，让 decode 输出也占用 KV
  - 验证：kv_cache_usage_perc > 70%

Phase 3: 用不同项目请求制造压力
  - 串行发送 3 个 sympy session 的 turn 0-3（每个 ~12K tokens）
  - 关键：sympy 的 L1 与 django 不同，不共享 L1 blocks
  - 验证：kv_cache_usage_perc > 90%

Phase 4: 测试 L0 是否被驱逐
  - 发送 1 个新 django session 的 turn 0
  - 记录 cached_tokens
  - 如果 cached_tokens < L0_block_aligned (7,824) → L0 被驱逐 ✅
  - 如果 cached_tokens ≈ L0 但 < L0+L1 → L1 被驱逐但 L0 保留
  - 如果 cached_tokens ≈ L0+L1 → 未触发驱逐，需增加压力
```

**如果 Phase 4 未触发驱逐**：
- 增加 Phase 2/3 的轮次（turn 1-8 或更多）
- 或使用策略 B（gpu_util=0.25）
- 或在 Phase 3 使用 max_tokens=1000 增加每个请求的 KV 占用

**关键指标**：

| 指标 | 采集方式 | 预期值 |
|------|---------|--------|
| Phase 4 cached_tokens | OpenAI usage API | < 7,824（L0 被驱逐）或 7,824-10,064（仅 L1 被驱逐） |
| kv_cache_usage_perc | Prometheus | Phase 3 后 > 90% |
| prefix_cache_hits / queries | Prometheus | Phase 4 命中率下降 |
| DEBUG 日志 evict 事件 | vLLM log | 应看到 block eviction 记录 |

### 实验 P2-B：LRU vs Agent-Aware 驱逐对比

**前置条件**：P2-A 成功触发驱逐后进行

**方案**：不修改 vLLM 源码，通过**请求调度顺序**模拟 Agent-Aware 驱逐效果。

```
配置 A（默认 LRU）：
  Phase 1: 3 django turn 0-5（建立 L0+L1_django 缓存）
  Phase 2: 3 sympy turn 0-3（制造压力，可能驱逐 L0/L1_django）
  Phase 3: 新 django turn 0 → 记录 cached_tokens_A

配置 B（模拟 Agent-Aware）：
  Phase 1: 3 django turn 0-5（同上）
  Phase 2: 3 sympy turn 0-3（同上）
  Phase 2.5: 发送 1 个 django turn 0（"touch" L0 blocks，提升其在 free queue 中的位置）
  Phase 3: 新 django turn 0 → 记录 cached_tokens_B
```

**预期**：cached_tokens_B > cached_tokens_A，因为 Phase 2.5 的 touch 操作将 L0 blocks 移到 free queue 尾部，降低被驱逐优先级。

**关键对比**：

| 指标 | 配置 A (LRU) | 配置 B (Agent-Aware) |
|------|-------------|---------------------|
| Phase 3 cached_tokens | 较低（L0 可能被驱逐） | 较高（L0 被 touch 保护） |
| Phase 3 TTFT | 较高（需重算被驱逐的 prefix） | 较低（prefix 命中） |
| 差异 | — | 量化 Agent-Aware 策略的收益 |

### 实验 P2-C：模拟器扩展——逐层命中率分解

**目标**：在 C++ 模拟器中追踪 L0/L1/L2 各层的驱逐情况，补充 vLLM 无法直接观测的细粒度数据。

**修改 `investigate_run_simulations.py`**：
1. 在模拟器输出中增加 per-layer 驱逐统计
2. 追踪：L0 blocks 被驱逐次数、L1 blocks 被驱逐次数、L2 blocks 被驱逐次数
3. 在不同容量点（16K, 24K, 32K, 44K, 64K）下运行
4. 输出：LRU vs Optimal 的逐层命中率对比

**预期输出**：

| 容量 | LRU L0 命中率 | Opt L0 命中率 | LRU L1 命中率 | Opt L1 命中率 | 总 gap |
|------|-------------|-------------|-------------|-------------|--------|
| 44K | ? | ~100% | ? | ? | 6.9% |
| 32K | ? | ~100% | ? | ? | 31.2% |
| 16K | ? | ~100% | ? | ? | 48.1% |

---

## 3. P3 补强实验：Preemption 导致 Decode 输出丢失的实测验证

### 当前证据状态

| 证据 | 等级 | 内容 |
|------|------|------|
| 源码机制 | [MECHANISM] | `_preempt_request()` 设 `num_computed_tokens=0`，释放所有 blocks |
| 源码机制 | [MECHANISM] | `offload_prompt_only=True`，decode blocks 不被 offload |
| Trace 分析 | [TRACE] | 10 turns decode 累积 ~5,000-15,000 tokens |
| vLLM 实测 | **缺失** | num_preemptions=0，从未触发抢占 |

### 目标

将 P3 证据等级从 [MECHANISM] 提升至 [MEASURED]，具体：
1. **在 vLLM 中触发真实的 preemption 事件**
2. **测量被 preempt 请求的恢复 TTFT（应接近冷启动）**
3. **对比 swap vs recompute vs default 三种策略在真实抢占下的表现**

### 实验 P3-A：触发 Preemption

**前置条件**：vLLM server, gpu_util=0.3, APC enabled, offload=0, LOG_LEVEL=debug

**核心策略**：让多个请求同时处于 running 状态（decode 阶段），使 KV 占用累积超出容量。

```
Phase 1: 启动长运行请求
  - 发送 req_A: django session turn 0, max_tokens=2000
  - 不等待完成，立即发送 req_B: django session turn 0 (不同 session), max_tokens=2000
  - 不等待完成，立即发送 req_C: django session turn 0 (不同 session), max_tokens=2000
  - 3 个请求同时 running → KV 占用 ≈ 3 × (10K prompt + 2K decode) = ~36K

Phase 2: 触发抢占
  - 在 req_A/B/C 仍在 decode 时，发送 req_D: sympy session turn 0, max_tokens=2000
  - req_D 需要 ~10K KV blocks，但剩余容量 ≈ 44K - 36K = ~8K → 不足
  - → scheduler 应抢占 req_C（最后进入的 running 请求）
  - 验证：Prometheus num_preemptions > 0

Phase 3: 观察恢复
  - req_C 被放回 waiting queue
  - 等 req_A/B 完成后，req_C 重新调度
  - 记录 req_C 恢复后的 TTFT
  - 对比：req_C 首次 TTFT vs 恢复 TTFT
```

**实现细节**：
- 使用 `asyncio.gather` 并发发送 Phase 1 的 3 个请求
- 在 Phase 1 请求开始 decode 后（等待 ~1 秒），发送 Phase 2 的请求
- 使用 streaming API 监控请求状态

**如果 Phase 2 未触发抢占**：
- 增加 Phase 1 的 max_tokens（3000, 4000...）
- 或增加 Phase 1 的请求数（4-5 个）
- 或使用策略 B（gpu_util=0.25, 容量 ~36K）

**关键指标**：

| 指标 | 采集方式 | 预期值 |
|------|---------|--------|
| num_preemptions | Prometheus | > 0 |
| req_C 恢复 TTFT | OpenAI streaming | 接近冷启动 TTFT (~1000ms+) |
| req_C 恢复 cached_tokens | OpenAI usage | ≈ L0 block_aligned（仅 prompt prefix 可恢复） |
| req_C decode tokens 丢失量 | 计算 | = 原始 completion_tokens - 恢复后重新生成的 tokens |
| DEBUG 日志 preempt 事件 | vLLM log | 应看到 "preempting request" 记录 |

### 实验 P3-B：三种 Preemption 策略对比

**前置条件**：P3-A 成功触发抢占后进行

**三种配置**：

| 配置 | 参数 | 预期行为 |
|------|------|---------|
| A: swap | KV_OFFLOAD_GIB=8 | 被 preempt 的 prompt blocks offload 到 CPU，恢复时 swap-in |
| B: recompute | offload=0, kv-load-failure-policy=recompute | 无 offload，恢复时重算 prompt |
| C: default | offload=0, 默认策略 | 无 offload，恢复时依赖 prefix cache（如果 blocks 还在） |

**每种配置重复 P3-A 的步骤**，对比：

| 指标 | swap | recompute | default |
|------|------|-----------|---------|
| 恢复 TTFT | 较低（CPU swap-in） | 最高（完全重算） | 中等（取决于 prefix cache 存活） |
| 恢复 cached_tokens | 较高（prompt 从 CPU 恢复） | 0（完全重算） | 取决于驱逐情况 |
| Decode 恢复 | ❌ 仍丢失 | ❌ 仍丢失 | ❌ 仍丢失 |
| 总延迟 | ? | ? | ? |

**关键发现预期**：三种策略都无法恢复 decode 输出——这证实了 P3 的核心论点：`offload_prompt_only=True` 使得 decode KV 在抢占后永久丢失。

### ~~P3-C：Decode Offload 原型验证~~（暂不执行）

> **决策**：暂不修改 vLLM 源码。P3 的核心论点（preemption 导致 decode 丢失）通过 P3-A/B 的实测数据即可充分论证。Decode Offload 原型属于解决方案验证，留待论文实现阶段进行。

**原方案（存档）**：将 `offload_prompt_only` 从 `True` 改为 `False`，验证 decode blocks 能否被 offload 并恢复。

**修改位置**：`Engine/vllm/vllm/v1/kv_offload/base.py` line 431-432

**如后续需要执行**：
1. 修改 `self.extra_config.get("offload_prompt_only", True)` → `False`
2. 重复 P3-A 步骤，对比 decode offload 开启前后的恢复 TTFT
3. 预期：decode blocks 被 offload 后，恢复 TTFT 显著低于 recompute 策略
4. 风险：修改可能引入 bug；decode blocks 数量大，offload 开销可能很高

---

## 4. P6 补强实验：Cache 层级不统一的实测验证

### 当前证据状态

| 证据 | 等级 | 内容 |
|------|------|------|
| 源码机制 | [MECHANISM] | `find_longest_cache_hit()` 只查 GPU `cached_block_hash_to_block`，不查 offload tier |
| 源码机制 | [MECHANISM] | GPU prefix cache 和 CPU offload 有独立 hash table |
| exp3_offload_on/off | **失败** | aggregated={}，无有效数据 |
| vLLM 实测 | **缺失** | 从未完成 offload ON vs OFF 的 A/B 对比 |

### 目标

将 P6 证据等级从 [PENDING] 提升至 [MEASURED]，具体：
1. **验证 offload ON vs OFF 时 cached_tokens 是否相同**（核心假设）
2. **测量 offload tier 的 store/load 行为**
3. **量化统一层级管理的潜在收益**

### 实验 P6-A：Offload ON vs OFF 的 A/B 对比

**这是 P6 最关键的实验**。需要两次独立的 server 部署。

**配置 A：Offload ON**

```bash
# 部署 server
KV_OFFLOAD_GIB=8 bash scripts/run_vllm_server.sh
# 等待就绪
python -c "import openai; c=openai.Client(base_url='http://localhost:8000/v1'); c.models.list()"
```

**配置 B：Offload OFF**

```bash
# Kill 旧 server, 重新部署
lsof -ti :8000 | xargs kill -9 2>/dev/null; sleep 3
KV_OFFLOAD_GIB=0 bash scripts/run_vllm_server.sh
# 等待就绪
python -c "import openai; c=openai.Client(base_url='http://localhost:8000/v1'); c.models.list()"
```

**两种配置使用完全相同的请求序列**：

```
Phase 1: 建立 L0+L1 缓存
  - 串行发送 3 个 django session turn 0-5
  - 记录每轮 cached_tokens, TTFT, kv_cache_usage_perc

Phase 2: 制造驱逐压力
  - 串行发送 3 个 sympy session turn 0-3
  - 记录 kv_cache_usage_perc（应 > 80%）

Phase 3: 测试 L0 恢复
  - 发送 1 个新 django session turn 0
  - 记录 cached_tokens, TTFT
  - 采集 Prometheus offload 指标
```

**核心对比**：

| 指标 | Offload ON | Offload OFF | 预期 |
|------|-----------|------------|------|
| Phase 3 cached_tokens | X | X | **X ≈ Y**（如果层级不统一） |
| Phase 3 TTFT | T_on | T_off | T_on ≈ T_off |
| kv_offload_store_bytes | > 0 | 0 | ON 时有 store 操作 |
| kv_offload_load_bytes | > 0? | 0 | **关键：ON 时 load 是否 > 0？** |

**判断标准**：
- 如果 `cached_tokens_ON == cached_tokens_OFF` → **证实 P6**：offload tier 不参与 prefix cache lookup
- 如果 `cached_tokens_ON > cached_tokens_OFF` → **部分否定 P6**：offload tier 在某些路径上参与了恢复
- 如果 `kv_offload_load_bytes > 0` 但 `cached_tokens` 无差异 → offload 有 load 操作但未反映在 prefix cache 命中中

### 实验 P6-B：Offload Tier 命中率独立测量

**目标**：直接测量 offload tier 的 store/load 行为，理解其与 prefix cache 的交互。

**方案**：在 Offload ON 配置下，逐步发送请求并采集 Prometheus 指标。

```
Step 1: 发送 1 个 django turn 0 → 记录 offload_store_bytes 增量
Step 2: 发送 5 个不同项目请求 → 触发驱逐 → 记录 offload_store_bytes 增量
Step 3: 发送 1 个 django turn 0 → 记录 offload_load_bytes 增量
Step 4: 对比 Step 3 的 cached_tokens 与 Step 1 的 cached_tokens
```

**关键问题**：
1. 被 GPU 驱逐的 L0 blocks 是否被 store 到 offload tier？（store_bytes 增量 > 0？）
2. 新请求是否从 offload tier load 了 L0 blocks？（load_bytes 增量 > 0？）
3. 如果 load 了，为什么 cached_tokens 没有增加？（load 是异步的？load 后不注册到 prefix cache？）

### 实验 P6-C：源码级验证——Offload Load 路径追踪

**目标**：通过 vLLM DEBUG 日志和源码分析，确认 offload tier 的 load 结果是否被 prefix cache 系统感知。

**方案**：
1. 在 Offload ON 配置下运行 P6-A
2. 设置 `LOG_LEVEL=debug`，收集完整日志
3. 在日志中搜索以下关键事件：
   - `kv_offload_store` — blocks 被 store 到 offload tier
   - `kv_offload_load` — blocks 从 offload tier 加载
   - `find_longest_cache_hit` — prefix cache 查找
   - `cache_full_blocks` — blocks 注册到 prefix cache
4. 分析：offload load 完成后，loaded blocks 是否被注册到 `cached_block_hash_to_block`？

**源码追踪路径**：
```
请求到达 → scheduler.schedule()
  → kv_cache_manager.get_computed_blocks()
    → coordinator.find_longest_cache_hit()  ← 只查 GPU hash table
  → 如果 GPU miss → kv_connector.build_connector_meta()
    → offloading_manager.lookup()  ← 查 offload tier
    → 如果 offload hit → prepare_load() → 异步加载
  → 加载完成后 → blocks 是否注册到 GPU prefix cache？
```

**预期发现**：offload tier 的 load 是通过 KV connector 路径完成的，加载的 blocks 直接写入 GPU KV cache 但**不注册到 `cached_block_hash_to_block`**。因此后续请求的 `find_longest_cache_hit()` 仍然找不到这些 blocks。

---

## 5. 实验执行顺序与依赖关系

```
P2-A (触发 L0 驱逐)
  │
  ├── 成功 → P2-B (LRU vs Agent-Aware 对比)
  │          P2-C (模拟器逐层分解) [可并行]
  │
  └── 失败 → 调整策略（增加压力 / 降低 gpu_util）→ 重试 P2-A

P3-A (触发 Preemption)
  │
  ├── 成功 → P3-B (三种策略对比)
  │
  └── 失败 → 调整策略（增加 max_tokens / 降低 gpu_util）→ 重试 P3-A

P6-A (Offload ON vs OFF) [独立于 P2/P3，可并行]
  │
  ├── 证实 P6 → P6-B (Offload 命中率测量)
  │            P6-C (源码级验证) [可并行]
  │
  └── 部分否定 P6 → 分析原因，调整 P6 论点
```

**建议执行顺序**：
1. **先跑 P2-A**：驱逐实验相对容易触发，成功后为 P3 和 P6 提供压力场景模板
2. **再跑 P3-A**：抢占更难触发，但 P2-A 的经验可帮助调整参数
3. **P6-A 可与 P2/P3 并行**：只需两次 server 部署，不依赖驱逐/抢占成功
4. **P2-B, P3-B, P6-B** 在各自 A 实验成功后进行
5. **P2-C, P6-C** 是分析型实验，可在任何时间进行

---

## 6. 脚本计划

### 新脚本

| 脚本 | 用途 | 基于现有脚本 |
|------|------|------------|
| `scripts/run_p2a_l0_eviction.py` | P2-A: 触发 L0 驱逐 | `run_exp5.py` + `investigate_phase2b_eviction.py` |
| `scripts/run_p2b_lru_vs_aware.py` | P2-B: LRU vs Agent-Aware 对比 | `run_exp5.py` |
| `scripts/run_p3a_trigger_preempt.py` | P3-A: 触发 Preemption | `run_exp6.py` + `investigate_phase3_pain_points.py` |
| `scripts/run_p3b_preempt_strategies.py` | P3-B: 三种策略对比 | `run_exp6.py` |
| `scripts/run_p6a_offload_ab.py` | P6-A: Offload ON vs OFF A/B | `run_exp3.py`（重写，修复空结果问题） |
| `scripts/run_p6b_offload_metrics.py` | P6-B: Offload 命中率测量 | 新写 |

### 可复用的现有基础设施

| 组件 | 来源 | 用途 |
|------|------|------|
| `send_and_record()` | `exp_utils.py` | 发送请求并记录指标 |
| `KVTimelineCollector` | `exp_utils.py` | 采集 KV 使用率时间线 |
| `get_prometheus_metrics()` | `exp_utils.py` | 采集 Prometheus 指标 |
| `make_layered_messages()` | `exp_utils.py` | 构造 L0/L1/L2 分层 prompt |
| `get_real_l0_text()` / `get_real_l1_text()` | `exp_utils.py` | 获取真实 Agent prompt |
| `load_session_turns()` | `investigate_phase3_pain_points.py` | 加载 LMCache trace session |
| `messages_to_openai_format()` | `investigate_phase3_pain_points.py` | 转换消息格式 |
| `run_vllm_server.sh` | `scripts/` | Server 部署（支持 KV_OFFLOAD_GIB 参数） |

### P2-A 脚本核心逻辑（伪代码）

```python
async def run_p2a():
    # Phase 1: 建立 L0+L1_django 缓存
    for i in range(3):
        r = await send_and_record(django_session[i].turn[0],
                                  max_tokens=500)  # 长输出增加 KV 占用
    # 验证 KV 使用率
    kv_usage = get_prometheus_metrics()["kv_cache_usage_perc"]
    assert kv_usage > 30%, f"KV usage too low: {kv_usage}%"

    # Phase 2: 填充至接近容量
    for i in range(3):
        for t in range(1, 6):  # turn 1-5
            r = await send_and_record(django_session[i].turn[t],
                                      max_tokens=500)
    kv_usage = get_prometheus_metrics()["kv_cache_usage_perc"]

    # Phase 3: 不同项目制造压力
    for i in range(3):
        for t in range(4):  # turn 0-3
            r = await send_and_record(sympy_session[i].turn[t],
                                      max_tokens=500)
    kv_usage = get_prometheus_metrics()["kv_cache_usage_perc"]

    # Phase 4: 测试 L0 是否被驱逐
    r_test = await send_and_record(new_django_session.turn[0])
    l0_block_aligned = 6157 // 16 * 16  # = 6144

    if r_test.cached_tokens < l0_block_aligned:
        print("✅ L0 WAS EVICTED — P2 confirmed!")
    elif r_test.cached_tokens < l0_block_aligned + l1_django_block_aligned:
        print("⚠️ L1 evicted but L0 survived")
    else:
        print("❌ No eviction — need more pressure")
```

### P3-A 脚本核心逻辑（伪代码）

```python
async def run_p3a():
    # Phase 1: 并发启动 3 个长运行请求
    tasks = []
    for i in range(3):
        tasks.append(send_and_record_long(
            django_session[i].turn[0],
            max_tokens=2000,  # 长输出
            label=f"long_req_{i}"))
    # 不等待完成，让它们同时 running

    # Phase 2: 等待 decode 开始后，发送新请求触发抢占
    await asyncio.sleep(1.0)  # 等待 Phase 1 请求进入 decode
    r_pressure = await send_and_record(
        sympy_session[0].turn[0],
        max_tokens=2000,
        label="pressure_req")

    # 等待所有请求完成
    results = await asyncio.gather(*tasks)

    # 检查 preemption
    prom = get_prometheus_metrics()
    num_preemptions = prom.get("num_preemptions", 0)

    if num_preemptions > 0:
        print("✅ PREEMPTION TRIGGERED — P3 confirmed!")
        # 分析被 preempt 请求的恢复 TTFT
    else:
        print("❌ No preemption — need more pressure")
```

### P6-A 脚本核心逻辑（伪代码）

```python
async def run_p6a(config="on"):  # "on" or "off"
    """需要两次独立 server 部署，此脚本只运行一次"""

    # Phase 1: 建立 L0+L1 缓存
    for i in range(3):
        for t in range(6):
            r = await send_and_record(django_session[i].turn[t])

    # Phase 2: 制造驱逐压力
    for i in range(3):
        for t in range(4):
            r = await send_and_record(sympy_session[i].turn[t])

    # Phase 3: 测试 L0 恢复
    r_test = await send_and_record(new_django_session.turn[0])

    # 采集 offload 指标
    prom = get_prometheus_metrics()
    offload_data = {
        "store_bytes": prom.get("kv_offload_store_bytes"),
        "load_bytes": prom.get("kv_offload_load_bytes"),
        "stores_skipped": prom.get("kv_offload_stores_skipped"),
    }

    return {
        "config": config,
        "cached_tokens": r_test.cached_tokens,
        "ttft_ms": r_test.ttft_ms,
        "offload_metrics": offload_data,
    }

# 运行方式：
# 1. KV_OFFLOAD_GIB=8 bash scripts/run_vllm_server.sh
#    python scripts/run_p6a_offload_ab.py --config on
# 2. KV_OFFLOAD_GIB=0 bash scripts/run_vllm_server.sh
#    python scripts/run_p6a_offload_ab.py --config off
# 3. 对比两次结果
```

---

## 7. 预期产出与论文影响

### 证据等级提升预期

| 痛点 | 当前等级 | 补强后等级 | 关键新增数据 |
|------|---------|-----------|------------|
| P2: LRU 驱逐 L0 | [SIMULATED] | **[MEASURED]** | vLLM 实测 L0 驱逐事件 + 恢复 TTFT + LRU vs Aware 对比 |
| P3: Preemption 丢失 decode | [MECHANISM] | **[MEASURED]** | vLLM 实测 preemption 事件 + 恢复 TTFT + 三策略对比 |
| P6: Cache 层级不统一 | [PENDING] | **[MEASURED]** | Offload ON vs OFF A/B 数据 + offload tier 命中率 |

### 论文数字补充

| 指标 | 当前值 | 补强后预期值 | 来源 |
|------|--------|------------|------|
| P2: L0 驱逐后 TTFT | 无 | ~X ms（接近冷启动） | [MEASURED] P2-A |
| P2: Agent-Aware 恢复 TTFT | 无 | ~Y ms（显著低于 LRU） | [MEASURED] P2-B |
| P2: L0/L1/L2 逐层驱逐率 | 无 | L0: Z%, L1: W%, L2: V% | [SIMULATED] P2-C |
| P3: Preemption 恢复 TTFT | 理论 ~1000ms | 实测值 | [MEASURED] P3-A |
| P3: Decode tokens 丢失量 | 理论 5K-15K | 实测值 | [MEASURED] P3-A |
| P3: Swap vs Recompute TTFT | 无 | 实测对比值 | [MEASURED] P3-B |
| P6: Offload ON cached_tokens | 无 | 实测值 | [MEASURED] P6-A |
| P6: Offload OFF cached_tokens | 无 | 实测值 | [MEASURED] P6-A |
| P6: Offload tier load 命中 | 无 | store/load bytes | [MEASURED] P6-B |

### 对优先级矩阵的影响

补强后，P2 和 P3 的证据等级将与 P1 同级（[MEASURED]），P6 从 [PENDING] 提升至 [MEASURED]。预期优先级调整：

| 痛点 | 当前优先级 | 补强后优先级 | 理由 |
|------|-----------|------------|------|
| P1 | CRITICAL | CRITICAL | 不变，已有 [MEASURED] |
| P2 | HIGH | **HIGH→CRITICAL** | [MEASURED] + LRU vs Aware 有明确收益 |
| P3 | HIGH | **HIGH** | [MEASURED] 但解决方案（decode offload）实现复杂度较高 |
| P6 | MEDIUM | **MEDIUM→HIGH** | [MEASURED] + 隐蔽但影响大 + unified hierarchy 方案清晰 |

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 策略 A 仍无法触发驱逐/抢占 | 中 | 高 | 降级到策略 B（gpu_util=0.25）；或策略 C（多 session 多轮并发） |
| P6-A 两次部署结果不可比 | 低 | 中 | 严格控制请求序列一致；每次部署后验证 server 状态 |
| 驱逐/抢占行为不可复现 | 低 | 高 | 每个实验跑 3 次，取中位数；记录完整 Prometheus 时间线 |
| Offload tier 行为与预期不符 | 中 | 中 | 如实记录，调整 P6 论点；P6-C 源码追踪可解释差异 |

---

## 9. 时间预算

| 实验 | 预计时间 | 依赖 |
|------|---------|------|
| P2-A: 触发 L0 驱逐 | 1-2h | 无 |
| P2-B: LRU vs Aware 对比 | 1h | P2-A 成功 |
| P2-C: 模拟器逐层分解 | 1h | 无（可并行） |
| P3-A: 触发 Preemption | 2-3h | P2-A 经验（参数调整） |
| P3-B: 三策略对比 | 1.5h | P3-A 成功 |
| P6-A: Offload A/B 对比 | 1.5h | 无（可并行） |
| P6-B: Offload 命中率 | 1h | P6-A 完成 |
| P6-C: 源码级验证 | 1h | 无（可并行） |
| **总计** | **~10h** | — |

**并行化**：P2-C、P6-A、P6-C 可与 P2-A/P3-A 并行进行，实际墙钟时间约 7-8h。

---

## 10. 验证检查点

| 实验 | 通过标准 | 不通过怎么办 |
|------|---------|------------|
| P2-A | Phase 4 cached_tokens < L0_block_aligned (7,824) | 增加 Phase 2/3 轮次或降低 gpu_util |
| P2-B | 配置 B cached_tokens > 配置 A cached_tokens | 检查 Phase 2.5 的 touch 是否生效 |
| P2-C | L0 驱逐率 > 0% 在 32K 容量下 | 检查模拟器 L0/L1/L2 标记逻辑 |
| P3-A | num_preemptions > 0 | 增加 max_tokens 或并发请求数 |
| P3-B | swap TTFT < recompute TTFT | 检查 offload 配置是否正确 |
| P6-A | offload ON cached_tokens == offload OFF cached_tokens | 分析差异原因，可能部分否定 P6 |
| P6-B | offload store_bytes > 0（ON 配置下） | 检查 offload 是否实际工作 |
| P6-C | 源码追踪确认 load 后不注册到 prefix cache | 如果注册了，P6 论点需调整 |
