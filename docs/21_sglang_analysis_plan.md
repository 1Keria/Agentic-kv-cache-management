# SGLang KV Cache 系统性分析规划

> 日期: 2026-06-25
> 状态: 计划（未执行）
> 目标: 对 SGLang KV Cache 机制进行与 vLLM 同等深度的系统性分析，量化每个 Agent 痛点在 SGLang 中的表现，形成 vLLM vs SGLang 的完整对比
> ⚠️ 原则：不修改 SGLang 源码，所有实验使用已部署的 SGLang server

---

## 0. 实验环境

### Python 环境

vLLM 和 SGLang 共用同一个 Conda 环境：

| 项目 | 值 |
|------|-----|
| Conda env | `agentkv_zls` (`/share/dai-sys/apps/anaconda3/envs/agentkv_zls`) |
| Python | 3.11.15 |
| vLLM | 0.8.5.dev0 (editable install, `Engine/vllm`) |
| SGLang | 0.0.0.dev1+g880e6f66f (editable install, `Engine/sglang`) |
| PyTorch | 2.11.0+cu130 |
| 模型 | Qwen3-8B (`/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/`) |

### SGLang Server 启动方式

**⚠️ 重要**：SGLang 不能用 `python -m sglang.launch_server` 启动（会触发 CUDA Error 803），必须用 `python -c` 方式启动：

```bash
export CUDA_VISIBLE_DEVICES=0
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache   # 避免 ~/.cache/tvm-ffi 权限问题

/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python -c "
import sys
sys.argv = ['sglang',
    '--model-path', '/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/',
    '--port', '8001',
    '--mem-fraction-static', '0.3',
    '--schedule-policy', 'lpm',
    '--enable-metrics',
    '--enable-cache-report',
    # 其他参数...
]

from sglang.srt.plugins import load_plugins
load_plugins()

from sglang.srt.server_args import prepare_server_args
server_args = prepare_server_args(sys.argv[1:])

from sglang.srt.entrypoints.http_server import launch_server
launch_server(server_args)
"
```

### SGLang 关键参数（已验证）

| 参数 | 默认值 | 实验推荐值 | 说明 |
|------|--------|-----------|------|
| `--mem-fraction-static` | 0.88 | 0.3 | 对齐 vLLM gpu_util=0.3 |
| `--schedule-policy` | fcfs | lpm | Cache-aware 调度 |
| `--enable-metrics` | False | **True** | 启用 Prometheus /metrics |
| `--enable-cache-report` | False | **True** | API 返回 cached_tokens |
| `--page-size` | 1 | 1 | Token-level 匹配（SGLang 默认） |
| `--disable-radix-cache` | False | False | 保持 radix cache 启用 |

### SGLang 已验证可用的指标

**OpenAI API**：
- `usage.prompt_tokens_details.cached_tokens`：✅ 可用（需 `--enable-cache-report`）
- Request 2 的 `cached_tokens=509/521` 证实 prefix cache 工作

**Prometheus (`http://localhost:8001/metrics`，需 `--enable-metrics`)**：
- `sglang:cached_tokens_total{cache_source="device"}`：GPU 端 cache 命中 token 数
- `sglang:max_total_num_tokens`：KV cache 总容量（mem-fraction=0.3 时 = 59,902 tokens）
- `sglang:page_size`：= 1（token-level）
- `sglang:num_pages`：= 59,902
- `sglang:num_running_reqs` / `num_queue_reqs`：运行/排队请求数
- `sglang:prompt_tokens_total` / `generation_tokens_total`：总 token 数

**SGLang vs vLLM 容量对比**：

| 参数 | vLLM (gpu_util=0.3) | SGLang (mem-fraction=0.3) |
|------|---------------------|--------------------------|
| KV 容量 | ~44,000 tokens | ~59,902 tokens |
| 管理粒度 | Block (16 tokens) | Token (page_size=1) |
| 可用 pages/blocks | ~2,750 blocks | 59,902 pages |

**注意**：SGLang 的 KV 容量（59,902 tokens）大于 vLLM（44,000 tokens），因为两者对 `mem-fraction-static` 的计算方式不同。SGLang 的 0.3 可能对应更多实际 KV cache 空间。实验设计时需要考虑这个差异。

### SGLang 启动耗时

SGLang server 启动约需要 **115-145 秒**（含模型加载、JIT 编译），比 vLLM 略长。

## 0. 为什么要做 SGLang 分析

### 已有基础

| 资源 | 内容 | 不足 |
|------|------|------|
| `notes/sglang_kv_cache.md` | 完整的 SGLang 源码分析笔记 | 偏描述性，缺 Agent 场景量化 |
| `docs/14_kv_cache_source_analysis.md` | 四框架对比报告 | 高层架构对比，未深入 Agent 痛点 |
| vLLM investigation 报告 | P1-P7 痛点量化 + 机制解释 | 仅 vLLM 视角 |
| C++ 模拟器 | block_size=16/64 容量扫描 | 仅模拟，未实测 SGLang |

### 核心目标

1. **对 SGLang 做与 vLLM 完全等价的痛点分析**：用相同的 LMCache Agentic Traces，在 SGLang 上复现 P1-P7 的量化实验
2. **形成 vLLM vs SGLang 的逐痛点对比表**：每个痛点在两个系统中的表现、根因差异、谁更优
3. **识别 SGLang 特有的 Agent 痛点**：SGLang 的架构优势（token-level 匹配、HiCache、LPM 调度）是否真正解决了 vLLM 的问题，还是引入了新问题
4. **为论文提供对比数据**：论文的 contribution 需要展示"现有最佳系统（SGLang）在 Agent 场景下仍有 X% 的不足"

---

## 1. vLLM vs SGLang 架构差异速览

### 1.1 核心设计对比

| 维度 | vLLM | SGLang | Agent 影响 |
|------|------|--------|-----------|
| **缓存数据结构** | Block Hash Table（`cached_block_hash_to_block`） | Radix Tree（`TreeNode` + `RadixKey`） | SGLang 结构寻址 vs vLLM 内容寻址 |
| **匹配粒度** | Block-level（16 tokens） | Token-level | SGLang 无 partial block 浪费 |
| **Key 计算** | 链式 SHA-256：`H(parent, tokens_i)` | Tree path：token ID 序列 | vLLM hash 有碰撞风险（极低）；SGLang 无碰撞 |
| **部分命中** | ❌ 不支持（只匹配完整 block） | ✅ 支持（节点分裂） | Agent prompt 不对齐 block_size 时 vLL 有损 |
| **并发共享** | 调度步内无法跨请求注册 | `match_prefix` 在调度前执行 | SGLang 是否有同样的并发问题？ |
| **驱逐策略** | LRU Free Queue（单一） | Min-heap + 可插拔（LRU/LFU/FIFO/MRU/Priority/SLRU） | SGLang 策略更丰富 |
| **Preemption** | `num_computed_tokens=0`，完全重算 | Retract + radix tree 恢复，部分保留 | SGLang 恢复更优 |
| **Offloading** | CPUOffloadingManager（独立于 prefix cache） | HiRadixCache（统一 radix tree 管理） | SGLang 层级统一 |
| **调度策略** | FCFS / PRIORITY | LPM / DFS-weight / FCFS / LOF / RANDOM | SGLang 有 cache-aware 调度 |
| **Session 机制** | ❌ 无 | ✅ SessionController + StreamingSession | SGLang 支持跨 turn 零 prefill |
| **Block size** | 16（默认） | 64（默认 page_size） | SGLang 单页更大但 token-level 匹配消除了浪费 |

### 1.2 关键架构差异的深层含义

#### 差异 1：结构寻址 vs 内容寻址

**vLLM（内容寻址）**：
- Block hash = `H(parent_hash, block_token_ids, extra_keys)`
- 相同 token 内容 → 相同 hash → 可以命中
- 但只能匹配完整 block（16 tokens 对齐）
- Agent 影响：L0=6,157 tokens，最后 9 个 token 无法被缓存（6,157 % 16 = 9）

**SGLang（结构寻址）**：
- Tree path = token ID 序列
- 匹配在任意 token 位置可以分裂节点
- 不依赖 hash，直接比较 token IDs
- Agent 影响：可以精确匹配到 L0 的 6,157 个 token，无浪费

#### 差异 2：并发请求的 prefix 注册时机

**vLLM**：
- `allocate_slots()` 期间注册 blocks 到 hash table
- 同一步调度的请求看不到彼此的 blocks
- → P1：并发 L1 命中率 = 0%

**SGLang**：
- `match_prefix_for_req()` 在 `calc_priority()` 中调用
- `calc_priority()` 对 waiting queue 中**所有请求**逐一调用
- 第一个请求 `match_prefix` 后，其 KV 是否立即可被后续请求命中？
- **关键问题**：`match_prefix` 只读取 radix tree，不写入。新 token 的 KV 在 prefill 完成后才通过 `insert()` 写入 radix tree。
- 因此 SGLang **也可能有同样的并发问题**：同一批调度中的请求，第一个请求 prefill 的结果不会被后续请求看到。

#### 差异 3：Preemption/Retraction 的恢复

**vLLM**：
- `_preempt_request()` 设 `num_computed_tokens=0`
- 所有 blocks 立即释放，decode blocks 因 `offload_prompt_only=True` 永久丢失
- 恢复 = 完全重算（除非 prefix cache 还有部分 blocks）

**SGLang**：
- `retract_decode()` 调用 `release_req()` → `release_kv_cache(req, tree_cache, is_insert=False)`
- `is_insert=False`：**不**将请求的 KV 插入 radix tree
- 但 radix tree 中已有的共享 prefix 节点仍然保留（因为它们是树中的独立节点）
- 请求重新调度时，`match_prefix_for_req()` 会命中 radix tree 中的共享 prefix
- **关键区别**：SGLang 的 radix tree 保留了 L0/L1 等共享 prefix，只丢失被 retract 请求独有的 decode 部分
- 但 `is_insert=False` 意味着 decode 输出的 KV **不被插入树中**，与 vLLM 一样丢失

#### 差异 4：Cache 层级统一性

**vLLM**：
- GPU prefix cache（`BlockPool.cached_block_hash_to_block`）和 CPU offload tier（`CPUOffloadingManager`）有独立 hash table
- `find_longest_cache_hit()` 不检查 offload tier
- → P6：offload ON vs OFF 的 cached_tokens 相同

**SGLang**：
- HiRadixCache 统一管理 GPU（`node.value`）和 CPU（`node.host_value`）
- 同一个 TreeNode 同时持有 `value`（GPU 索引）和 `host_value`（CPU 索引）
- `match_prefix` 遍历 radix tree 时，evicted 节点仍然存在于树中（`value=None` 但 `host_value` 有值）
- `load_back` 从 CPU 恢复到 GPU
- **SGLang 不存在 P6 问题**：层级是统一的

---

## 2. 分析计划：按 vLLM 痛点逐一对标

### 痛点映射表

| vLLM 痛点 | SGLang 对应机制 | 预期是否存在 | 分析方式 |
|-----------|----------------|------------|---------|
| P1: 并发共享失效 | `match_prefix` 批内注册时机 | **可能存在**（需验证） | 实测 + 源码追踪 |
| P2: LRU 驱逐 L0 | radix tree LRU 驱逐 | **可能存在但更可控** | 实测 + 模拟 |
| P3: Preemption 丢失 decode | retract + `is_insert=False` | **存在但恢复更优** | 实测 + 源码分析 |
| P4: Prefix 增长压力 | token pool 容量限制 | **存在**（同源 trace） | Trace 分析（与 vLLM 共享数据） |
| P5: Block 浪费 | token-level 匹配 | **不存在** | 理论分析 |
| P6: Cache 层级不统一 | HiRadixCache 统一管理 | **不存在** | 源码确认 |
| P7: 无调度感知 | LPM / DFS-weight | **部分解决** | 实测 + 对比 |

---

## 3. Phase 0：SGLang 实验基础设施搭建

### 3.1 SGLang Server 部署

**目标**：建立与 vLLM 对等的 SGLang 实验环境。

**硬件**：同 vLLM（8× H800, Qwen3-8B）

**部署脚本**：`scripts/run_sglang_server.sh`（新建）

```bash
#!/bin/bash
# 启动 SGLang server 用于 KV cache 实验
#
# ⚠️ 不能用 python -m sglang.launch_server（CUDA Error 803）
# 必须用 python -c 方式启动，先初始化 CUDA 再导入 SGLang
#
# 关键参数说明：
#   --enable-metrics              启用 Prometheus /metrics 端点
#   --enable-cache-report         API 返回 cached_tokens 字段
#   --schedule-policy lpm         使用 LPM（Longest Prefix Match）调度
#   --mem-fraction-static 0.3    对齐 vLLM gpu_util=0.3

export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
export TVM_FFI_CACHE_DIR=/tmp/tvm_ffi_cache
mkdir -p $TVM_FFI_CACHE_DIR

PYTHON=/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python
MODEL_PATH="/share/dai-sys/.cache/hub/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/"
MEM_FRACTION=${1:-0.3}
PORT=${2:-8001}
SCHEDULE=${3:-lpm}

echo "Starting SGLang server..."
echo "  Model: Qwen3-8B"
echo "  Mem fraction: $MEM_FRACTION"
echo "  Port: $PORT"
echo "  Schedule: $SCHEDULE"
echo "  Metrics: ON"
echo "  Cache report: ON"

$PYTHON -c "
import sys
sys.argv = ['sglang',
    '--model-path', '$MODEL_PATH',
    '--port', '$PORT',
    '--mem-fraction-static', '$MEM_FRACTION',
    '--schedule-policy', '$SCHEDULE',
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

**关键配置对比**：

| 参数 | vLLM | SGLang | 对齐说明 |
|------|------|--------|---------|
| GPU 内存比例 | `gpu_util=0.3` → ~44K tokens | `--mem-fraction-static 0.3` → ~60K tokens | ⚠️ SGLang 容量更大！实验需注意 |
| Prefix cache | `--enable-prefix-caching` | 默认启用 radix cache | SGLang 默认启用 |
| CPU offload | `KV_OFFLOAD_GIB=8` | `--hicache-ratio 2.0` | 需计算等效值 |
| 调度策略 | FCFS（默认） | LPM（实验推荐） | 各用默认值做基线，然后切换对比 |
| Block/page size | 16 | 1（token-level） | 架构差异，无法对齐 |
| Metrics | 默认启用 | 需 `--enable-metrics` | ⚠️ SGLang 需显式启用 |
| cached_tokens | `--enable-prompt-tokens-details` | `--enable-cache-report` | 不同参数名 |
| 模型 | Qwen3-8B | Qwen3-8B | 对齐 |

**验证**：
```bash
# 1. Server 就绪检查（启动约 115-145 秒）
python -c "import openai; c=openai.Client(base_url='http://localhost:8001/v1'); c.models.list()"

# 2. Prefix cache 功能验证
# 发送同一 system prompt 的两个请求，第二个应有 cached_tokens > 0
```

### 3.2 SGLang 实验工具函数

**新建**：`scripts/sglang_exp_utils.py`

基于 `exp_utils.py` 改写，适配 SGLang 的 API 差异：

| 功能 | vLLM (`exp_utils.py`) | SGLang 适配 |
|------|----------------------|------------|
| `send_and_record()` | OpenAI API `stream=True` + `usage` | 基本相同，但 SGLang 的 `cached_tokens` 采集方式可能不同 |
| `get_prometheus_metrics()` | `http://localhost:8000/metrics` | `http://localhost:8001/metrics`，指标名可能不同 |
| `KVTimelineCollector` | 采集 `kv_cache_usage_perc` | SGLang 对应指标待确认 |
| `make_layered_messages()` | L0/L1/L2 分层 prompt | 复用，API 兼容 |

**关键问题：SGLang 是否暴露 `cached_tokens` 和 `kv_cache_usage_perc`？**

需要确认：
1. SGLang OpenAI API 的 `usage.prompt_tokens_details.cached_tokens` 是否可用
2. SGLang Prometheus 指标中是否有等效的 cache hit rate 指标
3. 如果没有，需要从 SGLang server log 中解析

### 3.3 SGLang Prometheus 指标（已实测确认）

**实测结果**（`--enable-metrics`，`--enable-cache-report`）：

| 指标 | 类型 | 说明 |
|------|------|------|
| `sglang:cached_tokens_total{cache_source="device"}` | counter | GPU 端 cache 命中 token 数 |
| `sglang:cached_tokens_total{cache_source="host"}` | counter | CPU 端 cache 命中 token 数（HiCache） |
| `sglang:max_total_num_tokens` | gauge | KV cache 总容量（tokens） |
| `sglang:num_pages` | gauge | KV cache 总页数 |
| `sglang:page_size` | gauge | 页大小（默认 1 = token-level） |
| `sglang:num_running_reqs` | gauge | 运行中请求数 |
| `sglang:num_queue_reqs` | gauge | 排队请求数 |
| `sglang:prompt_tokens_total` | counter | 总 prompt token 数 |
| `sglang:generation_tokens_total` | counter | 总生成 token 数 |

**与 vLLM 指标对比**：

| 需求 | vLLM 指标 | SGLang 指标 |
|------|----------|------------|
| KV cache 使用率 | `kv_cache_usage_perc` | ❌ 无直接对应（需从 `num_running_reqs` 和 `max_total_num_tokens` 推算） |
| Cache 命中 | `prefix_cache_hits` / `prefix_cache_queries` | `sglang:cached_tokens_total` |
| Preemption 次数 | `num_preemptions` | ❌ 需从 server log 解析 retraction 事件 |
| Offload store/load | `kv_offload_store_bytes` / `kv_offload_load_bytes` | `sglang:cached_tokens_total{cache_source="host"}`（间接） |

**缺失指标**：
- **KV cache 使用率**：SGLang 不直接暴露百分比，需从运行请求的 KV 占用和总容量推算
- **Preemption/Retraction 次数**：需从 server log 中解析，或通过 TTFT 异常跳变间接推断

---

## 4. Phase 1：SGLang Prefix Cache 基本行为验证

### 实验 S1：单 Session 多轮串行回放

**目标**：验证 SGLang 的 radix cache 在串行模式下是否能正确缓存和复用 prefix。

**与 vLLM 对标**：对应 vLLM 的 Phase 1B（单 session 多轮回放）。

**步骤**：
1. 部署 SGLang server（mem-fraction=0.3, prefix-caching enabled）
2. 从 LMCache trace 选 1 个长 session（30+ 轮），逐轮串行发送
3. 每轮记录：`cached_tokens`（或等效指标）、TTFT、KV cache 使用率
4. 绘制 SGLang 的 KV 占用增长曲线

**验证标准**：
- 串行模式下命中率应接近 100%（SGLang token-level 匹配应优于 vLLM block-level）
- `cached_tokens` 应精确等于前轮 total_tokens（无 block 对齐浪费）

**vLLM 对比预期**：

| 指标 | vLLM | SGLang | 差异原因 |
|------|------|--------|---------|
| 串行命中率 | 99.9% | ~100% | SGLang token-level 无浪费 |
| cached_tokens 精度 | floor(prev/16)*16 | = prev（精确） | block vs token 粒度 |
| Block 对齐浪费 | 0-15 tokens/turn | 0 | SGLang 无此问题 |

### 实验 S2：并发请求 Prefix 共享

**目标**：验证 SGLang 在并发请求场景下是否也有 P1 问题。

**与 vLLM 对标**：对应 vLLM P1 实验（并发 vs 串行 L1 命中率对比）。

**步骤**：
1. 部署 SGLang server
2. 并发发送 3 个 django session 首轮请求 → 记录 cached_tokens
3. 重新部署 SGLang server
4. 串行发送同样 3 个请求 → 记录 cached_tokens
5. 对比：并发 vs 串行

**关键问题**：

SGLang 的调度流程是：
```
calc_priority() → 对每个请求调用 match_prefix_for_req()
  → tree_cache.match_prefix()  ← 只读，不写入
→ PrefillAdder.add_one_req()
  → alloc_for_extend() → prefill → 新 KV 写入
→ cache_finished_req() / insert()  ← 写入 radix tree
```

在 `calc_priority()` 阶段，所有请求都只是**读取** radix tree。第一个请求 prefill 产生的 KV 不会在第二个请求的 `match_prefix` 之前插入树中。因此：

**预期**：SGLang 也有并发 L1 命中率 = 0% 的问题。但 SGLang 有 `in-batch prefix caching` 机制（`schedule_policy.py:247-293`），可能部分缓解。

**需要验证的 in-batch prefix caching**：
- `waiting_queue_radix_tree` 是否在同批请求间共享？
- 阈值 `IN_BATCH_PREFIX_CACHING_CHECK_THRESHOLD=32` 是否影响 Agent 场景（L1 = 2,700-4,300 tokens >> 32）？
- 如果 prefix > 32 tokens，in-batch caching 是否被跳过？

**vLLM 对比预期**：

| 指标 | vLLM | SGLang | 说明 |
|------|------|--------|------|
| 并发 L1 命中率 | 0% | 0%（如果 in-batch 不生效） | 同根因：调度步内无跨请求注册 |
| 并发 L0 命中率 | 79.7%-86.3% | ~100%（token-level） | SGLang 无 block 浪费 |
| In-batch 缓解 | 无 | 可能有（需验证） | SGLang 特有机制 |

### 实验 S3：In-Batch Prefix Caching 深度验证

**目标**：定量测试 SGLang 的 in-batch prefix caching 对 Agent 场景的实际效果。

**步骤**：
1. 部署 SGLang server
2. 并发发送 3 个 django session 首轮请求，记录 cached_tokens
3. 检查 SGLang server log 中的 in-batch prefix caching 事件
4. 对比不同 L1 长度下的 in-batch 效果

**变量**：
- L1 长度：500, 1000, 2000, 4000 tokens
- 并发数：2, 3, 5, 9

**预期**：
- L1 < 32 tokens：in-batch caching 生效，后续请求可命中
- L1 > 32 tokens：in-batch caching 被跳过（超过 `DEPRIORITIZE_THRESHOLD`），回到 0% 命中
- Agent 场景 L1 通常 2,700-4,300 tokens → in-batch caching **大概率不生效**

---

## 5. Phase 2：SGLang 驱逐与 Retraction 行为分析

### 实验 S4：触发 L0 驱逐

**目标**：在 SGLang 中制造真实的内存压力，观察 L0 节点是否被 LRU 驱逐。

**与 vLLM 对标**：对应 P2-A（触发 L0 驱逐）。

**步骤**：
1. 部署 SGLang server（mem-fraction=0.3）
2. Phase 1: 串行发送 3 个 django session turn 0-5（建立 L0+L1 缓存）
3. Phase 2: 串行发送 3 个 sympy session turn 0-3（制造压力）
4. Phase 3: 发送新 django session turn 0 → 记录 cached_tokens

**SGLang 驱逐机制差异**：
- vLLM：free queue 头部驱逐，LRU 顺序
- SGLang：min-heap + eviction strategy，叶子节点优先驱逐
- SGLang 的 radix tree 结构使得 L0 是根节点的直接子节点，lock_ref=0 后是叶子还是非叶子？

**关键分析**：在 SGLang 的 radix tree 中，L0 节点的位置：
- L0 是根节点的子节点（6,157 tokens）
- L0 有多个子节点（各项目的 L1）
- L0 的 `lock_ref`：当有请求使用 L0 时 > 0；当所有请求完成后 = 0
- **当 lock_ref=0 且 L0 有子节点时，L0 不是叶子节点，不会被直接驱逐**
- SGLang 只驱逐**叶子节点**（`evictable_leaves`）

**预期**：
- SGLang 的 L0 不容易被驱逐（因为它是中间节点，不是叶子）
- 但 L1 节点可能是叶子，会被优先驱逐
- L1 被驱逐后，如果 L0 的子节点全部被驱逐，L0 本身变成叶子，然后也可能被驱逐

**vLLM 对比**：

| 指标 | vLLM | SGLang | 说明 |
|------|------|--------|------|
| L0 驱逐难度 | 较易（free queue 头部） | 较难（非叶子节点，需先驱逐所有子节点） | SGLang 树结构天然保护中间节点 |
| L1 驱逐难度 | 与 L0 相同 | 较易（L1 通常是叶子） | |
| LRU-Optimal gap | 6.9% @ 44K | 预计更小 | SGLang 树结构减少高价值节点驱逐 |

### 实验 S5：驱逐策略对比（LRU vs Priority vs SLRU）

**目标**：测试 SGLang 不同驱逐策略对 Agent 场景的影响。

**SGLang 支持的驱逐策略**：

| 策略 | 优先级计算 | 预期 Agent 表现 |
|------|-----------|----------------|
| LRU | `last_access_time` | 同 vLLM，可能驱逐高价值 L0 |
| LFU | `hit_count` | L0 hit_count 高，不易被驱逐 |
| Priority | `(priority, last_access_time)` | 可手动设置 L0 高优先级 |
| SLRU | protected segment by `hit_count` | L0 高 hit_count 进入 protected segment |

**步骤**：
1. 分别用 LRU、Priority、SLRU 策略部署 SGLang server
2. 重复 S4 的压力场景
3. 对比不同策略下 Phase 3 的 cached_tokens 和 TTFT

**vLLM 对比**：
- vLLM 只有 LRU，无法选择其他策略
- SGLang 的 Priority 和 SLRU 策略可能天然缓解 P2 问题

### 实验 S6：Retraction 恢复行为

**目标**：触发 SGLang 的 retract_decode，测量恢复 TTFT。

**与 vLLM 对标**：对应 P3-A（触发 Preemption）。

**步骤**：
1. 部署 SGLang server（mem-fraction=0.3）
2. Phase 1: 发送 3 个长运行请求（max_tokens=2000）
3. Phase 2: 发送新请求触发 retraction
4. 记录 retracted 请求的恢复 TTFT
5. 对比：首次 TTFT vs 恢复 TTFT

**SGLang Retraction vs vLLM Preemption 关键差异**：

| 维度 | vLLM Preemption | SGLang Retraction |
|------|----------------|-------------------|
| 触发条件 | 新请求无法分配 blocks | decode 内存不足 |
| KV 处理 | 全部释放，`num_computed_tokens=0` | `release_kv_cache(is_insert=False)`，不插入树 |
| 共享 prefix | 随 blocks 一起释放，可能被驱逐 | radix tree 中共享 prefix 节点**保留** |
| 恢复方式 | 依赖 prefix cache 残留 + 完全重算 | `match_prefix` 命中 radix tree + 重算缺失部分 |
| Decode 输出 | 永久丢失（offload_prompt_only=True） | 永久丢失（is_insert=False，不插入树） |
| 恢复 TTFT | 接近冷启动 | **预期更低**（prefix 可恢复） |

**预期**：
- SGLang retraction 的恢复 TTFT 显著低于 vLLM preemption
- 因为 radix tree 保留了 L0/L1 共享 prefix，只需重算 decode 输出
- 但 decode 输出仍然丢失（与 vLLM 相同的痛点）

**vLLM 对比预期**：

| 指标 | vLLM Preemption | SGLang Retraction |
|------|----------------|-------------------|
| 恢复 TTFT | ~1000ms+（接近冷启动） | ~200-400ms（只需重算 decode 部分） |
| Prefix 恢复 | 取决于 cache 残留 | L0+L1 从 radix tree 恢复 |
| Decode 恢复 | ❌ 丢失 | ❌ 丢失 |
| 丢失去重算量 | 全部（5K-15K tokens） | 仅 decode 部分（5K-15K tokens），但 prefix 免重算 |

---

## 6. Phase 3：SGLang 特有机制深度分析

### 实验 S7：HiCache 层级统一性验证

**目标**：验证 SGLang 的 HiRadixCache 是否真正解决了 P6（Cache 层级不统一）。

**与 vLLM 对标**：对应 P6-A（Offload ON vs OFF A/B 对比）。

**步骤**：
1. 部署 SGLang server（hicache-ratio=0.2，启用 HiCache）
2. 制造驱逐场景（同 S4）
3. Phase 3: 发送新请求 → 记录 cached_tokens
4. 观察 `host_hit_length > 0`（CPU 层命中）
5. 确认 `load_back` 被触发（从 CPU 恢复到 GPU）

**预期**：
- SGLang 中 evicted 节点仍存在于 radix tree（`value=None, host_value≠None`）
- `match_prefix` 遍历树时发现 evicted 节点，记录 `host_hit_length`
- `PrefillAdder` 调用 `init_load_back` 从 CPU 恢复
- **cached_tokens 应包含 load_back 恢复的部分**

**vLLM 对比**：

| 指标 | vLLM (Offload ON) | SGLang (HiCache ON) |
|------|-------------------|---------------------|
| 驱逐后 cached_tokens | = Offload OFF（无差异） | > HiCache OFF（CPU 恢复） |
| GPU→CPU 一致性 | 独立 hash table | 同一 TreeNode |
| Load-back 路径 | KV connector（独立路径） | radix tree match → load_back（统一路径） |
| 是否存在 P6 | ✅ 存在 | ❌ 不存在 |

### 实验 S8：LPM vs DFS-weight vs FCFS 调度对比

**目标**：定量对比 SGLang 不同调度策略在混合 Agent 负载下的 prefix 复用效果。

**与 vLLM 对标**：对应 P7（无调度感知）。

**步骤**：
1. 分别用 FCFS、LPM、DFS-weight 部署 SGLang server
2. 发送混合项目负载：3 django + 2 sympy 首轮请求（并发）
3. 记录每种策略的总 cached_tokens 和 TTFT

**预期**：

| 策略 | 总 cached_tokens | 说明 |
|------|-----------------|------|
| FCFS | 较低 | 无 cache 感知，与 vLLM 类似 |
| LPM | 较高 | 命中多的先调度，但可能饥饿 |
| DFS-weight | 最高 | 同 prefix 请求聚合，最大化共享 |

**vLLM 对比**：

| 指标 | vLLM FCFS | SGLang FCFS | SGLang LPM | SGLang DFS |
|------|-----------|------------|------------|------------|
| 调度 gap | 2,384 tokens | ? | ? | ? |
| 是否可配置 | ❌ | ✅ | ✅ | ✅ |
| Agent-aware | ❌ | ❌ | 部分 | 部分 |

**注意**：SGLang 的 LPM 在 `len(waiting_queue) > 128` 时降级为 FCFS。Agent 场景下并发请求数通常 < 128，LPM 应能正常工作。

### 实验 S9：StreamingSession 跨 Turn 零 Prefill 验证

**目标**：验证 SGLang 的 StreamingSession 是否真正实现跨 turn 零 prefill。

**这是 vLLM 完全没有的功能**。

**步骤**：
1. 部署 SGLang server
2. 使用 Session API 创建 streaming session
3. 逐轮发送同一 session 的消息
4. 记录每轮的 prefill token 数和 TTFT
5. 对比：使用 Session vs 不使用 Session

**预期**：
- 使用 StreamingSession：每轮 TTFT ≈ decode 延迟（几 ms），无 prefill
- 不使用 Session：每轮 TTFT 包含 prefix prefill 时间
- **差距是数量级的**：StreamingSession 消除了多轮对话的 prefill 开销

**vLLM 对比**：

| 指标 | vLLM（无 Session） | SGLang（无 Session） | SGLang（StreamingSession） |
|------|-------------------|---------------------|--------------------------|
| Turn 0 TTFT | ~300ms | ~300ms | ~300ms |
| Turn 5 TTFT | ~500ms（prefix 增长） | ~500ms | **~5ms**（零 prefill） |
| Turn 10 TTFT | ~1000ms | ~1000ms | **~5ms** |

**但 StreamingSession 有代价**：
- 持续占用 GPU 内存（KV tensor 不释放）
- Session 期间 `lock_ref > 0`，相关节点不被驱逐
- 在内存紧张时，多个活跃 StreamingSession 可能阻止驱逐，导致 OOM

### 实验 S10：StreamingSession 内存代价量化

**目标**：量化 StreamingSession 在内存压力下的代价。

**步骤**：
1. 部署 SGLang server（mem-fraction=0.3）
2. 同时打开 N 个 StreamingSession（N=1,3,5,10）
3. 各 session 运行到 turn 10
4. 记录 KV cache 使用率
5. 发送新请求，观察是否触发 retraction
6. 确认 StreamingSession 的 KV 是否受 retraction 保护

**预期**：
- StreamingSession 的 `lock_ref > 0`，KV 不会被驱逐
- 但这也意味着其他请求可能因内存不足被 retract
- N 个 session × ~20K tokens/session = N×20K tokens 被锁定
- 当 N×20K > 44K × 0.8 时，新请求几乎无法调度

---

## 7. Phase 4：SGLang 特有的 Agent 痛点

### 痛点 SP1：In-Batch Prefix Caching 阈值过高

**机制**：`IN_BATCH_PREFIX_CACHING_CHECK_THRESHOLD=32` tokens
**Agent 影响**：Agent 的 L1 prefix 通常 2,700-4,300 tokens，远超阈值
**结果**：in-batch prefix caching 被跳过，并发请求间无法共享 L1

**量化**：
- Agent L1 = 2,700-4,300 tokens
- 阈值 = 32 tokens
- **99%+ 的 Agent prefix 超过阈值**
- 等效于 in-batch caching 对 Agent 场景无效

**与 vLLM P1 的关系**：同一根因（调度步内无跨请求注册），但 SGLang 有潜在的缓解机制却因阈值过高而失效。

### 痛点 SP2：Retraction 仍丢失 Decode 输出

**机制**：`release_kv_cache(is_insert=False)` 不将 decode KV 插入 radix tree
**Agent 影响**：Agent 的推理/工具调用输出（5K-15K tokens）在 retraction 后丢失
**与 vLLM P3 的关系**：同一痛点，但 SGLang 的 prefix 恢复更优，只需重算 decode 部分

**量化**：
- SGLang retraction 恢复 TTFT = prefix 匹配时间 + decode 重算时间
- vLLM preemption 恢复 TTFT = 冷启动时间（全部重算）
- **SGLang 更优但仍需重算 decode 部分**

### 痛点 SP3：StreamingSession 内存锁定导致 OOM 风险

**机制**：StreamingSession 的 `lock_ref > 0`，KV 不释放
**Agent 影响**：Agent 长时间运行（30+ turns），KV 占用持续增长，可能耗尽 GPU 内存
**vLLM 无此问题**：vLLM 没有 Session 机制，不会锁定 KV

**量化**：
- 1 个 StreamingSession × turn 10 = ~20K tokens 被锁定
- 3 个并发 = ~60K tokens > 44K 容量 → OOM
- 即使不 OOM，锁定 KV 也减少了可用于其他请求的空间

### 痛点 SP4：LPM 降级机制在 Agent 负载下可能失效

**机制**：`len(waiting_queue) > 128` 时 LPM 降级为 FCFS
**Agent 影响**：Agent 高并发场景（如批量处理多个任务）可能触发降级
**vLLM 无此问题**：vLLM 只有 FCFS，不存在降级

**量化**：
- LMCache trace 有 767 个 session
- 如果大量 session 同时提交请求（如批量启动），可能超过 128
- 降级后 LPM 的 cache-aware 调度优势消失

### 痛点 SP5：Radix Tree 内存开销高于 Block Hash Table

**机制**：每个 TreeNode 包含 key、value、host_value、children dict、parent、lock_ref 等
**vLLM 对比**：BlockPool 只需 `cached_block_hash_to_block`（hash map）

**量化**：
- SGLang TreeNode ~200 bytes/node
- vLLM KVCacheBlock ~64 bytes/block
- 对于 6,157 token L0：SGLang ~1 node（200 bytes），vLLM ~385 blocks（24,640 bytes）
- 但 SGLang 的中间节点（L0 的父路径）也需要空间
- **总体**：SGLang 元数据开销可能更高，但差异在可接受范围内

---

## 8. Phase 5：C++ 模拟器扩展——SGLang block_size=64 对比

### 模拟器扩展计划

**目标**：在 C++ 模拟器中增加 SGLang 特有的模拟逻辑，形成 vLLM (bs=16) vs SGLang (bs=64) 的完整对比。

**现有基础**：
- `kvcache-blog/scripts/kv-cache-lab-native-sim.cc`：已支持 block_size=64
- `scripts/investigate_run_simulations.py`：已支持 block_size 参数

**新增**：
1. **Token-level 匹配模拟**：模拟 SGLang 的 token-level prefix matching（无 block 对齐浪费）
2. **Radix tree 驱逐模拟**：模拟 SGLang 的叶子节点优先驱逐（vs vLLM 的 free queue 驱逐）
3. **HiCache 层级模拟**：模拟 GPU→CPU→Storage 的统一管理

**模拟配置**：

| 配置 | vLLM 模拟 | SGLang 模拟 |
|------|----------|------------|
| Block size | 16 | 64（但 token-level 匹配） |
| 匹配粒度 | Block-level | Token-level |
| 驱逐策略 | LRU free queue | LRU min-heap (leaves only) |
| 层级管理 | 独立 | 统一（GPU→CPU→Storage） |

**预期模拟结果**：

| 容量 | vLLM LRU (bs=16) | SGLang LRU (bs=64, token-level) | SGLang 优势 |
|------|-----------------|-------------------------------|------------|
| 44K | 89.5% | ~92%+ | 叶子优先 + token-level |
| 32K | 59.5% | ~70%+ | 同上 |
| 16K | ~40% | ~55%+ | 同上 |

---

## 9. 输出结构

### 报告

```
docs/
  21_sglang_analysis_plan.md              # 本文档
  22_sglang_kv_cache_mechanics.md         # SGLang KV Cache 机制完整解析（对标 19_investigation_plan.md Part I）
  23_sglang_pain_point_analysis.md        # SGLang 痛点分析 + vLLM 对比（对标 investigation/report/05）

experiments/sglang_kv_cache/
  exp_s1_serial_replay/                    # S1: 单 session 串行回放
  exp_s2_concurrent_prefix/                # S2: 并发 prefix 共享
  exp_s3_in_batch_caching/                 # S3: In-batch prefix caching
  exp_s4_l0_eviction/                      # S4: L0 驱逐触发
  exp_s5_eviction_strategy/                # S5: 驱逐策略对比
  exp_s6_retraction_recovery/              # S6: Retraction 恢复
  exp_s7_hicache_unified/                  # S7: HiCache 层级统一
  exp_s8_schedule_policy/                  # S8: 调度策略对比
  exp_s9_streaming_session/                # S9: StreamingSession 零 prefill
  exp_s10_session_memory/                  # S10: StreamingSession 内存代价

scripts/
  sglang_exp_utils.py                      # SGLang 实验工具函数
  run_sglang_server.sh                     # SGLang server 部署脚本
  run_s1_serial_replay.py                  # S1 实验脚本
  run_s2_concurrent_prefix.py              # S2 实验脚本
  ...                                      # 其余实验脚本
```

### 核心产出：vLLM vs SGLang 痛点对比表

| 痛点 | vLLM 状态 | SGLang 状态 | SGLang 更优？ | 量化差距 |
|------|----------|------------|-------------|---------|
| P1: 并发共享失效 | [MEASURED] L1 命中 0% | [待测] 预期 L1 命中 0% | ❌ 同等 | 待测 |
| P2: LRU 驱逐 L0 | [SIMULATED] gap 6.9% | [待测] 预期 gap 更小 | ✅ 树结构保护中间节点 | 待测 |
| P3: Preemption/Retraction 丢失 decode | [MECHANISM] 完全重算 | [待测] prefix 可恢复 | ✅ 恢复更快 | 待测 |
| P4: Prefix 增长压力 | [TRACE] 3.64x | [共享数据] 3.64x | — | 同 |
| P5: Block 浪费 | [MEASURED] <0.07% | ✅ 不存在 | ✅ Token-level 无浪费 | 0% vs 0.07% |
| P6: Cache 层级不统一 | [PENDING] | ✅ 不存在 | ✅ HiRadixCache 统一 | 根本不同 |
| P7: 无调度感知 | [MEASURED] gap 2,384 | [待测] LPM/DFS 可缓解 | ✅ Cache-aware 调度 | 待测 |
| SP1: In-batch 阈值过高 | N/A | [待测] 32 token 阈值 | — | SGLang 特有 |
| SP2: Retraction 丢 decode | N/A | [待测] 同 P3 | — | 与 vLLM P3 同源 |
| SP3: Session 内存锁定 | N/A | [待测] OOM 风险 | ❌ vLLM 无此问题 | SGLang 特有 |
| SP4: LPM 降级 | N/A | [待测] >128 降级 | — | SGLang 特有 |

---

## 10. 执行顺序与依赖

```
Phase 0: 基础设施搭建
  ├── SGLang server 部署脚本
  ├── sglang_exp_utils.py
  └── Prometheus 指标调研

Phase 1: 基本行为验证（依赖 Phase 0）
  ├── S1: 串行回放
  ├── S2: 并发 prefix 共享
  └── S3: In-batch caching

Phase 2: 驱逐与 Retraction（依赖 Phase 1）
  ├── S4: L0 驱逐
  ├── S5: 驱逐策略对比
  └── S6: Retraction 恢复

Phase 3: 特有机制分析（可部分并行）
  ├── S7: HiCache 统一性（依赖 S4）
  ├── S8: 调度策略对比（依赖 S2）
  ├── S9: StreamingSession（依赖 Phase 0）
  └── S10: Session 内存代价（依赖 S9）

Phase 4: 模拟器扩展（可并行）
  └── block_size=64 + token-level + radix tree 驱逐

Phase 5: 报告与对比表（依赖所有 Phase）
```

---

## 11. 时间预算

| Phase | 实验 | 预计时间 | 依赖 |
|-------|------|---------|------|
| 0 | 基础设施搭建 | 2-3h | 无 |
| 1 | S1-S3 | 3-4h | Phase 0 |
| 2 | S4-S6 | 4-5h | Phase 1 |
| 3 | S7-S10 | 4-5h | Phase 1/2 |
| 4 | 模拟器扩展 | 2h | 可并行 |
| 5 | 报告 | 2h | 全部 |
| **总计** | | **~17h** | |

---

## 12. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| SGLang 不暴露 cached_tokens 指标 | 中 | 高 | 从 server log 解析；或通过 TTFT 差异间接推断 prefix 命中 |
| SGLang Qwen3-8B 部署失败 | 低 | 高 | 确认模型兼容性；备选模型 |
| HiCache 配置复杂 | 中 | 中 | 参考官方文档和配置示例 |
| SGLang Prometheus 指标与 vLLM 差异大 | 中 | 中 | 逐指标映射，建立等效关系 |
| StreamingSession API 不稳定 | 低 | 中 | 使用稳定版本；阅读 release notes |
| Retraction 难以触发 | 中 | 中 | 同 vLLM 策略：长输出 + 并发请求 |
| In-batch prefix caching 行为不确定 | 中 | 低 | 源码分析 + 日志验证 |

---

## 13. 与 P2/P3/P6 补强实验的关系

本文档（SGLang 分析规划）与 `docs/20_p2_p3_p6_reinforcement_plan.md`（vLLM 补强实验）是**并行独立**的两个任务：

| 维度 | vLLM 补强实验 | SGLang 分析 |
|------|-------------|------------|
| 目标 | 提升 P2/P3/P6 证据等级 | 全面对标 SGLang |
| 范围 | 3 个痛点 × 2-3 个实验 | 7 个 vLLM 痛点 + 4 个 SGLang 特有痛点 |
| 产出 | [MEASURED] 数据 | vLLM vs SGLang 对比表 |
| 可并行 | ✅ | ✅ |
| 互相增强 | SGLang 分析结果可指导 vLLM 补强策略 | vLLM 实验经验帮助设计 SGLang 实验 |

**建议执行顺序**：
1. 先完成 vLLM 补强实验（P2-A, P3-A, P6-A），获得关键 [MEASURED] 数据
2. 再启动 SGLang 分析，vLLM 的实验经验可直接复用
3. 两个任务的部分 Phase 可并行（如 vLLM P2-B/P3-B 与 SGLang Phase 0/1）

---

## 14. 验证检查点

| 检查点 | 通过标准 | 不通过怎么办 |
|--------|---------|------------|
| Phase 0: SGLang server 部署 | Server 正常启动，API 可用 | 检查模型路径、Python 环境 |
| Phase 0: Prometheus 指标 | 可采集 KV cache 使用率和 cache hit 指标 | 从 log 解析替代 |
| S1: 串行回放 | 串行命中率 ~100%，cached_tokens 精确 | 检查 radix cache 配置 |
| S2: 并发 prefix | 确认并发 L1 命中率是否为 0% | 如不为 0%，分析 in-batch 机制 |
| S4: L0 驱逐 | 成功触发驱逐或确认 L0 受树结构保护 | 增加压力或分析树结构 |
| S6: Retraction | num_retractions > 0，恢复 TTFT 可测量 | 增加 max_tokens 或并发数 |
| S7: HiCache | load_back 被触发，cached_tokens 包含恢复部分 | 检查 hicache 配置 |
| S9: StreamingSession | 跨 turn TTFT 显著低于无 Session | 检查 Session API 用法 |
