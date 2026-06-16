# vLLM KV Cache 源码分析

> 基于源码路径 `/share/dai-sys/zhoulongsheng/agentkv/Engine/vllm/` 深度分析
> 分析时间：2026-06-12

## 1. KV cache 基本抽象

### 1.1 Block 数据结构

vLLM v1 的核心 Block 元数据定义在 `KVCacheBlock` dataclass 中：

**文件**: `vllm/v1/core/kv_cache_utils.py:116-162`

```python
@dataclass(slots=True)
class KVCacheBlock:
    block_id: int                    # Block ID，范围 [0, num_gpu_blocks-1]
    ref_cnt: int = 0                 # 引用计数
    _block_hash: BlockHashWithGroupId | None = None  # 块哈希（仅满块且被缓存时有值）
    prev_free_block: KVCacheBlock | None = None      # 双向链表前驱（free queue）
    next_free_block: KVCacheBlock | None = None      # 双向链表后继（free queue）
    is_null: bool = False            # 是否为 null block（永不缓存）
```

**关键设计**：
- `KVCacheBlock` 仅是**元数据**，不持有实际 KV tensor 数据
- 实际的 KV 数据存储在 worker 端的 `kv_caches` tensor 中，由 `block_id` 索引
- 每个 Block 对应 `block_size` 个 token 的 KV 数据（默认 16 tokens）
- 双向链表指针 `prev_free_block/next_free_block` 仅用于 `FreeKVCacheBlockQueue`

**Null Block**: `BlockPool` 初始化时预分配一个 `null_block`（`block_pool.py:176`），用于填充 sliding window 中跳过位置。null block 的 `ref_cnt` 不被维护，不会被释放。

### 1.2 BlockTable（页表：逻辑位置 → 物理位置的映射）

#### 1.2.1 BlockTable 是什么？

**BlockTable 是 PagedAttention 的核心数据结构**，它的作用类似于操作系统的**页表**：

| 操作系统 | vLLM |
|---------|------|
| 虚拟地址 | 请求中 token 的逻辑 position |
| 虚拟页号 | 逻辑 block 索引（`position // block_size`） |
| 物理帧号 | 物理 block_id（`kv_caches` 的第一维索引） |
| 页内偏移 | block 内 slot 偏移（`position % block_size`） |
| 页表（虚拟页号 → 物理帧号） | BlockTable（逻辑 block 索引 → 物理 block_id） |
| 页大小 | block_size（默认 16 tokens） |

> **注意**：BlockTable 只存到**物理 block_id** 这一层（页表粒度），不存 token 级 slot。token 级的 flat 地址 `slot_id` 由 `slot_mapping` 承担（见 1.2.2）。

具体来说，BlockTable 是一个二维数组 `block_table[req_idx, logical_block_idx] = physical_block_id`：

- **行**：对应一个请求（`req_idx`）
- **列**：对应该请求中的逻辑 block 编号（第几个 block）
- **值**：指向 GPU 上 `kv_caches` tensor 中的物理 block 编号

例如，假设 block_size=16：
```
请求的 token 序列: [t0, t1, ..., t15, t16, ..., t31, t32, ..., t47]
逻辑 block 索引:    [  block_0     ] [  block_1    ] [  block_2    ]
BlockTable 行:      [  42          ] [  7           ] [  103         ]
```
这意味着：
- tokens t0~t15 的 KV 存储在 `kv_caches[42, :]`
- tokens t16~t31 的 KV 存储在 `kv_caches[7, :]`
- tokens t32~t47 的 KV 存储在 `kv_caches[103, :]`

**为什么需要 BlockTable？** 因为请求的逻辑位置（position 0, 1, 2, ...）和 GPU 上的物理存储位置不一定连续。PagedAttention 允许 KV cache 非连续存储，这样：
1. 不需要预分配连续大块内存
2. 可以共享 block（prefix cache 命中时，多个请求指向同一个物理 block）
3. 可以增量追加 block（decode 时只需追加新 block，不移动已有数据）

#### 1.2.2 slot_mapping 是什么？

`slot_mapping` 是**本 forward step 中、每个待处理 token 的物理 slot 编号**，形状为 `[num_batched_tokens]`（一维，与 batch 内 token 顺序对齐）：

```
slot_mapping[batch_token_idx] = slot_id    # flat index，int64
```

其中 `slot_id` 把物理 block_id 和 block 内偏移压成一个整数：

```
slot_id = physical_block_id * block_size + (position % block_size)
```

**物理含义**：`kv_caches` 在逻辑上可视为 `[num_blocks * block_size, ...]` 的 flat 数组，`slot_id` 就是某个 token 的 KV 在该 flat 空间中的索引。写 KV 的 kernel 再拆回 block 坐标：

```
block_idx    = slot_id // block_size      # 物理 block_id
block_offset = slot_id % block_size       # block 内第几个 token
```

**文件**: `vllm/v1/worker/block_table.py:75-77`（定义）、`vllm/v1/attention/ops/triton_reshape_and_cache_flash.py:52-59`（写入时使用）

**关键特征**：
- **Token 粒度**：每个 token 一条，不像 BlockTable 按 block 存
- **按 batch 组织**：一维数组，顺序与当前 step 的 batched tokens 一致（可混合多请求、chunked prefill）
- **每 step 重算**：每次 forward 根据本 step 的 `positions` 重新计算，不跨 step 持久化
- **主要服务于写路径**：`reshape_and_cache_flash(key, value, kv_cache, slot_mapping)` 用其做 scatter write

#### 1.2.3 BlockTable 与 slot_mapping：关系与区别

两者都在做「逻辑位置 → 物理存储」映射，但粒度、组织方式、生命周期和使用者不同。

##### 对比总览

| 维度 | BlockTable | slot_mapping |
|------|-----------|--------------|
| **粒度** | Block 级（每 `block_size` 个 token 一条） | Token 级（每个 token 一条） |
| **形状** | `[max_num_reqs, max_num_blocks_per_req]`（二维，按请求） | `[num_batched_tokens]`（一维，按 batch token 顺序） |
| **存什么** | 逻辑 block 索引 → 物理 block_id | batch token → flat slot_id |
| **生命周期** | 请求存活期间持久维护，decode 时增量追加 | 每次 forward 为本 step 的 token 重算 |
| **谁维护** | Scheduler 分配 block 后，`append_row()` / `add_row()` 写入 | `compute_slot_mapping()` 从 block_table + positions 推导 |
| **主要消费者** | Attention **读** KV（FlashAttention paged read） | `reshape_and_cache` **写** KV（scatter write） |

##### 从 BlockTable 推导 slot_mapping

`slot_mapping` **不是独立维护的第二套页表**，而是由 BlockTable 在本 step 展开得到：

```
slot_id = block_table[req_idx, position // block_size] * block_size + (position % block_size)
```

源码中由 Triton kernel `_compute_slot_mapping_kernel` 实现（`block_table.py:326-380`）：

```
pos → block_indices = pos // block_size
    → block_numbers = block_table[req_idx, block_indices]     # 查页表
    → slot_ids = block_numbers * block_size + block_offset    # 展开为 token 级地址
```

##### 块间无序、块内有序

PagedAttention 的物理布局可以概括为：**逻辑序列按 block 切分，块与块之间物理地址可以乱序分配，块内 slot 顺序存放**。

| | 块间（逻辑 block 之间） | 块内（同一 block 内） |
|---|------------------------|----------------------|
| **BlockTable** | 物理 block_id **可以无序、不连续** | 不表达块内顺序（只到 block 粒度） |
| **slot_mapping** | 跨 block 时 slot_id **会跳变** | 同一 block 内 slot_id **连续 +1** |

**BlockTable 只管块间映射**。它回答「逻辑 block #k 落在哪个物理 block_id」，例如 `[42, 7, 103]`——三个逻辑 block 对应的物理 block 完全不必相邻。块内第几个 token 存在哪，BlockTable 不管，由 `position % block_size` 在展开 slot 时补上。

**slot_mapping 同时体现块间无序和块内有序**。公式中两部分各司其职：

```
slot_id = physical_block_id * block_size + (position % block_size)
          └──── 块间：由 block_table 决定，可跳变 ────┘  └─ 块内 offset 递增 ─┘
```

块内：position 每 +1，slot_id 也 +1（同一物理 block 内）：

```
position 35 → slot 103*16+3 = 1651
position 36 → slot 103*16+4 = 1652
position 37 → slot 103*16+5 = 1653
```

块间：跨 logical block 边界时 slot_id 跳变：

```
position 15 → block 42 → slot 42*16+15 = 687
position 16 → block 7  → slot 7*16+0  = 112    ← 从 687 跳到 112
```

物理上 `kv_caches[block_id, offset, ...]` 的 **offset 维（0..block_size-1）始终有序**；不同 block_id 在 HBM 中不必相邻。

**三个常见误解**：

1. **`slot_mapping` 数组本身 ≠ slot_id 递增**。数组按 batch 内 token 顺序排列（可混合多请求），不是按 slot_id 排序。「块内有序」指的是同一请求、同一 block 内 position 递增 → slot_id 递增。
2. **逻辑连续 ≠ 物理连续**。逻辑 token 序列 0,1,2,… 连续；物理上只有同一 block 内 slot 连续，block 之间不要求连续。
3. **CP / padding 是例外**。上下文并行下，非本 rank 的 token 可能被标为 `PAD_SLOT_ID = -1`，不写入本地 cache，此时不适用「块内有序写入」的基本模型。

##### 物理存储与寻址方式

BlockTable 和 slot_mapping **最终都指向 GPU HBM 上同一块预分配的 `kv_caches` tensor**，但映射到的物理地址**粒度不同**，不是都映射到同一种「physical id」：

```
key_cache:   [num_blocks, block_size, num_heads, head_size]
value_cache: [num_blocks, block_size, num_heads, head_size]
```

**文件**: `vllm/v1/attention/ops/triton_reshape_and_cache_flash.py:29-30`

- **第一维 `num_blocks`**：BlockPool 分配的全部物理 block（`block_id` 即此下标）
- **第二维 `block_size`**：block 内第几个 token 的 slot（0 ~ block_size-1）
- 后面是 head、head_size 等

`kv_caches` 不是一维 flat 数组，而是 **`(block_id, offset)` 两维块式存储**。

| | BlockTable | slot_mapping |
|---|-----------|--------------|
| **映射结果** | 物理 **block_id**（第一维下标） | 物理 **slot_id**（flat 编码 = block_id + offset） |
| **粒度** | 块级 | token 级 |
| **如何访问 kv_caches** | `kv_caches[block_id, offset, ...]`，offset 由 kernel 内部计算 | `block_id = slot_id // block_size`，`offset = slot_id % block_size` → `kv_caches[block_id, offset, ...]` |

关系：`slot_id = physical_block_id * block_size + offset`——BlockTable 提供 block_id，slot_mapping 提供完整的 (block_id, offset) flat 编码。

```
                    ┌─────────────────────────────────────┐
                    │  kv_caches[block_id, offset, ...]   │
                    │  同一块 GPU HBM 上的物理 tensor       │
                    └─────────────────────────────────────┘
                           ▲                    ▲
                           │                    │
              读：block_table ──► block_id      │  写：slot_mapping ──► slot_id
                  kernel 内部算 offset          │       拆成 block_id + offset
                  遍历 0..block_size-1          │       scatter 写入
```

**写入示例**（slot_mapping）：

```
slot_mapping[i] = 1651
  → block_id = 1651 // 16 = 103
  → offset   = 1651 % 16  = 3
  → 写入 kv_caches[103, 3, :, :]
```

**读取示例**（block_table，标准 FlashAttention）：

```
block_table[req, 2] = 103          ← 只查 block_id
kernel 内部对 offset = 0, 1, ..., 15:
  → 读取 kv_caches[103, offset, :, :]
```

读路径**不经过 slot_mapping 数组**，但访问的仍是同一个 `kv_caches`——block_id 来自 block_table，offset 在 attention kernel 内按 `position % block_size` 计算。

##### 读写路径：数学等价，实现不同

读和写**物理地址的计算公式相同**：

```
slot_id = block_table[req, pos // block_size] * block_size + (pos % block_size)
          └──────── 块级查表 ────────┘              └── 块内 offset ──┘
```

差别在于**谁来算、算不算成数组**：

| | 写入 | 读取 |
|---|---|---|
| **处理哪些 token** | 仅本 step **新算出来**的 token | **整段历史**所有 token 的 KV |
| **映射表覆盖范围** | slot_mapping 只覆盖本 batch 的 token | 需要 0..seq_len-1 全部位置 |
| **实现方式** | 预先算好 slot_mapping 数组 → scatter write kernel 直接用 | block_table + seq_lens 传给 attention kernel → kernel 内部查表并算 offset |

```
写入：CPU/GPU 预先展开 → slot_mapping 数组 → reshape_and_cache 直接 scatter

读取：block_table 传给 flash_attn → kernel 内部 pos // block_size 查表
                                  → kernel 内部 pos % block_size 算 offset
                                  → 不 materialize slot_mapping
```

> **一句话**：写入用 slot_mapping「地址算好了，照着写」；读取用 block_table「给我页表和序列长度，kernel 自己翻页读」。少数特殊 backend（如 sparse MLA）读路径也会用到 slot_mapping，但标准 FlashAttention paged read **只用 block_table**。

##### 为什么需要两个结构？

**1. 读写 kernel 接口不同**

```
写入 KV（prefill/decode）:
  key/value ──reshape_and_cache──► kv_caches
                    ↑
              slot_mapping（scatter write：一 token 一 slot）

读取 KV（attention）:
  query ──flash_attn_varlen──► 读 kv_caches
                    ↑
              block_table + seq_lens（paged read：按 block 遍历历史 KV）
```

- **写**：当前 step 产出的 K/V 需 scatter 到确定 slot → 用 **slot_mapping**
- **读**：Attention 遍历整段历史 KV，kernel 内部按 block 查页表 → 用 **block_table**

标准 FlashAttention 读路径**不需要**为每个历史 token 预展开 slot；kernel 内部通过 `block_table[req, block_idx]` 做 paged lookup。

**2. 效率考虑**

- BlockTable 在请求生命周期内复用，decode 只追加新 block
- slot_mapping 仅为本 step 实际计算的 token 展开，避免维护 `[所有 req × 所有 position]` 的大表

**3. Batch 形态**

同一 forward 可混合多请求、chunked prefill；slot_mapping 与 batched token 顺序对齐，写路径更简单。

##### 完整数值示例

假设 `block_size=16`，某请求 BlockTable 为 `[42, 7, 103]`，本 step 处理 position 35、36（decode 两个 token）：

```
position 35:
  logical_block_idx = 35 // 16 = 2
  physical_block_id = block_table[req, 2] = 103
  slot_id = 103 * 16 + (35 % 16) = 1651

position 36:
  slot_id = 103 * 16 + 4 = 1652
```

本 batch 只有这两个 token 时：`slot_mapping = [1651, 1652]`。

Attention 读历史时不会枚举 `[1651, 1652, ...]` 所有 slot，而是用 `block_table = [42, 7, 103]` + `seq_len=37` 在 kernel 内按 block 读取。

##### 数据流

```
Scheduler 分配 block_ids
        ↓
BlockTable.append_row()          ← 持久页表（CPU numpy 写入）
        ↓ commit_block_table()   ← CPU → GPU 异步拷贝
compute_slot_mapping()           ← 本 step：block_table[GPU] + positions → slot_mapping[GPU]
        ↓
reshape_and_cache(slot_mapping)  ← 写 KV
flash_attn(block_table)          ← 读 KV
```

#### 1.2.4 两套 BlockTable 实现

vLLM v1 在 **Scheduler（调度侧）** 和 **Worker（推理侧）** 之间分工：Scheduler 负责分配 block_id，Worker 负责维护 BlockTable 并在 forward 中使用。两套 BlockTable 实现都运行在 **Worker 进程内**，差别在于具体代码路径和 CPU/GPU 交互方式（见下文对比表）。

##### Scheduler 与 Worker 的分工

```
┌──────────────── Scheduler (CPU) ────────────────┐
│  决定本 step 跑哪些请求                              │
│  KVCacheManager 分配 / 释放 block                  │
│  产出 SchedulerOutput（含 block_ids）               │
└──────────────────────┬──────────────────────────┘
                       │ IPC 传 block_ids、token 等
                       ▼
┌──────────────── Worker (GPU) ────────────────────┐
│  加载模型权重 + kv_caches tensor                   │
│  GPUModelRunner 做 forward                        │
│  维护 BlockTable、算 slot_mapping                  │
│  执行 attention 读写 KV                            │
└─────────────────────────────────────────────────┘
```

| | Scheduler | Worker |
|---|-----------|--------|
| **跑在哪** | 主要在 CPU（Engine 进程） | GPU 进程（每张卡通常一个 Worker） |
| **干什么** | 调度、分配 block、决定 batch | 跑模型、维护 block_table、读写 KV |
| **核心类** | `Scheduler`、`KVCacheManager` | `Worker`（`gpu_worker.py`）、`GPUModelRunner` |
| **是否持有 kv_caches** | 否（只分配 block_id 元数据） | 是（真正的 KV tensor 在 Worker 上） |

完整数据流见 §1.2.5：Scheduler 分配 block_ids → IPC 传给 Worker → Worker 更新 BlockTable 并 forward。

##### 「Worker 端 BlockTable」指什么？

§1.2.4(1) 中的 **Worker 端** 是相对 **Scheduler** 而言的——指推理进程里维护 block_table 的那套代码（`vllm/v1/worker/block_table.py`），**不是**指「只在 CPU 上运行」。

挂载关系（默认 v1 路径）：

```
Worker 进程
  └── GPUModelRunner (gpu_model_runner.py)
        └── InputBatch (gpu_input_batch.py)
              └── MultiGroupBlockTable   ← §1.2.4(1)
                    └── block_table.py
```

> **易混淆点**：§1.2.4(1) 架构图中的「CPU 端 / GPU 端」是**同一条 BlockTable 在 Worker 进程内的双缓冲**（pinned numpy ↔ GPU tensor），不是说 BlockTable 放在 Scheduler 的 CPU 上。Scheduler 只通过 IPC 传递 block_ids，不持有 block_table。

##### (1) Worker 端 BlockTable（`vllm/v1/worker/block_table.py`）

**用于：调度器分配 block 后，Worker 侧维护 block_table 并计算 slot_mapping**

```
┌─────────────────────── CPU 端 ───────────────────────┐    ┌──── GPU 端 ────┐
│ block_table.np  (numpy, pinned memory)                │    │ block_table.gpu │
│   ← append_row() 写入 block_ids                       │    │  ← copy_to_gpu()│
│                                                       │    │                 │
│ num_blocks_per_row (numpy)                            │    │                 │
│   ← 追踪每行有效 block 数                               │    │                 │
└───────────────────────────────────────────────────────┘    └────────┬────────┘
                                                                      │
                                                            commit_block_table()
                                                            (CPU → GPU 异步拷贝)
                                                                      │
                                                                      ▼
                                                            compute_slot_mapping()
                                                            (Triton kernel 在 GPU 上计算:
                                                             block_table[GPU] + positions
                                                             → slot_mapping[GPU])
```

核心数据结构：
- `block_table: CpuGpuBuffer[max_num_reqs, max_num_blocks_per_req]` — CPU/GPU 双缓冲
  - CPU 端：numpy 视图，Scheduler 分配 block 后通过 `append_row()` 写入
  - GPU 端：tensor，attention kernel 读取
- `num_blocks_per_row: np.ndarray[max_num_reqs]` — 每行有效 block 数
- `slot_mapping: CpuGpuBuffer[max_num_batched_tokens]` — token → 物理 slot 映射

核心方法：
- `append_row(block_ids, row_idx)`: 追加 block IDs 到指定行（decode 阶段增量追加）
- `add_row(block_ids, row_idx)`: 覆写整行（新请求，完整设置）
- `clear_row(row_idx)`: 清除行（请求完成）
- `commit_block_table(num_reqs)`: CPU → GPU 异步拷贝
- `compute_slot_mapping(num_reqs, query_start_loc, positions)`: Triton kernel 计算 slot mapping

**Hybrid Blocks**：当内存管理使用的 block_size 与 attention kernel 的 block_size 不同时（如内存 32 tokens/kernel 16 tokens），BlockTable 自动将内存 block_id 拆分为多个 kernel block_id：
```python
# map_to_kernel_blocks: 内存 block_id 0 → kernel block_id [0, 1]
kv_manager_block_ids = [0, 1, 2]
kernel_block_ids = [0, 1, 2, 3, 4, 5]  # 每个 * 2 + [0,1]
```

**上下文并行（CP）**：`compute_slot_mapping` 支持 pipeline CP 和 data CP，根据 CP rank 过滤非本地 slot（标记为 PAD_SLOT_ID = -1）。

##### (2) GPU BlockTables（`vllm/v1/worker/gpu/block_table.py`）

**用于：v2 路径 `worker/gpu/model_runner.py` 中，model forward 阶段在 GPU 上高效组装 batch 级别的 block_table**

> 与 (1) 的关系：两套实现都在 Worker 进程内，(1) 用于默认 `gpu_model_runner.py`，(2) 用于 `use_v2_model_runner=True` 时的 v2 ModelRunner。命名上 (2) 强调全 GPU 实现（StagedWrite + UVA），(1) 的「Worker 端」强调架构角色（推理侧 vs 调度侧）。

```
┌───────────── Stage Writes ─────────────┐
│ block_tables[i].stage_write(req_idx,   │
│   start, block_ids)                    │
│ → 延迟写入，不立即生效                    │
└─────────────────┬──────────────────────┘
                  │ apply_staged_writes()
                  ▼
┌───────────── GPU Tensors ──────────────┐
│ block_tables[i].gpu  (物理 block table) │
│ num_blocks.gpu       (每行有效 block 数) │
└─────────────────┬──────────────────────┘
                  │
   ┌──────────────┴───────────────┐
   │                              │
   ▼                              ▼
gather_block_tables()     compute_slot_mappings()
(Triton kernel:           (Triton kernel:
 req_index → block_table)  block_table + positions → slot_mapping)
   │                              │
   ▼                              ▼
input_block_tables        slot_mappings
(给 attention kernel 用)    (给 kv_cache write 用)
```

核心数据结构：
- `block_tables: list[StagedWriteTensor]` — 每个 KV cache group 一个，支持延迟写入（stage → apply）
- `num_blocks: UvaBackedTensor` — UVAmapped tensor，CPU 写入 GPU 可直接看到
- `input_block_tables: list[Tensor]` — 给 attention kernel 用的 block table（gather 后）
- `slot_mappings: Tensor[num_groups, max_num_batched_tokens]` — 所有 group 的 slot mapping

核心方法：
- `append_block_ids(req_index, new_block_ids, overwrite)`: 追加或覆写 block IDs（stage 写入）
- `apply_staged_writes()`: 将所有 staged writes 应用到 GPU tensor
- `gather_block_tables(idx_mapping, num_reqs_padded)`: 通过 Triton kernel 按 req 索引映射组装 batch block table
- `compute_slot_mappings(idx_mapping, query_start_loc, positions, num_tokens_padded)`: Triton kernel 计算 slot mapping

##### 两套 BlockTable 的关系

**源码里两套并存，运行时只用一个**——它们是互斥的实现路径，不会在同一个 Worker 进程里同时维护两份 block_table。

Worker 启动时由配置 `use_v2_model_runner` 二选一（`gpu_worker.py:327-341`）：

```
Worker 启动
    │
    ├── use_v2_model_runner = False（默认）
    │     → GPUModelRunner v1 (gpu_model_runner.py)
    │     → worker/block_table.py，挂载于 InputBatch.block_table
    │
    └── use_v2_model_runner = True
          → GPUModelRunner v2 (worker/gpu/model_runner.py)
          → worker/gpu/block_table.py，挂载于 GPUModelRunner.block_tables
```

| 配置 | ModelRunner | BlockTable 实现 |
|------|-------------|-----------------|
| `use_v2_model_runner=False`（**默认**） | `gpu_model_runner.py` | `worker/block_table.py` |
| `use_v2_model_runner=True` | `worker/gpu/model_runner.py` | `worker/gpu/block_table.py` |

其他平台：TPU 也使用 `worker/block_table.py`（通过 `tpu_input_batch.py`），与默认 GPU v1 路径同一套。

实现差异对比如下：

| 维度 | Worker BlockTable (`worker/block_table.py`) | GPU BlockTables (`worker/gpu/block_table.py`) |
|------|---------------------------------------------|-----------------------------------------------|
| **架构角色** | Worker 推理侧（相对 Scheduler） | 同在 Worker 进程，v2 优化路径 |
| **ModelRunner** | 默认 `gpu_model_runner.py` | v2 `worker/gpu/model_runner.py` |
| **挂载点** | `InputBatch.block_table` | `GPUModelRunner.block_tables` |
| **存储位置** | CPU pinned + GPU tensor（双缓冲） | GPU only (StagedWrite + UVA) |
| **写入方式** | numpy 直接写 CPU → copy_to_gpu | stage_write → apply_staged_writes |
| **slot_mapping** | Triton kernel 在 GPU 上计算 | Triton kernel 在 GPU 上计算 |
| **CP 支持** | ✅ pipeline + data CP | ✅ CP rank/interleave |

**MultiGroupBlockTable**：在**已选定的那一套**实现内部，每个 KV cache group 各有一个 BlockTable 实例（两套代码都有此封装）。用于混合注意力模型（如 Full Attention + Sliding Window + Mamba 共存）。这与上文「v1/v2 二选一」是不同层面的「多套」——前者是同一 ModelRunner 内按 KV group 分表，后者是 ModelRunner 版本之间的实现切换。

#### 1.2.5 BlockTable 的完整数据流

```
┌─────────────────── Scheduler (CPU) ───────────────────┐
│                                                        │
│  KVCacheManager.allocate_slots()                       │
│    → BlockPool 分配 block_ids                          │
│    → req_to_new_blocks[req_id].get_block_ids()         │
│                                                        │
│  SchedulerOutput:                                      │
│    NewRequestData.block_ids      (完整，新请求)          │
│    CachedRequestData.new_block_ids (增量，已调度请求)     │
└──────────────────────────┬─────────────────────────────┘
                           │ IPC (pickle + shared memory)
                           ▼
┌─────────────────── Worker (GPU) ───────────────────────┐
│                                                        │
│  GPUModelRunner._update_states():                      │
│    新请求: input_batch.add_request(req)                 │
│            → block_table.add_row(block_ids, req_idx)   │
│    已调度: input_batch.block_table.append_row(          │
│              new_block_ids, req_idx)                    │
│    ← 写 CPU/numpy                                      │
│                                                        │
│  GPUModelRunner._prepare_inputs_decode():               │
│    block_table.commit_block_table(num_reqs)             │
│    ← CPU → GPU 异步拷贝                                 │
│                                                        │
│    block_table.compute_slot_mapping(                    │
│        num_reqs, query_start_loc, positions)            │
│    ← Triton kernel: block_table[GPU] + positions        │
│       → slot_mapping[GPU]                              │
│                                                        │
│  CommonAttentionMetadata:                               │
│    block_table_tensor, slot_mapping                     │
│                                                        │
│  Attention forward:                                     │
│    do_kv_cache_update():                                │
│      reshape_and_cache_flash(                           │
│          key, value, kv_cache, slot_mapping)            │
│      ← scatter write: slot_mapping 作为写入索引          │
│                                                        │
│    flash_attn_varlen_func(                              │
│          query, key_cache, value_cache, block_table)    │
│      ← block_table 作为读取索引                         │
└────────────────────────────────────────────────────────┘
```

**关键设计要点**：
1. **增量传递**：Scheduler 只传新分配的 block_ids（`append_row`），减少通信开销
2. **双缓冲（CpuGpuBuffer）**：CPU 端通过 numpy 高效写入，GPU 端通过异步拷贝使用，避免 CPU-GPU 同步
3. **Triton kernel 计算 slot_mapping**：在 GPU 上直接从 block_table + positions 计算，避免 CPU-GPU 往返
4. **读写分离**：`slot_mapping` 主要用于 scatter write（写入 KV）；`block_table` 主要用于 paged read（Attention 读 KV）。部分特殊 backend（如 sparse MLA）也会用到 slot_mapping，但标准 FlashAttention 读路径只用 block_table
5. **Prefix cache 命中时**：多个请求的 BlockTable 行指向相同的物理 block_id（通过 `ref_cnt` 共享），这就是 APC 复用的物理基础

### 1.3 Key 设计

vLLM 的 KV cache key 体系是 **block-level hash chain**：

**BlockHash**: `kv_cache_utils.py:43`
```python
BlockHash = NewType("BlockHash", bytes)  # 32 bytes (sha256)
```

**BlockHashWithGroupId**: `kv_cache_utils.py:48`
```python
BlockHashWithGroupId = NewType("BlockHashWithGroupId", bytes)  # BlockHash + 4 bytes group_id
```

**Hash 计算方式** (`kv_cache_utils.py:563-590`):
```python
def hash_block_tokens(hash_function, parent_block_hash, curr_block_token_ids, extra_keys=None):
    if not parent_block_hash:
        parent_block_hash = NONE_HASH  # 初始种子
    return BlockHash(hash_function((parent_block_hash, curr_block_token_ids_tuple, extra_keys)))
```

**关键特性**：
- **链式哈希**：每个 block 的 hash 包含父 block 的 hash，形成 hash chain
- **初始种子** `NONE_HASH`：若未设 `PYTHONHASHSEED` 则随机生成 (`kv_cache_utils.py:98-113`)
- **extra_keys**：包含多模态 hash、LoRA name、cache_salt、prompt_embeds hash
- **默认哈希算法**：`sha256`（`cache.py:94`），可选 `sha256_cbor`/`xxhash`/`xxhash_cbor`

**与 SGLang 的本质区别**：
- vLLM：Block-level hash chain，粒度固定为 `block_size`（默认 16 tokens）
- SGLang：Token-level prefix tree (RadixCache)，粒度为单个 token
- vLLM 的 hash chain 使得 block 只能按 block_size 对齐复用，不支持 partial block hit
- SGLang 的 RadixTree 允许任意 token 粒度的前缀匹配

### 1.4 Value 设计

KV cache 的 value 有多个层次：

1. **GPU HBM**: Worker 端的 `kv_caches` tensor（`gpu_model_runner.py` 中分配）
   - 形状: `(num_blocks, page_size_bytes)` per layer
   - 数据类型: 由 `cache_dtype` 配置（auto/float16/bfloat16/fp8 等）
   - 通过 `block_id` 索引，slot mapping 确定具体位置

2. **CPU DRAM (offload)**: `kv_offload/cpu/` 和 `simple_kv_offload/`
   - CPU 侧的 KV cache buffer，由 `CPUOffloadingManager` 管理
   - 使用 `CanonicalKVCacheTensor` 规范化格式 (`base.py:356`)

3. **Disk SSD**: `kv_offload/tiering/fs/`
   - `FileSystemTierManager`: 基于文件的二级存储
   - 文件路径: `<base_path>_r<rank>/<hhh>/<hh>_g<group_idx>/<hash_hex>.bin`

4. **Remote Object Store**: `kv_offload/tiering/obj/`
   - `ObjectStoreSecondaryTierManager`: 通过 NIXL agent 访问远程对象存储

5. **Remote Memory (RDMA)**: `kv_transfer/` 下的 Mooncake/NIXL connector
   - 使用 Mooncake TransferEngine 或 NIXL 进行跨节点传输

### 1.5 引用计数机制

**文件**: `vllm/v1/core/block_pool.py`

引用计数由 `KVCacheBlock.ref_cnt` 字段追踪。

**谁持有引用**：
- 每个 `SingleTypeKVCacheManager` 的 `req_to_blocks[request_id]` 列表持有该请求的所有 block
- 当一个 block 在 `req_to_blocks` 中时，其 `ref_cnt >= 1`
- 被缓存但未被任何请求引用的 block，`ref_cnt == 0`，在 free queue 中作为驱逐候选

**引用计数操作**：
1. **分配** (`block_pool.py:333-363`): `get_new_blocks()` 从 free queue 弹出 block，`ref_cnt += 1`
2. **Touch** (`block_pool.py:402-417`): prefix cache 命中时 `touch()` 增加 `ref_cnt`
   - 若 `ref_cnt == 0`（在 free queue 中），先从 free queue 移除，再 `ref_cnt += 1`
3. **释放** (`block_pool.py:419-441`): `free_blocks()` 将 `ref_cnt -= 1`
   - 仅当 `ref_cnt == 0` 且非 null 时才放回 free queue
   - cached block（有 block_hash）放回 free queue 尾部（驱逐候选）
   - uncached block 放回 free queue 头部（优先复用，`prepend=True`）

**完整生命周期**：
```
创建 → get_new_blocks(ref_cnt=1) → 请求使用 → free_blocks(ref_cnt=0)
                                            ↘ 如果被缓存 → 进入 free queue 尾部
                                            ↘ 如果未缓存 → 进入 free queue 头部
                                            ↘ 如果被其他请求 touch → ref_cnt > 0 → 不释放
请求完成 → 按逆序释放 blocks → cached 在后(驱逐候选)，uncached 在前(优先复用)
```

### 1.6 Copy-on-Write 机制

**vLLM v1 不实现传统意义上的 COW 机制**。

原因：vLLM 的设计哲学是 **append-only block table**。如 `block_pool.py:48-52` 的注释所述：

> NOTE #1: We currently don't de-duplicate the blocks in the cache, meaning that if a block becomes full and is cached, we don't check if there is already an identical block in the cache. This is because we want to make sure the allocated block IDs won't change so that block tables are append-only.

**隐式 COW 效果**：
- 当一个 cached block 被 touch（prefix cache 命中），新请求共享同一个物理 block（通过 `ref_cnt` 追踪）
- 这不是真正的 COW，因为 block 是只读的（满块才缓存），不存在写入冲突
- 对于 decode 阶段的新 block，总是分配新的物理 block，不会与 cached block 冲突

**与 SGLang 的对比**：
- SGLang RadixCache 实现了真正的 COW：当一个 node 需要追加 token 但其子节点被多个请求共享时，先复制 node 再修改
- vLLM 不需要 COW 是因为：block table 是 append-only，满块不可修改，decode 产生的 block 一定是新分配的

---

## 2. 生命周期

### 2.1 Allocate

**入口**: `KVCacheManager.allocate_slots()` (`kv_cache_manager.py:244-458`)

分配流程：
1. **计算需要分配的 block 数** (`coordinator.get_num_blocks_to_allocate()`)
2. **释放不必要的 block**（sliding window 跳过的 block）(`coordinator.remove_skipped_blocks()`)
3. **检查可用空间**：`required_blocks > available_blocks` 则返回 None（分配失败）
4. **分配 prefix cache 命中的 block** (`coordinator.allocate_new_computed_blocks()`)
   - Touch cached blocks（增加 ref_cnt）
   - 对于 SWA，跳过的 block 用 null_block 填充
5. **分配新 block** (`coordinator.allocate_new_blocks()`)
   - 从 `BlockPool.get_new_blocks()` 获取
   - 如果启用 caching，先驱逐 cached block
6. **缓存满块** (`coordinator.cache_blocks()`)

**Block 分配细节** (`block_pool.py:333-363`):
```python
def get_new_blocks(self, num_blocks):
    ret = self.free_block_queue.popleft_n(num_blocks)
    for block in ret:
        if self.enable_caching:
            self._maybe_evict_cached_block(block)  # 驱逐被复用的 cached block
        block.ref_cnt += 1
    return ret
```

### 2.2 Prefill 写入

Prefill 阶段的 KV cache 写入由 ModelRunner 在 forward pass 中完成：

1. **调度器** 通过 `allocate_slots()` 为请求分配 block，返回 `KVCacheBlocks`
2. **Block IDs** 传入 `SchedulerOutput` → `NewRequestData`
3. **Worker** 的 `GPUModelRunner` 接收 block IDs，构建 `BlockTable`
4. **Attention kernel** 在 prefill forward 中将 K/V 写入 `kv_caches[block_id * block_size + offset]`
5. 具体写入通过 `slot_mapping` 定位：`slot_id = block_id * block_size + local_offset`

**Chunked Prefill**:
- 当 `num_new_tokens > long_prefill_token_threshold` 时，prefill 被分块
- 每个调度步骤只处理部分 tokens
- `num_computed_tokens` 追踪已处理量，下次从断点继续

### 2.3 Decode Append

Decode 阶段每次只处理 1 个 token（或 spec decoding 的多个 token）：

1. 调度器为 running 请求调用 `allocate_slots()`，`num_new_tokens = 1`
2. 如果当前 block 未满，不需要新 block（`num_required_blocks - num_req_blocks <= 0`）
3. 如果 block 已满，分配新 block
4. Attention kernel 在 decode forward 中将新 token 的 K/V 写入对应 slot

**KV cache 追加不需要移动已有数据**——这是 paged attention 的核心优势。

### 2.4 命中复用

**Prefix Cache Hit 流程**:

1. **请求创建时**计算 block hashes (`request.py:175-180`):
   ```python
   self.block_hashes: list[BlockHash] = []
   self._block_hasher = block_hasher  # 绑定 block hash 计算函数
   self.update_block_hashes()         # 初始计算
   ```

2. **调度器调度 WAITING 请求时**，调用 `kv_cache_manager.get_computed_blocks(request)` (`kv_cache_manager.py:202-242`):
   ```python
   max_cache_hit_length = request.num_tokens - 1  # 必须重算最后一个 token
   computed_blocks, num_new_computed_tokens = self.coordinator.find_longest_cache_hit(
       request.block_hashes, max_cache_hit_length
   )
   ```

3. **`find_longest_cache_hit()`** 逐 block 查找 (`single_type_kv_cache_manager.py:523-569`):
   - Full Attention: 左到右顺序查找，命中 break
   - Sliding Window: 右到左查找，需要连续 block
   - Mamba: 右到左查找，只需要最后一个 block

4. **命中后的处理**:
   - `allocate_new_computed_blocks()` touch 命中的 block（`ref_cnt += 1`）
   - 命中的 block 直接映射到 block table，不需要重新计算 KV
   - `num_computed_tokens` 跳过已缓存的 tokens，prefill 只处理剩余部分

5. **避免重复计算**:
   - `request.num_computed_tokens = num_computed_tokens`（跳过 cached 部分）
   - Prefill 只处理 `num_new_tokens = request.num_tokens - num_computed_tokens`

### 2.5 Evict/Free/Offload

**触发条件**：

1. **新 block 分配时驱逐** (`block_pool.py:365-400`):
   - `get_new_blocks()` 从 free queue 弹出 block
   - 如果 block 有 `block_hash`（cached），调用 `_maybe_evict_cached_block()`
   - 驱逐：从 `cached_block_hash_to_block` 移除，`block.reset_hash()`

2. **Preemption 释放** (`scheduler.py:1033-1054`):
   - 当 GPU 空间不足时，preempt 最低优先级的 running 请求
   - 调用 `kv_cache_manager.free(request)` 释放所有 blocks
   - `request.num_computed_tokens = 0`（需要完全重算）

3. **SWA 跳过释放** (`single_type_kv_cache_manager.py:448-501`):
   - 当 token 超出 sliding window 时，释放 window 外的 blocks
   - 用 null_block 替换，uncached 优先复用（prepend），cached 留作驱逐候选

4. **请求完成释放** (`single_type_kv_cache_manager.py:363-378`):
   - `free(request_id)` 逆序释放 blocks
   - cached 和 uncached blocks 分别处理

**Offload 机制**:
- `CPUOffloadingManager` (`kv_offload/cpu/manager.py`): CPU DRAM offload，支持 LRU/ARC 策略
- `FileSystemTierManager` (`kv_offload/tiering/fs/manager.py`): SSD offload
- `ObjectStoreSecondaryTierManager` (`kv_offload/tiering/obj/manager.py`): 远程对象存储
- `SimpleCPUOffloadScheduler` (`simple_kv_offload/manager.py`): 简化版 CPU offload

### 2.6 Request 结束后的处理

**文件**: `scheduler.py` 中的 `update_from_output()` 和 `_process_finished_requests()`

1. **请求完成后**，调度器调用 `kv_cache_manager.free(request)` (`kv_cache_manager.py:460-468`)
2. `free()` 调用 `coordinator.free(request_id)` → 每个 `SingleTypeKVCacheManager.free()`
3. 所有 block 的 `ref_cnt` 递减，`ref_cnt == 0` 的 block 放回 free queue
4. **Cached blocks 保留在 `cached_block_hash_to_block` 中**（不清除 hash 映射）
5. 这些 cached blocks 在 free queue 尾部，可作为后续请求的 prefix cache 命中源
6. 当新请求需要分配 block 且 free queue 中的 cached block 被弹出时，执行驱逐（从 hash 表移除）

**保留时长**：cached block 在 free queue 中**一直保留直到被驱逐**。驱逐顺序为 LRU（free queue 头部优先弹出）。

**KV Connector 的特殊处理**:
- 如果配置了 KV connector（如 P/D disaggregation），`request_finished()` 可能返回 `True` 表示 connector 异步负责释放 blocks
- 这意味着 blocks 不会立即释放，而是等待 connector 完成远程传输后再释放

---

## 3. 内存层级

### 3.1 GPU HBM

- **主存储**：所有 KV cache 的主要存储位置
- **分配方式**：启动时通过 `CacheConfig` 计算可用 block 数量
- **管理**：`BlockPool` 管理 GPU blocks 的分配/释放/缓存
- **Tensor 布局**：由 `KVCacheConfig.kv_cache_tensors` 定义，可能跨 layer 共享 tensor
- **量化**：支持 FP8/INT8/NVFP4 等多种 KV cache 量化格式

### 3.2 CPU DRAM (swap/offload)

vLLM v1 **没有 v0 的 swap 机制**。取而代之的是更灵活的 offload 体系：

**CPU Offloading** (`kv_offload/cpu/`):
- `CPUOffloadingManager`：管理 CPU 侧的 KV cache blocks
- 支持两种缓存策略：LRU 和 ARC (`kv_offload/cpu/policies/`)
- `SharedOffloadRegion`：CPU 侧共享内存区域
- `GPUWorker`：处理 GPU↔CPU 的数据传输
- 数据流：GPU → CPU (store) / CPU → GPU (load)

**SimpleCPUOffload** (`simple_kv_offload/`):
- 简化版 CPU offload，独立的 CPU KV cache coordinator
- 使用 `SimpleCPUOffloadScheduler` 和 `SimpleCPUOffloadWorker`
- 通过 `CopyBackend` (CUDA memcpy) 或 `CudaMemOps` 进行数据传输

### 3.3 Disk SSD

**FileSystemTierManager** (`kv_offload/tiering/fs/manager.py`):
- 二级 offloading 层，数据从 CPU tier 级联到 SSD
- 文件路径格式：`<base_path>_r<rank>/<hhh>/<hh>_g<group_idx>/<hash_hex>.bin`
- 使用 `DualQueueThreadPool`（读/写优先线程池）
- Store 路径：写入临时文件 → `os.replace` 原子重命名
- Load 路径：`os.readv` 直接读入 memoryview
- 跨进程共享需设置相同的 `PYTHONHASHSEED`

### 3.4 Remote Memory

**ObjectStoreSecondaryTierManager** (`kv_offload/tiering/obj/manager.py`):
- 通过 NIXL agent 访问远程对象存储
- 支持存在性探测（`query_memory`）和实际数据传输
- 异步传输模型：`submit_load/submit_store` → `get_finished_jobs` 轮询

### 3.5 层级迁移机制

vLLM v1 的 offload 体系采用**层级级联**设计：

```
GPU HBM (主存储)
  ↕ CPU DRAM (一级 offload, CPUOffloadingManager)
    ↕ SSD (二级 offload, FileSystemTierManager)
    ↕ Remote Object Store (二级 offload, ObjectStoreSecondaryTierManager)
```

**关键规则** (`kv_offload/tiering/base.py:48-53`):
> Secondary tiers cannot directly access GPU memory. All data transfers must go through the CPU (primary) tier:
> - Store: GPU → CPU (primary) → secondary (cascade)
> - Load: secondary → CPU (primary) → GPU (promotion)

**OffloadingManager 接口** (`kv_offload/base.py:149-300`):
- `lookup(key)`: 检查 block 是否已 offload
- `prepare_load(keys)`: 准备加载，保护 block 不被驱逐
- `touch(keys)`: 标记 block 最近使用（LRU 更新）
- `complete_load(keys)`: 加载完成
- `prepare_store(keys)`: 准备存储
- `complete_store(keys)`: 存储完成，block 变为可加载

---

## 4. Prefix cache / reuse 机制 (APC)

### 4.1 Block hash 计算

**文件**: `vllm/v1/core/kv_cache_utils.py:563-590`

```python
def hash_block_tokens(hash_function, parent_block_hash, curr_block_token_ids, extra_keys=None):
    if not parent_block_hash:
        parent_block_hash = NONE_HASH
    curr_block_token_ids_tuple = tuple(curr_block_token_ids)
    return BlockHash(hash_function((parent_block_hash, curr_block_token_ids_tuple, extra_keys)))
```

**特性**：
- **链式哈希**：`hash(block_i) = H(hash(block_{i-1}), tokens_i, extra_keys_i)`
- **确定性**：相同的 token 序列产生相同的 hash chain
- **种子**：`NONE_HASH`，由 `PYTHONHASHSEED` 或 `os.urandom(32)` 决定 (`kv_cache_utils.py:98-113`)
- **Hash 算法**：默认 sha256，可选 xxhash_cbor（更快，跨语言兼容）
- **extra_keys** 来源 (`generate_block_hash_extra_keys()`, `kv_cache_utils.py:525-560`):
  - 多模态特征：`(mm_hash, start_offset)`
  - LoRA name
  - cache_salt（仅第一个 block）
  - prompt_embeds hash

**Block hash 计算时机** (`kv_cache_utils.py:659-710`):
- 请求创建时：`Request.__init__()` → `update_block_hashes()` → `self._block_hasher(self)`
- 每次追加 output token 时：`append_output_token_ids()` → `update_block_hashes()`
- 仅对**满块**计算 hash（`num_tokens >= (len(block_hashes)+1) * block_size`）

### 4.2 Hash 表维护

**文件**: `vllm/v1/core/block_pool.py:34-127`

`BlockHashToBlockMap` 维护 hash → block 的映射：

```python
class BlockHashToBlockMap:
    def __init__(self):
        self._cache: dict[BlockHashWithGroupId, KVCacheBlock | dict[int, KVCacheBlock]] = {}
```

**设计细节**：
- Key 是 `BlockHashWithGroupId`（BlockHash + 4 bytes group_id）
- Value 是 `KVCacheBlock`（单个 block）或 `dict[int, KVCacheBlock]`（多个同 hash block）
- 当多个 block 有相同 hash 时（不同物理 block 但相同内容），合并为 dict
- **不进行去重**：相同内容的不同 block 不会合并为一个（保证 block table append-only）

**操作**：
- `get_one_block(key)`: 获取任意一个匹配的 block
- `insert(key, block)`: 插入 block（已有则合并为 dict）
- `pop(key, block_id)`: 弹出指定 block_id

**缓存写入时机** (`block_pool.py:211-331`):
- `cache_full_blocks()`: 当 block 变满时，设置 `block_hash` 并插入 hash 表
- 仅缓存 `num_cached_blocks` 到 `num_full_blocks` 之间的新满块

### 4.3 APC 命中处理路径

APC（Automatic Prefix Caching）的核心思路：**以前算过的 prompt 前缀，其 KV 已经存在 GPU 上；新请求若前缀相同，直接复用这些 block，跳过 prefill 计算**。

命中处理分两个阶段：**查找（lookup）** 和 **绑定（bind）**。查找只读 hash 表；绑定把命中的 physical block 挂到新请求上。

#### 4.3.1 整体流程概览

```
新请求到达 (WAITING)
    │
    ▼
[1] 计算 block_hashes（请求创建时已算好，链式 hash）
    │
    ▼
[2] find_longest_cache_hit()  ← 在 hash 表中逐 block 查找最长前缀
    │
    ├── 未命中 → num_computed_tokens = 0，正常 prefill
    │
    └── 命中 N 个 block → 得到 computed_blocks + num_hit_tokens
            │
            ▼
[3] allocate_new_computed_blocks()  ← touch + 挂到 req_to_blocks（不拿新 block）
            │
            ▼
[4] allocate_new_blocks()  ← 仅为剩余 token 从 free pool 拿新 block
            │
            ▼
[5] SchedulerOutput → Worker 更新 BlockTable
            │
            ▼
[6] Prefill 只算 num_new_tokens = num_tokens - num_computed_tokens
    命中部分的 KV 不重新写入
```

#### 4.3.2 阶段一：查找（Lookup）

**入口**：Scheduler 调度 WAITING 请求时（`scheduler.py:623-662`）

```python
new_computed_blocks, num_new_local_computed_tokens = \
    self.kv_cache_manager.get_computed_blocks(request)
```

**Step 1 — 前置检查**（`kv_cache_manager.py:218-219`）：
- `enable_caching == False` → 直接返回空，不查 cache
- `request.skip_reading_prefix_cache == True` → 跳过（如 prompt logprobs 场景）

**Step 2 — 限制最大命中长度**（`kv_cache_manager.py:221-227`）：

```python
max_cache_hit_length = request.num_tokens - 1  # 必须重算最后一个 token
```

即使 prompt 全部命中 cache，**最后一个 token 也必须重算**，因为需要它的 logits 做采样。这是「全命中仍要算 1 个 token（甚至 1 个 block）」的原因。

**Step 3 — 逐 block 链式查找**（`FullAttentionManager.find_longest_cache_hit()`）：

```python
for block_hash in itertools.islice(block_hashes, max_num_blocks):
    if cached_block := block_pool.get_cached_block(block_hash, kv_cache_group_ids):
        computed.append(cached_block)   # 命中，继续
    else:
        break                            # chain 断裂，停止
```

关键约束：**hash chain 要求严格前缀匹配**——必须从 block 0 开始连续命中，任一 block miss 则后续全部停止：

```
block_hashes:  [H0,  H1,  H2,  H3,  H4]
hash 表:        [✓,   ✓,   ✗,   -,   -]
命中结果:       [B0,  B1]              ← 只命中 2 个 block，32 tokens（block_size=16）
```

为什么不能跳 block 命中？因为 `hash(block_i) = H(hash(block_{i-1}), tokens_i)`，block 2 的 hash 依赖 block 1 的 hash。block 1 没命中，block 2 的 hash 对不上，chain 必然断裂。

**Step 4 — hash 表查找细节**（`block_pool.py:184-209`）：

```python
def get_cached_block(block_hash, kv_cache_group_ids):
    for group_id in kv_cache_group_ids:
        block = cached_block_hash_to_block.get_one_block(hash + group_id)
        if not block:
            return None   # 任一 KV group miss → 整体 miss
        cached_blocks.append(block)
    return cached_blocks
```

- Key = `BlockHashWithGroupId`（hash + group_id），Hybrid 模型每个 attention group 各查一次
- 同 hash 可能有多个 physical block（不去重），取任意一个即可
- 被命中的 block 可能 `ref_cnt == 0`（在 free queue 里等待驱逐），此时仍可用，后续 touch 会把它拉出来

**查找产出**：

| 产出 | 含义 |
|------|------|
| `computed_blocks` | 命中的 `KVCacheBlock` 列表（含 physical block_id） |
| `num_new_computed_tokens` | `len(computed_blocks) * block_size`（命中 token 数） |

#### 4.3.3 阶段二：绑定（Bind）

查找完成后，Scheduler 调用 `allocate_slots()`，内部两步：

**Step 5 — 挂接 cached blocks**（`allocate_new_computed_blocks()`）：

```
对每个命中的 block:
  1. touch(block)          → ref_cnt += 1，若在 free queue 则移除（防驱逐）
  2. req_to_blocks.extend  → 挂到新请求的 block 列表
  3. num_cached_block 标记  → 后续 cache_blocks() 不会重复缓存
```

这一步**不从 free pool 分配新 physical block**，只是让新请求「指向」已有 block。

**Step 6 — 分配剩余 block**（`allocate_new_blocks()`）：

仅为 cache 未覆盖的 token 从 free pool 拿新 block：

```
num_new_tokens = request.num_tokens - num_computed_tokens
剩余 block 数 = ceil(num_new_tokens / block_size) - 已有 block 数
```

#### 4.3.4 数值示例

假设 `block_size = 16`，system prompt 已被请求 A 算过并 cache：

```
请求 A（之前）:
  prompt = "You are a helpful assistant. Please answer:"  (48 tokens = 3 blocks)
  BlockTable = [10, 20, 30]    ← 已 cache，hash 表中有 H0→10, H1→20, H2→30

请求 B（新来，相同 system prompt + 新问题）:
  prompt = "You are a helpful assistant. Please answer:" + "What is 2+2?"  (52 tokens)
  block_hashes = [H0, H1, H2, H3]

[Lookup]
  H0 → block 10 ✓
  H1 → block 20 ✓
  H2 → block 30 ✓
  H3 → miss ✗  (block 3 从未算过)
  命中: 3 blocks = 48 tokens

[Bind]
  touch(10, 20, 30)           ref_cnt: 1→2 for each
  req_to_blocks = [10, 20, 30]

[Allocate new]
  剩余 4 tokens ("2+2?") → 需要 1 个新 block
  get_new_blocks(1) → block 205
  req_to_blocks = [10, 20, 30, 205]

[Worker]
  BlockTable = [10, 20, 30, 205]
  num_computed_tokens = 48
  prefill 只算后 4 tokens 的 KV，写入 block 205
  block 10/20/30 的 KV 直接用于 attention 读取，不重新写入
```

#### 4.3.5 命中后的三个「跳过」

| 跳过什么 | 机制 |
|---------|------|
| **跳过 KV 计算** | `num_computed_tokens = 48`，attention 只对 position ≥ 48 的 token 做 forward |
| **跳过 KV 写入** | 命中 block 已有 KV，`reshape_and_cache` 只写新 block（block 205）的 slot |
| **跳过重复缓存** | `num_cached_block` 标记已 cache 的 block，`cache_blocks()` 不会给它们重新算 hash |

#### 4.3.6 特殊情况

**全命中（prompt 全部在 cache 中）**：

```
max_cache_hit_length = num_tokens - 1
→ 最多命中 num_tokens - 1 个 token
→ 最后 1 个 token 必须重算（需要 logits）
→ 若最后不足 1 个 block，可能重算整个末 block（block 对齐限制）
```

**Running 请求不会再查 prefix cache**（`single_type_kv_cache_manager.py:205-209`）：

```python
if request_id in self.num_cached_block:
    assert len(new_computed_blocks) == 0  # running 请求不会有新命中
    return
```

Prefix cache 查找**只在请求首次调度（WAITING → RUNNING）时做一次**。之后 decode 追加的新 block 走正常的 allocate + cache 流程。

**Hybrid 模型（Full Attention + Mamba 等）**：

各 KV cache group 独立查找，最终命中长度取各 group 的交集（固定点迭代）。Mamba 只关心最后一个 block 是否命中；Full Attention 要求从左到右连续命中。

#### 4.3.7 源码路径索引

| 步骤 | 文件 | 函数 |
|------|------|------|
| 调度入口 | `scheduler.py:623-662` | `schedule()` 中调用 `get_computed_blocks()` |
| 查找入口 | `kv_cache_manager.py:202-242` | `get_computed_blocks()` |
| 逐 block 查找 | `single_type_kv_cache_manager.py:523-569` | `FullAttentionManager.find_longest_cache_hit()` |
| Hash 表查询 | `block_pool.py:184-209` | `get_cached_block()` |
| 挂接 cached blocks | `single_type_kv_cache_manager.py:182-244` | `allocate_new_computed_blocks()` |
| Touch 防驱逐 | `block_pool.py:402-417` | `touch()` |
| 分配新 block | `kv_cache_manager.py:435-440` | `allocate_new_blocks()` |
| Worker 更新 | `gpu_model_runner.py:1401+` | `block_table.add_row()` / `append_row()` |

### 4.4 Hash collision 处理

**vLLM 没有显式的 hash collision 处理机制**。

原因：
1. 使用 SHA-256（256 bits），collision 概率极低
2. Hash chain 设计隐式降低了 collision 影响：即使单个 block hash 碰撞，后续 block 的 hash 不同也会断开 chain
3. 如果确实发生 collision，最坏情况是：两个不同内容的 block 被错误地视为相同，导致 attention 使用错误的 KV cache

**没有 content verification**：vLLM 不在命中后验证 block 内容是否真的匹配。这是一个潜在的正确性风险，但在实践中被认为可以接受（SHA-256 collision 概率约 2^-128）。

### 4.5 与 SGLang RadixCache 的区别

| 维度 | vLLM APC (Block Hash Chain) | SGLang RadixCache |
|------|---------------------------|-------------------|
| **数据结构** | Hash table (`BlockHash → KVCacheBlock`) | Radix Tree (prefix tree) |
| **匹配粒度** | Block-level (block_size tokens, 默认 16) | Token-level |
| **Key 计算** | Hash chain: `H(parent_hash, tokens, extra)` | Tree path: token ID 序列 |
| **部分命中** | 不支持（只匹配完整 block） | 支持（token-level 匹配） |
| **非前缀复用** | 不支持（chain 要求严格前缀） | 支持（radix tree 支持中间节点匹配） |
| **COW** | 不需要（append-only block table） | 需要（共享 node 修改前复制） |
| **Hash collision 风险** | 存在（但极低） | 不存在（直接比较 token IDs） |
| **内存开销** | 低（仅 hash 表） | 较高（tree node 结构） |
| **查找复杂度** | O(num_blocks) 顺序查找 | O(depth) tree traversal |
| **跨请求复用** | 支持（通过 block hash 查找） | 支持（通过 radix tree 共享节点） |
| **Hybrid 模型** | 复杂（需多 group 协调） | 相对简单 |
| **Cache 驱逐** | LRU（free queue 顺序） | LRU（evictable node 驱逐） |

**本质区别**：
- vLLM 的 block hash 是**内容寻址**（content-addressed），类似 CDN 的 cache key
- SGLang 的 RadixCache 是**结构寻址**（structure-addressed），类似文件系统的路径查找
- vLLM 只能匹配"前缀"，因为 hash chain 的单调性要求；SGLang 可以匹配任意子串（因为 radix tree 支持中间节点）

### 4.6 跨请求/跨节点复用

**跨请求复用**：支持
- 同一个 GPU 上的不同请求通过 `BlockHashToBlockMap` 共享 cached blocks
- 命中时通过 `touch()` 增加 `ref_cnt`，物理 block 被多个请求共享
- 这是 APC 的核心价值

**跨 worker 复用**：不支持（在同一个 vLLM 实例内）
- 每个 worker 有独立的 KV cache tensor 和 block 管理
- 调度器端的 `BlockPool` 是集中式的，但 worker 端的 KV 数据是分布式的
- TP 并行下，各 rank 的 KV cache 分片不同，无法直接共享

**跨节点/跨引擎复用**：通过 KV Connector 支持
- **Mooncake Connector** (`kv_transfer/kv_connector/v1/mooncake/`): RDMA 传输
- **NIXL Connector** (`kv_transfer/kv_connector/v1/nixl/`): 通用跨节点传输
- **LMCache Connector** (`kv_transfer/kv_connector/v1/lmcache_connector.py`): 外部缓存集成
- **HF3FS Connector** (`kv_transfer/kv_connector/v1/hf3fs/`): 高性能文件系统

---

## 5. 调度器与 KV cache 的关系

### 5.1 Cache 命中信息传递

**Scheduler → Worker 的信息流**：

1. **调度器端** (`scheduler.py:623-698`):
   - 调用 `kv_cache_manager.get_computed_blocks(request)` 获取命中 blocks
   - 命中 blocks 的 block IDs 通过 `req_to_new_blocks[request_id]` 传递

2. **SchedulerOutput** 包含:
   - `scheduled_new_reqs`: 新请求的 `NewRequestData`（含 block_ids）
   - `scheduled_cached_reqs`: 已运行请求的 `CachedRequestData`
   - `num_common_prefix_blocks`: 所有运行请求的公共前缀 block 数

3. **Worker 端**:
   - `GPUModelRunner` 接收 block IDs，更新 `BlockTable`
   - `compute_slot_mapping()` 计算 slot mapping 用于 attention kernel

4. **KV Connector** 的额外信息:
   - `connector.build_connector_meta(scheduler_output)`: 构建 connector 元数据
   - Worker 端 connector 根据元数据决定是否需要从远程加载 KV

### 5.2 Cache 命中对 prefill 的影响

**核心机制**：`num_computed_tokens` 决定 prefill 起始位置

1. **无命中**：`num_computed_tokens = 0`，prefill 从头开始
2. **部分命中**：`num_computed_tokens = num_hit_blocks * block_size`，prefill 从断点开始
3. **全命中**：`max_cache_hit_length = request.num_tokens - 1`，强制重算最后 token

**影响**：
- 减少 prefill 计算量：只计算 `num_new_tokens = num_tokens - num_computed_tokens`
- 减少 KV cache 写入：命中部分不需要重新写入
- 对于长 prompt 的重复前缀，APC 可大幅降低 TTFT

**调度器的处理** (`scheduler.py:696-741`):
```python
num_computed_tokens = num_new_local_computed_tokens + num_external_computed_tokens
num_new_tokens = request.num_tokens - num_computed_tokens
```

### 5.3 Preemption 处理 (swap vs recompute)

**vLLM v1 只支持 recompute，不支持 swap**。

**Preemption 实现** (`scheduler.py:1033-1054`):
```python
def _preempt_request(self, request, timestamp):
    assert request.status == RequestStatus.RUNNING
    self.kv_cache_manager.free(request)          # 释放所有 blocks
    self.encoder_cache_manager.free(request)
    request.status = RequestStatus.PREEMPTED
    request.num_computed_tokens = 0               # 需要完全重算
    request.num_preemptions += 1
    self.waiting.prepend_request(request)         # 放回等待队列
```

**与 v0 的区别**：
- v0 支持 swap（将 KV cache 搬到 CPU，需要时搬回）和 recompute 两种模式
- v1 只支持 recompute：preempted 请求的 KV cache 被完全释放，重新调度时从头计算
- 原因：v1 的设计哲学是 recompute 比 swap 更简单、更可靠，且在大多数场景下性能相当

**KV Connector 的 swap 等价**：
- 通过 offloading 机制（CPU/SSD/remote），v1 可以实现类似 swap 的效果
- 但这是在 connector 层面，不是 scheduler 层面的 preemption swap
- preempted 请求的 blocks 可以先 offload 到 CPU，后续重新加载（但当前实现中 preempt 直接 free）

**Preemption 触发条件** (`scheduler.py:474-519`):
- 当 `allocate_slots()` 返回 None（空间不足）时
- 驱逐最低优先级的 running 请求
- FCFS 策略：驱逐最后加入的请求
- PRIORITY 策略：驱逐优先级最低的请求

### 5.4 Admission Control

**文件**: `kv_cache_manager.py:244-458`, `scheduler.py`

**多级控制**：

1. **Block 级别**: `allocate_slots()` 中检查 `required_blocks > available_blocks`
   ```python
   available_blocks = self.block_pool.get_num_free_blocks() - reserved_blocks
   required_blocks = num_blocks_to_allocate + watermark_blocks
   if required_blocks > available_blocks:
       return None  # 分配失败
   ```

2. **Full sequence 级别**: `full_sequence_must_fit=True` 时，检查完整序列是否放得下
   - 用于 `scheduler_reserve_full_isl` 配置

3. **Watermark**: `scheduler_config.watermark` 保留一定比例的 free blocks
   - 仅对 WAITING/PREEMPTED 请求生效
   - 已 RUNNING 请求不受 watermark 限制

4. **Recycling-aware cap**: SWA 和 chunked-local attention 有每请求 block 上限
   - `max_admission_blocks_per_request` 防止死锁 (`single_type_kv_cache_manager.py:133-145`)

5. **Inflight prefill 保护**: 异步 KV 加载的请求保留 block 空间
   - `reserved_blocks = self._inflight_prefill_reserved_blocks()`

---

## 6. Disaggregated 架构

### 6.1 KV cache connector/transfer

**架构概述**：
vLLM v1 的 disaggregated serving 通过 KV Connector 机制实现。Connector 在 Scheduler 端和 Worker 端各有一个实例，协同完成 KV cache 的跨节点传输。

**核心接口** (`kv_connector/v1/base.py`):

**Scheduler 端**:
- `get_num_new_matched_tokens(request, num_local_computed_tokens)`: 查询远程有多少已缓存 tokens
- `update_state_after_alloc(request, blocks, num_external_computed_tokens)`: 分配后更新状态
- `update_connector_output(output)`: 处理 worker 端返回的传输结果
- `request_finished(request, block_ids)`: 请求完成时，决定是否异步保存 blocks
- `take_events()`: 获取 KV cache 事件

**Worker 端**:
- `handle_preemptions()`: 处理 preempted 或 evicted blocks
- `start_load_kv()`: 开始加载远程 KV（可能异步）
- `wait_for_layer_load(i)`: 等待第 i 层加载完成
- `save_kv_layer(i)`: 开始保存第 i 层的 KV（可能异步）
- `wait_for_save()`: 等待所有保存完成
- `get_finished(ids)`: 返回已完成传输的请求 IDs

**已实现的 Connector**:

1. **NixlConnector** (`kv_connector/v1/nixl/connector.py`):
   - 基于 NIXL（NVIDIA IO 库）的通用 connector
   - 支持 HMA（Hybrid Memory Allocator）
   - 支持 P/D disaggregation 和 offloading
   - 使用 `NixlConnectorScheduler` 和 `NixlConnectorWorker` 分离调度和传输

2. **MooncakeConnector** (`kv_connector/v1/mooncake/mooncake_connector.py`):
   - 基于 Mooncake TransferEngine 的 RDMA connector
   - 支持 P/D disaggregation
   - 异构 TP 支持（不同 TP size 的 P/D 节点）
   - 使用 ZMQ 进行控制面通信
   - 支持 HMA

3. **LMCacheConnector** (`kv_connector/v1/lmcache_connector.py`):
   - 与 LMCache 项目集成
   - 使用 `KVEventAggregator` 聚合多个 worker 的 KV 事件
   - 支持原生和 multi-process 两种模式
   - `vllm_v1_adapter.py` 提供 vLLM v1 的适配层

4. **HF3FSConnector** (`kv_connector/v1/hf3fs/`):
   - 基于 HuggingFace 3FS（高速文件系统）
   - 包含 metadata server 和 mock client
   - 使用 `gather_scatter_helper` 处理 TP 分片

5. **OffloadingConnector** (`kv_connector/v1/offloading_connector.py`):
   - 通用 offloading connector，使用 `OffloadingManager` 框架
   - 支持 CPU/SSD/Remote 等多层级 offload

6. **SimpleCPUOffloadConnector** (`kv_connector/v1/simple_cpu_offload_connector.py`):
   - 简化版 CPU offload connector

7. **MoriioConnector** (`kv_connector/v1/moriio/`):
   - 基于 Moriio 引擎的 connector

### 6.2 与 Mooncake/LMCache 的集成

**Mooncake 集成**:
- `mooncake_connector.py`: 完整的 P/D disaggregation 实现
- 使用 Mooncake 的 `TransferEngine` 进行 RDMA 传输
- ZMQ 控制面：bootstrap server、session 协调
- `mooncake_utils.py`: 辅助工具（bootstrap server、payload 注册）
- `store/` 目录：KV cache store 实现（coordinator、scheduler、worker）
- `rdma_utils.py`: RDMA 传输辅助

**LMCache 集成**:
- `lmcache_connector.py`: 主连接器，委托给 `lmcache_integration/` 模块
- `vllm_v1_adapter.py`: vLLM v1 的适配器
- `multi_process_adapter.py`: 多进程模式适配器
- `utils.py`: 工具函数
- 支持两种模式：
  - **Native**：直接使用 LMCache API
  - **Multi-process**：通过共享内存与独立 LMCache 进程通信

**EC Transfer** (`distributed/ec_transfer/`):
- Encoder Cache Transfer，用于多模态 encoder 输出的跨节点传输
- `ec_connector/base.py`: 基础接口
- `ec_connector/example_connector.py`: 示例实现
- `ec_transfer_state.py`: 传输状态管理

---

## 7. Agent 场景差距分析

### 7.1 当前不足

**1. 无 Session/Group 概念**

vLLM 的 KV cache 管理完全基于单个 request，没有 session 或 agent group 的概念。当一个 agent 的多轮对话作为多个独立请求处理时：
- 不同轮次的请求之间只能通过 APC 的 block hash 匹配复用前缀
- 没有机制保证同一 agent 的请求获得优先级
- 没有跨轮次的 KV cache 保持策略

**2. Block-level 粒度限制**

APC 以 block_size（默认 16 tokens）为最小复用单位：
- Agent 场景中，system prompt 通常不恰好是 block_size 的整数倍
- 每轮对话的新增部分可能不到一个 block，导致部分计算无法缓存
- SGLang 的 token-level 匹配在 agent 多轮场景中更高效

**3. 驱逐策略不感知 Agent 语义**

- LRU 驱逐不考虑 block 属于哪个 agent session
- 高优先级 agent 的 KV cache 可能被低优先级 agent 驱逐
- 没有组感知驱逐（group-aware eviction）机制

**4. Preemption 只支持 Recompute**

- Agent 的长上下文被 preempt 后需要完全重算
- 对于累积了大量上下文的 agent，recompute 代价极高
- 没有 swap 机制保留被 preempt 的 KV cache

**5. 异步加载延迟不可控**

- KV Connector 的异步加载（`WAITING_FOR_REMOTE_KVS` 状态）会延迟调度
- Agent 批量推理时，多个 agent 同时加载 KV 可能造成资源争抢
- 没有基于 agent 优先级的加载调度

**6. 跨节点 KV 复用效率低**

- Agent 场景中，多个 worker 可能同时处理同一 agent 的不同轮次
- Block hash chain 的匹配要求严格的 hash 种子一致性
- 没有 agent-aware 的 KV cache 路由机制

### 7.2 扩展改动点

**1. Agent-Aware Scheduling**（改动量：大）

需要修改的模块：
- `vllm/v1/core/sched/scheduler.py`: 添加 agent group 概念，优先调度同 agent 的请求
- `vllm/v1/core/sched/request_queue.py`: 支持按 agent group 分组的队列
- `vllm/v1/request.py`: 添加 `agent_id` / `session_id` 字段

**2. 跨 Session KV Cache 保持**（改动量：中）

需要修改的模块：
- `vllm/v1/core/kv_cache_manager.py`: 添加 session-level 的 block 引用保持
- `vllm/v1/core/block_pool.py`: 支持按 session 标记 block 优先级
- `vllm/v1/core/single_type_kv_cache_manager.py`: session-aware 驱逐策略

**3. 组感知驱逐**（改动量：中）

需要修改的模块：
- `vllm/v1/core/kv_cache_utils.py`: `FreeKVCacheBlockQueue` 添加 group 标签
- `vllm/v1/core/block_pool.py`: 驱逐时考虑 agent group 权重

**4. Partial Block 支持**（改动量：极大）

需要修改的模块：
- `vllm/v1/core/kv_cache_utils.py`: 重写 hash 计算逻辑
- `vllm/v1/core/kv_cache_coordinator.py`: 支持 partial block 匹配
- `vllm/v1/core/single_type_kv_cache_manager.py`: `find_longest_cache_hit()` 支持 token-level
- `vllm/v1/worker/block_table.py`: BlockTable 支持 partial block 映射
- 基本上需要将整个 APC 体系替换为 RadixCache 类似结构

**5. Swap-for-Preemption**（改动量：大）

需要修改的模块：
- `vllm/v1/core/sched/scheduler.py`: `_preempt_request()` 支持 swap 模式
- `vllm/v1/core/kv_cache_manager.py`: 添加 swap out/in 操作
- 需要引入 CPU swap buffer 管理

### 7.3 改动量评估

| 改动项 | 改动量 | 影响范围 | 风险 |
|--------|--------|----------|------|
| Agent group 概念 | 大 | scheduler, request, queue | 低（新增字段，不破坏现有逻辑） |
| Session-level KV 保持 | 中 | kv_cache_manager, block_pool | 中（修改引用计数逻辑） |
| 组感知驱逐 | 中 | block_pool, free_queue | 中（修改驱逐策略） |
| Partial block 支持 | 极大 | 几乎所有 KV cache 相关模块 | 高（架构性变更） |
| Swap-for-Preemption | 大 | scheduler, kv_cache_manager, worker | 高（引入新的内存管理） |
| Agent-aware 加载调度 | 中 | kv_connector, scheduler | 中（修改异步加载逻辑） |

---

## 8. 关键源码文件索引

| 文件 | 关键类/函数 | 作用 |
|------|------------|------|
| `vllm/v1/core/kv_cache_utils.py` | `KVCacheBlock`, `FreeKVCacheBlockQueue`, `BlockHash`, `hash_block_tokens()` | Block 元数据定义、free queue、hash 计算 |
| `vllm/v1/core/block_pool.py` | `BlockPool`, `BlockHashToBlockMap` | Block 分配/释放/缓存管理 |
| `vllm/v1/core/kv_cache_manager.py` | `KVCacheManager`, `KVCacheBlocks` | KV cache 管理入口，对外接口 |
| `vllm/v1/core/kv_cache_coordinator.py` | `KVCacheCoordinator`, `UnitaryKVCacheCoordinator`, `HybridKVCacheCoordinator` | 多 group KV cache 协调 |
| `vllm/v1/core/single_type_kv_cache_manager.py` | `FullAttentionManager`, `SlidingWindowManager`, `MambaManager`, `ChunkedLocalAttentionManager` | 单类型 KV cache 管理 |
| `vllm/v1/core/sched/scheduler.py` | `Scheduler`, `_preempt_request()` | v1 调度器，preemption 处理 |
| `vllm/v1/worker/block_table.py` | `BlockTable`, `MultiGroupBlockTable` | Worker 端 block table（CPU/GPU 双缓冲） |
| `vllm/v1/worker/gpu/block_table.py` | `BlockTables` | GPU 端 block table（StagedWrite） |
| `vllm/v1/request.py` | `Request`, `update_block_hashes()` | 请求对象，block hash 追踪 |
| `vllm/v1/kv_cache_interface.py` | `KVCacheSpec`, `FullAttentionSpec`, `SlidingWindowSpec` | KV cache 规格定义 |
| `vllm/v1/kv_offload/base.py` | `OffloadingManager`, `OffloadKey`, `CanonicalKVCacheTensor` | Offload 抽象接口 |
| `vllm/v1/kv_offload/cpu/manager.py` | `CPUOffloadingManager` | CPU DRAM offload 管理 |
| `vllm/v1/kv_offload/tiering/fs/manager.py` | `FileSystemTierManager` | SSD offload 管理 |
| `vllm/v1/kv_offload/tiering/obj/manager.py` | `ObjectStoreSecondaryTierManager` | 远程对象存储 offload |
| `vllm/v1/simple_kv_offload/manager.py` | `SimpleCPUOffloadScheduler` | 简化版 CPU offload |
| `vllm/distributed/kv_transfer/kv_connector/v1/base.py` | `KVConnectorBase_V1`, `KVConnectorRole` | KV Connector 基础接口 |
| `vllm/distributed/kv_transfer/kv_connector/v1/nixl/connector.py` | `NixlConnector` | NIXL connector（RDMA） |
| `vllm/distributed/kv_transfer/kv_connector/v1/mooncake/mooncake_connector.py` | `MooncakeConnector` | Mooncake connector（RDMA） |
| `vllm/distributed/kv_transfer/kv_connector/v1/lmcache_connector.py` | `LMCacheConnectorV1` | LMCache connector |
| `vllm/distributed/kv_transfer/kv_connector/v1/hf3fs/hf3fs_connector.py` | `HF3FSConnector` | HF3FS connector |
| `vllm/distributed/kv_transfer/kv_connector/v1/offloading/scheduler.py` | `OffloadingConnectorScheduler` | Offloading connector 调度 |
| `vllm/distributed/ec_transfer/ec_connector/base.py` | `ECConnectorBase` | Encoder Cache Transfer 接口 |
| `vllm/v1/core/kv_cache_metrics.py` | `KVCacheMetricsCollector`, `BlockMetricsState` | KV cache 指标收集 |
| `vllm/config/cache.py` | `CacheConfig` | 缓存配置（block_size, prefix_caching 等） |

---

## 9. 未确认问题

1. **v0 swap 机制是否完全移除**：v1 scheduler 只实现了 recompute，但 `simple_kv_offload/` 中有 swap_blocks 相关代码（`swap_blocks_triton.py`），不确定是否在 v1 调度路径中使用。

2. **Mamba prefix caching 的正确性**：Mamba 的 `find_longest_cache_hit()` 只匹配最后一个 block（`single_type_kv_cache_manager.py:995-1014`），这与 Mamba 的状态依赖性有关，但不确定是否存在边界情况导致状态不一致。

3. **HybridKVCacheCoordinator 的收敛性**：`find_longest_cache_hit()` 使用迭代固定点算法（`kv_cache_coordinator.py:582-692`），理论上保证收敛（长度单调递减），但不确定在极端情况下（多种 attention type 互相约束）是否会出现性能问题。

4. **Block hash 种子跨实例一致性**：`NONE_HASH` 默认使用 `os.urandom(32)`，这意味着不同 vLLM 实例的 block hash 不同，无法跨实例复用 prefix cache。需要设置 `PYTHONHASHSEED` 才能保证一致性。File system offload 的文档提到了这一点，但不确定 Mooncake/NIXL connector 是否有同样的问题。

5. **EC Transfer 的完整流程**：只看到了 `ec_connector/base.py` 和 `example_connector.py`，不确定完整的 encoder cache 跨节点传输流程是否已实现。

6. **Multi-connector 支持**：`kv_connector/v1/multi_connector.py` 存在，表明支持多个 connector 组合使用，但不确定具体的组合规则和优先级。

7. **CUDA Graph 兼容性**：v1 大量使用 CUDA graph，但 KV connector 的异步操作（`start_load_kv`/`wait_for_layer_load`）与 CUDA graph 的交互机制不确定。`LMCacheConnector.requires_piecewise_for_cudagraph()` 暗示了 piecewise 模式的存在。
