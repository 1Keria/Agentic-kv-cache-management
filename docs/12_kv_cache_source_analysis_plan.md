# 四大 Serving 框架 KV Cache 源码分析规划

> 日期：2026-06-12
> 目标：理解 SGLang、vLLM、Mooncake、LMCache 的 KV cache 实现，为 AgentKV 设计提供参考
> 总工作量：~24 小时（4 个 agent 并行分析，墙钟时间 ~6 小时）

---

## 1. 分析维度

### 1.1 KV cache 基本抽象
- cache entry / block / page / token range / prefix node 如何表示？
- **key** 是什么？token ids、hash、prefix tree path、request id、block id？
- **value** 是什么？GPU tensor、CPU tensor、serialized tensor、remote object？
- 引用计数如何工作？谁持有引用？何时释放？

### 1.2 生命周期
- 何时 allocate？prefill 如何写入？decode 如何 append？
- 何时命中复用？命中后如何避免重复计算？
- 何时 evict/free/offload？触发条件是什么？
- request 结束后 cache 是否保留？保留多久？
- cache entry 的引用计数从创建到释放的完整过程

### 1.3 内存层级
- GPU HBM / CPU DRAM / disk SSD / remote memory (RDMA) / distributed store
- 每个项目分别支持哪些层级？层级之间如何迁移？
- offload/onload 的触发条件和实现方式
- 不同层级的容量管理策略

### 1.4 Prefix cache / reuse 机制
- exact prefix match 还是 block hash？匹配算法的时间复杂度？
- 是否支持 partial hit？命中部分如何处理？
- 是否支持非 prefix 复用（如 suffix、中间段）？
- 是否支持跨请求、跨 worker、跨 engine、跨节点复用？
- 复用时的数据拷贝还是指针共享？

### 1.5 调度器与 KV cache 的关系
- scheduler 如何知道 cache 命中？命中信息如何传递？
- cache 命中如何影响 prefill 长度？跳过多少 token？
- cache 命中如何影响 batching 策略？
- KV cache 空间不足时如何影响 admission control / eviction / recompute？
- 是否有 preemption？preemption 时 KV cache 如何处理？

### 1.6 Agent 场景差距
- 每个框架为什么不适合 agent 批量推理？
- 缺少什么能力？（agent-aware 调度、跨 session 保持、组感知驱逐）
- 如果要扩展，需要修改哪些模块？改动量多大？

---

## 2. 分析范围与时间分配

### SGLang（~8h/agent，重点）

| 模块 | 关键文件 | 分析重点 |
|------|---------|---------|
| RadixCache | `python/sglang/srt/mem_cache/radix_cache.py` | TreeNode 结构（字段、引用计数）、prefix 匹配算法（match_prefix）、insert、evict |
| HiCache / Offload | `python/sglang/srt/mem_cache/` | 层级缓存架构、offload backend 实现、CPU/GPU 间迁移 |
| Eviction | `python/sglang/srt/mem_cache/` | LRU 驱逐实现、内部节点（共享 prefix）是否受保护、evict 触发条件 |
| Scheduler | `python/sglang/srt/managers/scheduler.py` | 调度循环（`cache_ready`、`get_new_batch`）、batch 组装逻辑 |
| Schedule Policy | `python/sglang/srt/managers/schedule_policy.py` | LPM / DFS-weight / FCFS 策略的具体实现、优先级计算 |
| Session | `python/sglang/srt/session/` | SessionController、SessionAwareCache、跨 turn KV 持久化机制 |
| KV Memory Pool | `python/sglang/srt/layers/` | GPU 内存分配、token-level 内存管理 |
| HTTP API | `python/sglang/srt/entrypoints/` | session 相关 API 参数、agent_group 扩展点 |

**SGLang 额外分析项**：
- TreeNode 的 `lock_ref`、`last_access_time`、`parent/children` 如何协同工作
- `match_prefix()` 返回值如何被 scheduler 使用
- 跨 turn 复用时 KV cache 是如何"接续"的（不重新 prefill 的机制）
- 现有 session 机制与 agent group 概念的差距

### vLLM（~6h/agent）

| 模块 | 关键文件 | 分析重点 |
|------|---------|---------|
| BlockManager | `vllm/core/block/` | Block 分配、引用计数、block table 结构、BlockTable 管理 |
| PagedAttention | `vllm/attention/` | block-level KV cache 的物理布局、attention kernel 如何使用 block table |
| Prefix Caching (APC) | `vllm/worker/` | block hash 计算、hash 表维护、APC 命中/未命中的处理路径 |
| Scheduler | `vllm/core/scheduler.py` | cache-aware 调度、preemption 逻辑、recompute 策略 |
| KV Cache Config | `vllm/config.py` | `enable_prefix_caching`、`block_size`、`gpu_memory_utilization` 等配置 |
| CacheEngine | `vllm/worker/cache_engine.py` | KV cache 的物理分配和 swap in/out |

**vLLM 额外分析项**：
- Block hash 与 SGLang token-level prefix 匹配的本质区别
- hash collision 的处理
- APC 下 block 的 copy-on-write 机制
- vLLM 的 preemption 如何处理 KV cache（swap vs recompute）

### Mooncake（~6h/agent）

| 模块 | 关键文件 | 分析重点 |
|------|---------|---------|
| Mooncake Store | `mooncake-store/` | prefix 存储接口、object metadata 结构、matching 逻辑 |
| Transfer Engine | `mooncake-transfer-engine/` | KV cache 传输协议、RDMA 实现、segment 管理 |
| Controller | `mooncake-controller/` | 分布式调度、prefill-decode disaggregation 路由 |
| KV Cache Protocol | `mooncake-store/include/` | KV cache object 的序列化格式、传输格式 |

**Mooncake 额外分析项**：
- disaggregated 架构下 KV cache 的定位（在 prefill node 还是 decode node？）
- prefix store 的匹配粒度（token? block? segment?）
- 跨节点 KV cache 传输的延迟模型
- 与 SGLang/vLLM 单节点架构的本质区别

### LMCache（~4h/agent）

| 模块 | 关键文件 | 分析重点 |
|------|---------|---------|
| Cache Engine | `lmcache/` | offloading 逻辑、store/retrieve/lookup 接口 |
| Storage Backend | `lmcache/storage_backend/` | CPU adapter、disk adapter、remote adapter 的实现 |
| Connector | `lmcache/connector/` | vLLM adapter、SGLang adapter 的集成方式 |
| Cache Key | `lmcache/` | cache key 生成逻辑（fmt、hash）、prefix 匹配支持 |

**LMCache 额外分析项**：
- offloading 粒度（整个 sequence vs prefix block）
- 与 vLLM BlockManager 的交互方式（hook 还是替换？）
- 跨实例 cache 复用的完整路径（lookup → retrieve → load → use）
- LMCache 作为外部 KV 存储层 vs SGLang 内部 RadixCache 的定位差异

---

## 3. 产出物

### 3.1 关键文件索引 `docs/13_kv_cache_file_index.md`

每个框架列出关键源码文件、类/函数、作用：

```
| 文件 | 关键类/函数 | 作用 | 为什么相关 |
```

### 3.2 各框架详细分析 `notes/`

四个独立 notes 文件，作为原始分析记录永久保留：

- `notes/sglang_kv_cache.md`
- `notes/vllm_kv_cache.md`
- `notes/mooncake_kv_cache.md`
- `notes/lmcache_kv_cache.md`

每个 note 包含：
1. **数据结构** — 核心类的字段定义和含义
2. **核心流程追踪** — 关键函数的调用链和逻辑
3. **关键源码片段** — 带行号的代码摘录
4. **尚未确认的问题** — 标注不确定项和需要进一步查看的文件

### 3.3 完整分析报告 `docs/14_kv_cache_source_analysis.md`

从 notes 提炼，包含：

1. **每个框架的 KV cache 架构概述** — 核心数据结构 + 关键流程
2. **生命周期对比** — allocate → write → reuse → evict
3. **内存层级对比** — 每个框架支持的层级和迁移方式
4. **Prefix reuse 机制对比** — 匹配算法、共享粒度、复用路径
5. **调度器与 KV cache 关系对比**
6. **横向对比表**：

| 维度 | SGLang | vLLM | Mooncake | LMCache |
|------|--------|------|----------|---------|
| 核心设计 | | | | |
| 管理粒度 | | | | |
| cache key | | | | |
| cache value | | | | |
| 内存层级 | | | | |
| eviction 策略 | | | | |
| 跨请求复用 | | | | |
| 跨节点复用 | | | | |
| 引用计数机制 | | | | |
| preemption 策略 | | | | |
| 主要优点 | | | | |
| 主要限制 | | | | |

7. **两个 Mermaid 图**：
   - 单请求 prefill/decode 下 KV cache 写入与读取流程
   - 四个项目的 KV cache 架构对比图

8. **Agent 场景差距分析**：
   - 每个框架在 agent 批量推理场景下的具体不足
   - 扩展为 agent-aware 所需的改动量和改动点

9. **设计启示**：
   - 自研 KV cache manager 应分别借鉴什么
   - SGLang/vLLM（engine 内部 KV 管理）与 Mooncake/LMCache（外部 KV 存储/传输层）的边界
   - AgentKV 应该站在哪一层，如何组合这四个系统的优势

---

## 4. 分析方法

- **数据结构优先**：先理解核心类（TreeNode、Block、PrefixStore），再追踪流程
- **关键路径追踪**：跟随一个请求从 API → 调度 → prefill → prefix match → decode
- **ripgrep 搜索关键词**：`kv_cache, kvcache, prefix, radix, block_manager, paged, cache_engine, eviction, offload, connector, transfer, store, prefill, decode`
- **每个结论带源码路径依据**（文件:行号）
- **不确定的地方标注"不确定"**，并说明还需看哪些文件
- 只关注 Python/C++ 逻辑层，不读 CUDA kernel
- 纯源码阅读，不运行框架

---

## 5. 工作流程

1. **产出文件索引**（`13_kv_cache_file_index.md`）— ripgrep 搜索 + 定位关键文件
2. **并行分析四个框架**（4 个 agent 同时进行）：
   - Agent 1: SGLang → `notes/sglang_kv_cache.md`
   - Agent 2: vLLM → `notes/vllm_kv_cache.md`
   - Agent 3: Mooncake → `notes/mooncake_kv_cache.md`
   - Agent 4: LMCache → `notes/lmcache_kv_cache.md`
3. **汇总**：基于四个 notes，产出横向对比 + Mermaid 图 + 设计启示 → `docs/14_kv_cache_source_analysis.md`

---

## 参考

- `docs/04_agent_framework_comparison.md` — 初步对比
- `docs/11_precise_lcp_calculation.md` — LCP 数据
- `docs/ref.md` — 参考分析框架
