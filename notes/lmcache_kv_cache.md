# LMCache KV Cache 源码分析

## 1. KV cache 基本抽象

### 1.1 核心数据结构

LMCache 的核心抽象围绕三层结构展开：

**CacheEngineKey** (`lmcache/utils.py:399-561`)
- `model_name: str` — 模型名称
- `world_size: int` — 全局 world size
- `worker_id: int` — 当前 worker rank
- `chunk_hash: int` — chunk 的 prefix hash（核心标识）
- `dtype: torch.dtype` — KV tensor 数据类型
- `request_configs: Optional[dict]` — 请求级配置（含 tags）
- `tags: Optional[tuple]` — 从 request_configs 中提取的标签元组

**LayerCacheEngineKey** (`lmcache/utils.py:563-636`)
- 继承 CacheEngineKey，额外包含 `layer_id: int`
- 用于 layerwise 存储模式下按层分 key

**MemoryObj** (`lmcache/v1/memory_management.py:185-383`)
- 抽象基类，核心方法：
  - `ref_count_up()` / `ref_count_down()` — 引用计数管理
  - `pin()` / `unpin()` — 钉住/解钉（防止驱逐）
  - `invalidate()` / `is_valid()` — 失效检查
  - `get_size()` / `get_shape()` / `get_dtype()` — 元数据访问
  - `raw_tensor` / `byte_array` / `data_ptr` — 数据访问
- 两个主要实现：
  - `TensorMemoryObj` (line 575-811) — 包装 pinned CPU tensor 或 GPU tensor
  - `BytesBufferMemoryObj` (line 814-937) — 包装 bytes buffer（用于序列化数据）
  - `GDSMemoryObject` (line 940-1059) — GDS slab 上的占位对象

**MemoryObjMetadata** (`lmcache/v1/memory_management.py:108-182`)
- `shape`, `dtype`, `address`, `phy_size` — 物理内存信息
- `ref_count: int`, `pin_count: int` — 引用计数和钉计数
- `fmt: MemoryFormat` — 内存布局格式
- `cached_positions` — 缓存位置信息

**MemoryFormat** (`lmcache/v1/memory_management.py:50-94`)
- `KV_2LTD` — [2, num_layers, num_tokens, hidden_dim]
- `KV_T2D` — [num_tokens, 2, hidden_dim]（layerwise 格式）
- `KV_2TD` — [2, num_tokens, hidden_dim]（blending 格式）
- `KV_MLA_FMT` — [1, num_layers, num_tokens, aligned_head_size]
- `BINARY` / `BINARY_BUFFER` — 压缩/序列化格式
- `EC_TD` — encoder cache 格式

### 1.2 Key 设计

Cache key 的生成是一个 **prefix hash chain** 过程：

**ChunkedTokenDatabase.process_tokens** (`lmcache/v1/token_database.py:367-448`)
1. 将 token 序列按 `chunk_size`（默认 256）切分为 chunks
2. 对每个 chunk 计算 **prefix hash**：`hash_i = hash_func((hash_{i-1}, tokens_i, extra_keys))`
3. 初始 hash 为 `NONE_HASH`（0 或从 vLLM 初始化）
4. 每个 chunk 的 key = `_make_key_by_hash(chunk_hash)` → `CacheEngineKey(model_name, world_size, worker_id, chunk_hash, dtype, request_configs)`

**Hash 函数选择** (`lmcache/v1/token_database.py:123-176`)
- 优先使用 vLLM 的 `sha256_cbor` hash（跨实例一致性）
- 回退到 Python builtin `hash`（需设置 PYTHONHASHSEED 保证一致性）

**Key 的字符串格式** (`lmcache/utils.py:448-456`)
- `model_name@world_size@worker_id@chunk_hash_hex@dtype[@tag%value...]`
- 用于远程存储和序列化

**关键设计决策**：
- Key 中 **不包含 request_id**，仅包含 chunk_hash — 这使得跨请求的 prefix 复用成为可能
- `world_size` 和 `worker_id` 嵌入 key 中，MLA 模式下可折叠为 1 以实现跨部署复用
- `request_configs` 中的 tags 允许请求级差异化缓存

### 1.3 Value 设计

Value 是 **MemoryObj**，其物理存储取决于层级：

| 层级 | 物理存储 | MemoryObj 实现 | 格式 |
|------|---------|----------------|------|
| GPU HBM | torch.Tensor on cuda | TensorMemoryObj | KV_2LTD / KV_T2D / KV_2TD |
| CPU DRAM (pinned) | torch.Tensor on cpu (pinned) | TensorMemoryObj | KV_2LTD / KV_T2D / KV_2TD |
| Disk SSD | 文件系统文件 | DiskCacheMetadata + 通过 CPU staging buffer 加载 | BINARY |
| Remote (Redis/Mooncake/etc.) | 远程存储 | 通过 CPU buffer 中转 | 序列化 bytes |
| GDS | GPU Direct Storage slab | GDSMemoryObject | 通过 GPU buffer 直接读写 |

**LocalCPUBackend.hot_cache** (`lmcache/v1/storage_backend/local_cpu_backend.py:60`)
- 类型：`dict[CacheEngineKey, MemoryObj]`（由 cache policy 决定具体 MutableMapping 类型）
- 存储的是 CPU pinned memory 上的 TensorMemoryObj

**LocalDiskBackend** (`lmcache/v1/storage_backend/local_disk_backend.py`)
- 磁盘文件存储，key 映射为文件路径
- 通过 `PathSharder` 支持多 GPU 分片

**RemoteBackend** (`lmcache/v1/storage_backend/remote_backend.py:27-100`)
- 通过 `RemoteConnector` 与远程存储通信
- 支持 serde（序列化/反序列化）转换
- 支持 MooncakeStore、Redis、InfiniStore、S3 等多种后端

### 1.4 引用计数机制

**TensorMemoryObj** (`lmcache/v1/memory_management.py:657-677`)
- `ref_count_up()`: `meta.ref_count += 1`
- `ref_count_down()`: `meta.ref_count -= 1`；当 `ref_count == 0 && pin_count == 0 && parent_allocator is not None` 时调用 `parent_allocator.free(self)`
- 线程安全：使用 `threading.Lock` 保护

**Pin 机制** (`lmcache/v1/memory_management.py:688-728`)
- `pin()`: `meta.pin_count += 1`；首次 pin 时通知 PinMonitor
- `unpin()`: `meta.pin_count -= 1`；当 `pin_count <= 0 && ref_count <= 0` 时释放内存
- 钉住的对象不会被驱逐（`can_evict` 返回 False）

**驱逐条件** (`lmcache/v1/memory_management.py:782-788`)
- `can_evict = not is_pinned and ref_count == 1`
- ref_count == 1 表示只有 hot_cache 持有引用

**生命周期流程**：
1. `allocate()` → ref_count=1, pin_count=0
2. `submit_put_task()` → `ref_count_up()` → ref_count=2（hot_cache + caller 各持一份）
3. `batched_put()` 完成 → `ref_count_down()` → ref_count=1（仅 hot_cache 持有）
4. `get_blocking()` → `ref_count_up()` → ref_count=2（hot_cache + caller）
5. caller 使用完毕 → `ref_count_down()` → ref_count=1
6. 驱逐时 → `remove()` → `ref_count_down()` → ref_count=0 → `free()`

## 2. 生命周期

### 2.1 Store

**入口**：`LMCacheEngine.store()` (`lmcache/v1/cache_engine.py:372-573`)

完整流程：
1. **Token 处理**：`token_database.process_tokens(tokens, hashes, offsets, mask)` → 生成 `(start, end, CacheEngineKey)` 序列
2. **内存分配**：`storage_manager.allocate(kv_shapes, kv_dtypes)` → 分配 CPU MemoryObj
3. **GPU → CPU 拷贝**：`gpu_connector.batched_from_gpu(memory_objs, starts, ends)` → 通过 GPUConnector 从 vLLM/SGLang 的 paged KV buffer 拷贝到 CPU MemoryObj
4. **写入存储后端**：`storage_manager.batched_put(keys, memory_objs)` → 异步写入 LocalCPUBackend + LocalDiskBackend + RemoteBackend 等
5. **引用计数释放**：`batched_put` 内部对所有 memory_obj 调用 `ref_count_down()`

**Layerwise Store** (`lmcache/v1/cache_engine.py:577-759`)
- 使用 Python generator 实现逐层存储
- 每次 yield 让出控制权，允许 serving engine 执行下一层计算
- key 按 `key.split_layers(num_layers)` 拆分为 per-layer key

### 2.2 Offload

**Offload 的含义**：在 LMCache 中，"offload" 特指 GPU KV cache → CPU MemoryObj → Storage Backend 的过程，即 store 操作本身就是 offload。

**ZMQOffloadServer** (`lmcache/v1/offload_server/zmq_server.py:22-123`)
- 独立线程，通过 ZMQ IPC 接收 offload 请求
- `offload(hashes, slot_mapping, offsets)` → 调用 `lmcache_engine.store(hashes=hashes, slot_mapping=slot_mapping, offsets=offsets)`
- 用于 vLLM v0 模式下的异步 offload

**Offload 粒度**：
- **Chunk 粒度**（默认）：按 chunk_size（256 tokens）切分后逐 chunk offload
- **Layer 粒度**（layerwise 模式）：逐层逐 chunk offload，减少峰值 CPU 内存占用
- **Segment 粒度**（blending 模式）：按特殊分隔符切分为 segment 后 offload

### 2.3 Lookup/Retrieve

**Lookup** (`lmcache/v1/cache_engine.py:1111-1230`)
- 返回值：`int` — 前缀匹配的 token 数量
- 流程：
  1. `token_database.process_tokens()` → 生成 key 序列
  2. `storage_manager.batched_contains(keys, search_range, pin)` → 逐后端前缀匹配
  3. 返回第一个 miss 前的累计 token 数
  4. 若 `pin=True`，记录 `lookup_pins[lookup_id]` 供后续 retrieve 使用

**Retrieve** (`lmcache/v1/cache_engine.py:763-951`)
- 返回值：`torch.Tensor`（bool mask，标记哪些 token 被成功 retrieve）
- 流程：
  1. `_process_tokens_internal()` 或 `_async_process_tokens_internal()`
  2. 根据 `lookup_pins` 确定数据所在后端位置
  3. `storage_manager.batched_get(keys, location)` → 从后端获取 MemoryObj
  4. `gpu_connector.batched_to_gpu(memory_objs, starts, ends)` → CPU MemoryObj → GPU KV buffer
  5. 对每个 memory_obj 调用 `ref_count_down()` 释放引用

**Async Lookup + Prefetch** (`lmcache/v1/cache_engine.py:1301-1357`)
- `async_lookup_and_prefetch()` → 提交到 StorageManager 的 asyncio event loop
- StorageManager 执行 `async_lookup_and_prefetch()` (`lmcache/v1/storage_backend/storage_manager.py:651-826`)
  - 逐后端 `batched_async_contains()` → 确定每层命中 chunk 数
  - 对命中 chunk 执行 `batched_get_non_blocking()` → 异步预取
  - 完成后通过 `async_lookup_server.send_response_to_scheduler()` 通知 scheduler

### 2.4 Load/Use

**GPUConnector** 负责将 CPU MemoryObj 数据写入 serving engine 的 GPU KV buffer：

- `batched_to_gpu(memory_objs, starts, ends, **kwargs)` — CPU → GPU
  - kwargs 包含 `kvcaches`（paged KV buffer）、`slot_mapping`（页表映射）等
  - SGLang 使用 `SGLangGPUConnector`，vLLM 使用 `VLLMPagedKVGPUConnector`

**Retrieve 后的使用**：
- retrieve 返回 `ret_mask`，serving engine 据此跳过已 cached token 的计算
- vLLM: `num_computed_tokens` 增加，scheduler 不再调度这些 token
- SGLang: `prefix_len` 更新，跳过 prefix prefill

### 2.5 Evict/Free

**驱逐触发**：`LocalCPUBackend.allocate()` (`lmcache/v1/storage_backend/local_cpu_backend.py:614-714`)
- 当 `memory_allocator.allocate()` 返回 None（内存不足）时触发
- 调用 `cache_policy.get_evict_candidates(hot_cache)` 获取驱逐候选
- 调用 `batched_remove(evict_keys)` 驱逐
- 支持 busy loop 等待其他请求释放内存

**Cache Policy** (`lmcache/v1/storage_backend/cache_policy/`)
- 支持 LRU、LFU、FIFO、MRU 四种策略
- `BaseCachePolicy` 接口：`init_mutable_mapping()`, `update_on_hit()`, `update_on_put()`, `update_on_force_evict()`, `get_evict_candidates()`
- LRU 使用 `OrderedDict`，LFU 使用自定义计数结构

**驱逐消息**：
- `BatchedMessageSender` 将 ADMIT/EVICT 事件批量发送给 Cache Controller
- Controller 维护全局 KV pool 视图，用于跨实例 lookup

### 2.6 过期和清理

**PinMonitor** (`lmcache/v1/pin_monitor.py`)
- 跟踪所有 pinned MemoryObj 的 pin 时间
- 支持超时自动 unpin（防止 lookup 后未调用 lookup_unpin 导致内存泄漏）

**显式清理**：
- `LMCacheEngine.clear(tokens)` — 清除指定 token 对应的缓存
- `LMCacheEngine.lookup_unpin(lookup_id)` — 释放 lookup 时钉住的缓存
- `LMCacheEngine.close()` — 关闭所有组件

**Freeze 模式** (`lmcache/v1/cache_engine.py:319-344`)
- `freeze(enabled=True)` — 禁止新 store，仅允许从 LocalCPUBackend retrieve
- 保护 hot cache 不被修改

## 3. 内存层级

### 3.1 GPU HBM

- LMCache **不直接管理 GPU HBM** 中的 KV cache
- GPU KV cache 由 serving engine（vLLM/SGLang）的 BlockManager 管理
- LMCache 通过 GPUConnector 读取/写入 GPU KV buffer
- GPUConnector 实现：`VLLMPagedKVGPUConnector`, `SGLangGPUConnector` 等

### 3.2 CPU DRAM

**LocalCPUBackend** (`lmcache/v1/storage_backend/local_cpu_backend.py:39-946`)
- 核心存储层，**始终创建**（其他后端依赖它作为 buffer）
- `hot_cache: MutableMapping[CacheEngineKey, MemoryObj]` — 热缓存字典
- 内存分配器链：
  - `MixedMemoryAllocator` → `PinMemoryAllocator` (pinned CPU) + `BufferAllocator` (bytearray)
  - `PagedTensorMemoryAllocator` — 分页分配（用于 P2P/NIXL/io_uring）
  - `TensorMemoryAllocator` — 连续分配（默认）
- 支持巨大页（hugepages）、NUMA 感知分配、共享内存（shm）

**MixedMemoryAllocator** (`lmcache/v1/memory_management.py:2284-2478`)
- 组合 pinned tensor allocator + buffer allocator
- KV tensor → pinned memory（零拷贝 GPU transfer）
- BINARY_BUFFER → bytearray（序列化数据）

### 3.3 Disk SSD

**LocalDiskBackend** (`lmcache/v1/storage_backend/local_disk_backend.py`)
- 异步磁盘 I/O，通过 `AsyncPQThreadPoolExecutor` 管理任务优先级
- 优先级：prefetch(0) > delete(1) > put(2)
- 支持 `PathSharder` 按 GPU 分片存储路径
- 支持 Rust raw block 后端（io_uring / O_DIRECT）实现零拷贝

**GdsBackend** (`lmcache/v1/storage_backend/gds_backend.py`)
- GPU Direct Storage (GDS) 后端
- 直接在 GPU VRAM 和 NVMe 之间传输，绕过 CPU
- 使用 `CuFileMemoryAllocator` 注册 GPU buffer

### 3.4 Remote Memory

**RemoteBackend** (`lmcache/v1/storage_backend/remote_backend.py:27-100`)
- 通过 `RemoteConnector` 抽象与远程存储通信
- 支持 serde（序列化/反序列化）：naive、cachegen（有损压缩）
- 连接管理：自动重连（10秒冷却期）
- 写入时序列化 → 远程 put；读取时远程 get → 反序列化

**支持的远程存储**（通过 Connector 适配）：
- Redis / Redis Sentinel / Redis SSL
- MooncakeStore（RDMA）
- InfiniStore（InfiniBand）
- S3（Amazon S3 / S3 Express）
- FS（本地文件系统，通过 remote 接口）
- Blackhole（空后端，用于测试）
- Mock（模拟延迟/带宽）
- 自定义 plugin connector

### 3.5 层级迁移机制

**StorageManager** (`lmcache/v1/storage_backend/storage_manager.py:218-1421`)
- 管理所有后端，协调层级间数据迁移
- 后端创建顺序（`CreateStorageBackends`，`__init__.py:111-336`）：
  1. PDBackend（如果 enable_pd）
  2. LocalCPUBackend（始终创建）
  3. P2PBackend（如果 enable_p2p）
  4. NixlStorageBackend（如果 enable_nixl_storage）
  5. LocalDiskBackend（如果 local_disk 配置）
  6. GdsBackend（如果 gds_path 配置）
  7. MaruBackend（如果 maru_path 配置）
  8. RemoteBackend（如果 remote_url 或 remote_storage_plugins 配置）
  9. Storage plugins（动态加载）

**写入路径**（`batched_put`，line 383-432）：
- 数据始终先写入 allocator_backend（LocalCPUBackend 或 PDBackend）
- 对其他后端，通过 `allocate_and_copy_objects()` 分配新 MemoryObj 并拷贝数据
- 各后端异步 `batched_submit_put_task()`

**读取路径**（`batched_get`，line 479-512）：
- 按后端顺序搜索：LocalCPU → LocalDisk → Remote
- 从非 CPU 后端读取后，**自动 write-back 到 LocalCPUBackend**（缓存提升）
- 前缀匹配：逐后端检查连续命中 chunk

**Prefetch 路径**（`async_lookup_and_prefetch`，line 651-826）：
- 逐后端 `batched_async_contains()` → 确定每层命中范围
- 对命中 chunk 执行 `batched_get_non_blocking()` → 异步加载到 CPU
- 完成后通知 scheduler

## 4. Prefix cache / reuse 机制

### 4.1 Cache key 生成

**Prefix Hash Chain** (`lmcache/v1/token_database.py:268-294`)

```
hash_0 = NONE_HASH
hash_1 = hash_func((hash_0, tuple(tokens[0:chunk_size]), ()))
hash_2 = hash_func((hash_1, tuple(tokens[chunk_size:2*chunk_size]), ()))
...
```

- 每个 chunk 的 hash 依赖于前一个 chunk 的 hash → **prefix 敏感**
- 相同 prefix 的 token 序列会产生相同的 hash chain → **自动 prefix 匹配**
- `extra_keys` 预留给 multi-modal / LoRA 等场景，当前未使用

**Hash 函数选择**：
- `builtin` — Python 内置 `hash()`（需 PYTHONHASHSEED 一致）
- `sha256_cbor` — vLLM 的 SHA256+CBOR hash（跨进程一致，推荐分布式场景）

### 4.2 Prefix 匹配

**Lookup 的前缀匹配** (`lmcache/v1/cache_engine.py:1198-1221`)

```python
hit_chunks, block_mapping = storage_manager.batched_contains(keys, search_range, pin)
for idx, (start, end, key) in enumerate(chunk_info_list):
    if idx < hit_chunks:
        res = end  # 累加命中 token 数
        continue
    return res  # 第一个 miss 处返回
```

- **严格前缀匹配**：从第一个 chunk 开始连续匹配，第一个 miss 即停止
- 不支持中间空洞匹配（non-contiguous hit）
- `batched_contains` 实现在 `StorageBackendInterface.batched_contains()` (`abstract_backend.py:272-293`)：逐 key 检查 `contains()`，第一个 miss 即 break

**跨后端前缀匹配** (`storage_manager.py:967-1005`)
- 逐后端检查：先 LocalCPU，再 LocalDisk，再 Remote
- 每个后端返回其连续命中 chunk 数
- 总命中数 = 各后端命中数之和（前缀拼接）

### 4.3 Partial hit

**支持 partial hit**：
- Lookup 返回的 `res` 可以小于总 token 数
- Serving engine 对未命中部分执行正常 prefill
- Retrieve 时，`ret_mask` 标记实际 retrieve 的 token 范围

**Retrieve 的 partial 处理** (`cache_engine.py:1678-1783`)
- 如果某个 chunk 的 `batched_get` 返回 None（被驱逐），标记 `last_failed_block_start`
- 所有 `end > last_failed_block_start` 的 chunk 被丢弃
- `ret_mask[last_failed_block_start:] = False` — 确保返回的 hit 是连续前缀

### 4.4 跨实例复用

**完整路径**：

1. **Store（实例 A）**：
   - `LMCacheEngine.store()` → GPU → CPU MemoryObj → LocalCPUBackend + RemoteBackend
   - RemoteBackend 通过 Connector 写入远程存储（Redis/Mooncake/S3）
   - Cache Controller 收到 ADMIT 事件，更新全局 KV pool

2. **Lookup（实例 B）**：
   - Scheduler 调用 `lookup_client.lookup(token_ids)` → 通过 ZMQ/RPC 发送到 LookupServer
   - LookupServer 调用 `lmcache_engine.lookup()` → 检查 LocalCPU + LocalDisk + Remote
   - 返回命中 token 数

3. **Prefetch（实例 B）**：
   - `async_lookup_and_prefetch()` → 对 RemoteBackend 命中的 chunk 执行 `batched_get_non_blocking()`
   - 数据从远程存储加载到 CPU MemoryObj
   - 自动 write-back 到 LocalCPUBackend

4. **Retrieve（实例 B）**：
   - `LMCacheEngine.retrieve()` → `storage_manager.batched_get()` → 从 LocalCPUBackend 获取
   - `gpu_connector.batched_to_gpu()` → CPU → GPU

**Cache Controller 的角色** (`lmcache/v1/cache_controller/controllers/kv_controller.py:55-105`)
- 维护全局 KV pool：`(instance_id, worker_id) → {location → set[chunk_hash]}`
- 处理 ADMIT/EVICT 事件，更新全局视图
- 支持 pin/move/compress/decompress 等操作
- 支持 full sync（全量同步）机制

### 4.5 数据共享方式

**跨实例数据共享**：
- **Remote Backend**：数据序列化后存储在远程 KV store（Redis/Mooncake/S3），实例 B 通过网络获取
- **P2P Backend**：点对点直接传输，使用 NIXL 进行 RDMA/GPU Direct 传输
- **PD Backend**：Prefill/Decode 分离架构，sender 将 KV cache 传输给 receiver
- **MooncakeStore**：基于 Mooncake 的分布式存储，支持 RDMA

**同实例数据共享**：
- **引用计数**：多个 consumer 共享同一 MemoryObj，通过 ref_count 管理
- **Pin 机制**：lookup 时 pin 防止驱逐，使用完毕后 unpin
- **零拷贝**：pinned CPU memory → GPU 通过 DMA 传输，无需额外拷贝

## 5. 与 vLLM 的集成

### 5.1 v1 adapter 设计

**LMCacheConnectorV1Impl** (`lmcache/integration/vllm/vllm_v1_adapter.py:453-`)

- 实现 vLLM v1 的 `KVConnectorBase_V1` 接口
- 两个角色：
  - **Scheduler**：负责 lookup（确定 cache hit 范围）、调度决策
  - **Worker**：负责 store（保存 KV cache）、retrieve（加载 KV cache 到 GPU）

**核心方法**：
- `update_state_after_alloc()` — scheduler 端，根据 lookup 结果调整调度
- `build_connector_metadata()` — scheduler 端，构建 per-request 的 load/save metadata
- `apply_kv_load()` — worker 端，从 LMCache retrieve KV cache 到 GPU
- `store_kv_cache()` — worker 端，将 GPU KV cache store 到 LMCache

**RequestTracker** (`vllm_v1_adapter.py:111-275`)
- 跟踪每个请求的状态：token_ids、allocated_block_ids、num_saved_tokens、num_lmcache_cached_tokens
- 支持 preempted 请求的恢复

**ReqMeta** (`vllm_v1_adapter.py:278-436`)
- Per-request 的 load/save 元数据
- 包含 token_ids、slot_mapping、save_spec、load_spec、disagg_spec

### 5.2 集成方式

**Hook 模式**（非替换 BlockManager）：
- vLLM v1 引入 `KVConnectorBase_V1` 接口作为 KV cache 转移的 hook 点
- LMCache 实现 `KVConnectorBase_V1`，通过 `kv_transfer_config.kv_connector` 配置注入
- vLLM 的 BlockManager 仍然管理 GPU block 分配
- LMCache 在 BlockManager 之外管理 CPU/remote 的 KV cache 存储

**关键交互点**：
- Scheduler 在调度前调用 `update_state_after_alloc()` 获取 cache hit 信息
- Worker 在 model forward 前调用 `apply_kv_load()` 加载 cached KV
- Worker 在 model forward 后调用 `store_kv_cache()` 保存新 KV

### 5.3 交互流程

**Prefill 请求的完整流程**：

1. **Scheduler - Lookup**：
   - 新请求到达，scheduler 调用 `lookup_client.lookup(token_ids)`
   - 返回 `num_hit_tokens`，scheduler 据此减少需要 prefill 的 token 数

2. **Scheduler - Schedule**：
   - 根据 `num_hit_tokens` 分配 GPU block（仅分配未命中部分）
   - 构建 `LoadSpec`（需要加载的 token 范围）和 `SaveSpec`（需要保存的 token 范围）

3. **Worker - Load**：
   - 收到 `ReqMeta`，调用 `lmcache_engine.retrieve(token_ids, mask)`
   - KV cache 从 CPU/remote 加载到 GPU paged KV buffer
   - 返回 `ret_mask`，标记实际加载的 token

4. **Worker - Forward**：
   - 仅对未 cached 的 token 执行 attention 计算

5. **Worker - Save**：
   - 调用 `lmcache_engine.store(token_ids, mask)`
   - GPU KV cache → CPU MemoryObj → Storage Backends

## 6. 与 SGLang 的集成

### 6.1 SGLang adapter 设计

**LMCacheConnector** (`lmcache/integration/sglang/sglang_adapter.py:108-212`)

- 直接封装 `LMCacheEngine`，不经过 vLLM 的 KVConnector 接口
- 核心方法：
  - `load_kv(load_metadata)` — 调用 `lmcache_engine.retrieve()`
  - `store_kv(store_metadata)` — 调用 `lmcache_engine.store()`
  - `get_kv_events()` — 获取 KV 事件（用于 radix tree 同步）

**LMCacheLayerwiseConnector** (`sglang_adapter.py:214-347`)
- 继承 LMCacheConnector，支持逐层 retrieve
- `start_load_kv()` — 先 lookup，再启动 layerwise retrieve generator
- `load_kv_layerwise(layer_id)` — 逐层推进 retrieve
- `store_kv()` — 使用 layerwise store generator

**初始化** (`init_lmcache_engine`, line 48-105)
- 直接创建 `LMCacheEngine`，传入 SGLang 的 model config
- 使用 `CreateGPUConnector(config, metadata, EngineType.SGLANG)` 创建 SGLang 专用 GPU connector
- broadcast 函数使用 mock（SGLang 不需要跨 rank broadcast）

### 6.2 多进程 adapter

**LMCacheMPConnector** (`lmcache/integration/sglang/multi_process_adapter.py:76-`)

- SGLang 多进程模式下的 LMCache connector
- 通过 ZMQ MessageQueue 与独立 LMCache daemon 通信
- 核心方法：
  - `lookup_kv()` — 发送 LOOKUP 请求到 daemon
  - `retrieve_kv()` — 发送 RETRIEVE 请求，daemon 执行 L1→GPU 传输
  - `store_kv()` — 发送 STORE 请求到 daemon
  - `release_pending()` — 释放 lookup 时持有的读锁
  - `end_session()` — 请求结束清理

**架构**：
- SGLang worker 进程 ← ZMQ → LMCache daemon 进程
- daemon 持有 LMCacheEngine 实例，管理所有存储后端
- worker 通过 IPC 传递 CUDA tensor handle（CudaIPCWrapper）

### 6.3 交互流程

**SGLang 单进程模式**：
1. Scheduler 调用 `lookup()` → `lmcache_engine.lookup(token_ids)`
2. Worker 调用 `load_kv()` → `lmcache_engine.retrieve(token_ids, mask)`
3. Worker forward（仅计算未 cached token）
4. Worker 调用 `store_kv()` → `lmcache_engine.store(token_ids, mask)`

**SGLang 多进程模式**：
1. Worker 发送 LOOKUP → daemon 执行 lookup + prefetch
2. Worker 发送 RETRIEVE → daemon 执行 retrieve（L1→GPU）
3. Worker forward
4. Worker 发送 STORE → daemon 执行 store

## 7. Storage Backend

### 7.1 抽象接口

**StorageBackendInterface** (`lmcache/v1/storage_backend/abstract_backend.py:27-323`)

核心方法：
- `contains(key, pin)` — 检查 key 是否存在
- `batched_contains(keys, pin)` — 批量前缀匹配检查
- `batched_submit_put_task(keys, objs, transfer_spec)` — 异步写入
- `get_blocking(key)` — 同步读取
- `get_non_blocking(key)` — 异步读取
- `batched_get_blocking(keys)` — 批量同步读取
- `batched_get_non_blocking(keys)` — 批量异步读取
- `pin(key)` / `unpin(key)` — 钉住/解钉
- `remove(key)` — 删除
- `touch_cache()` — 更新缓存策略（LRU 等）
- `close()` — 关闭

**AllocatorBackendInterface** (line 325-421)
- 扩展 StorageBackendInterface，增加内存分配能力
- `allocate(shapes, dtypes, fmt, eviction)` — 分配 MemoryObj
- `batched_allocate()` — 批量分配
- `initialize_allocator(config, metadata)` — 创建内存分配器
- `get_memory_allocator()` — 获取底层分配器

**StoragePluginInterface** (line 424-460)
- 可插拔存储后端接口，支持动态加载

### 7.2 CPU adapter

**LocalCPUBackend** (`local_cpu_backend.py:39-946`)

- 实现 `AllocatorBackendInterface`
- `hot_cache` — 核心 KV 存储（CacheEngineKey → MemoryObj）
- `memory_allocator` — MixedMemoryAllocator / PagedTensorMemoryAllocator
- `cache_policy` — LRU/LFU/FIFO/MRU 驱逐策略
- `batched_msg_sender` — 与 Cache Controller 通信

**关键特性**：
- 同步 put（`submit_put_task` 直接写入 hot_cache）
- 分配时支持驱逐（eviction）
- 支持 freeze 模式（禁止新写入）
- 支持 hot cache 动态开关

### 7.3 Disk adapter

**LocalDiskBackend** (`local_disk_backend.py`)

- 实现 `StorageBackendInterface`（非 AllocatorBackend）
- 依赖 LocalCPUBackend 作为 staging buffer
- 异步 I/O：通过 `AsyncPQThreadPoolExecutor` 管理任务队列
- 任务优先级：prefetch > delete > put
- 支持 PathSharder（按 GPU 分片存储路径）
- 支持 Rust raw block 后端（io_uring / O_DIRECT）

### 7.4 Remote adapter

**RemoteBackend** (`remote_backend.py:27-100`)

- 实现 `StorageBackendInterface`
- 通过 `RemoteConnector` 与远程存储通信
- 支持 serde 转换（序列化/反序列化）
- 连接管理：自动重连（10秒冷却期）
- MLA 模式下支持 worker_id 折叠为 0

**RemoteConnector** (`connector/base_connector.py`)
- 抽象接口：`exists()`, `set()`, `get()`, `batched_exists()`, `batched_set()`, `batched_get()`
- 实现类：RedisConnector, MooncakeStoreConnector, InfiniStoreConnector, S3Connector, FSConnector 等

### 7.5 Connector 设计

**ConnectorManager** (`connector/__init__.py:214-356`)
- 维护 `ConnectorAdapter` 列表
- 根据 URL scheme 选择合适的 adapter
- 支持动态加载 plugin connector

**ConnectorAdapter** (line 157-171)
- 抽象接口：`can_parse(url)`, `create_connector(context)`
- 每个 adapter 对应一种 URL scheme

**ConnectorClientBase** (`native_clients/connector_client_base.py:10-166`)
- 泛型基类，包装 native C++ client
- 通过 event fd + asyncio event loop 实现异步完成通知
- 支持 `batch_get`, `batch_set`, `batch_exists` 的同步和异步版本
- 使用 `drain_completions()` 获取 C++ 端完成的事件

**支持的 Connector 类型**：
- `redis://` — Redis / Redis Sentinel / Redis SSL
- `lm://` — LMCache 自有协议
- `infinistore://` — InfiniStore (InfiniBand)
- `mooncakestore://` — MooncakeStore (RDMA)
- `blackhole://` — 空后端
- `audit://` — 审计后端
- `fs://` — 文件系统
- `s3://` — Amazon S3
- `mock://` — 模拟后端
- `plugin://` — 自定义 plugin

## 8. Lookup Client 架构

### 8.1 抽象接口

**LookupClientInterface** (`lmcache/v1/lookup_client/abstract_client.py:10-77`)

- `lookup(token_ids, lookup_id, request_configs)` → `Optional[int]` — 执行 lookup，返回命中 token 数
- `lookup_cache(lookup_id)` → `Optional[int]` — 查询已缓存的结果
- `supports_producer_reuse()` → `bool` — 是否支持 producer KV 复用
- `clear_lookup_status(lookup_id)` — 清除临时状态
- `close()` — 关闭

### 8.2 LMCache lookup client

**LMCacheLookupClient** (`lmcache_lookup_client.py:24-177`)

- 通过 `RpcClientTransport`（ZMQ REQ-REP）与 LookupServer 通信
- 非 blending 模式：发送 hashes + offsets（减少数据量）
- Blending 模式：发送完整 token_ids（blender 需要输入 embedding）
- 维护 `reqs_status: dict[str, int]` 缓存 lookup 结果
- 支持多 rank 结果聚合（取最小值）

**LMCacheLookupServer** (`lmcache_lookup_client.py:179-293`)

- 在独立线程中处理 lookup 请求
- 调用 `lmcache_engine.lookup(hashes=hashes, offsets=offsets, lookup_id=lookup_id, pin=True)`
- 返回命中 token 数（4 字节 big-endian）

### 8.3 Mooncake lookup client

**MooncakeLookupClient** (`mooncake_lookup_client.py:22-96`)

- 直接使用 `MooncakeDistributedStore` 的 `batch_is_exist()` 检查 key 存在性
- 不经过 LMCacheEngine，直接与 Mooncake 存储交互
- 不支持 blending
- 适用于跨实例复用场景（无需 LMCache lookup server）

### 8.4 异步 lookup client

**LMCacheAsyncLookupClient** (`lmcache_async_lookup_client.py`)

- 基于 ZMQ DEALER-ROUTER 模式
- 支持非阻塞 lookup + prefetch
- 与 `StorageManager.async_lookup_and_prefetch()` 配合
- prefetch 完成后通过 ZMQ 通知 scheduler

**LookupClientFactory** (`factory.py:36-252`)

- 根据配置创建合适的 lookup client：
  - `external_lookup_client` → MooncakeLookupClient
  - `enable_scheduler_bypass_lookup` → LMCacheBypassLookupClient（直接调用 engine）
  - `enable_async_loading` → LMCacheAsyncLookupClient
  - 默认 → LMCacheLookupClient（ZMQ）
- 可选包装：HitLimitLookupClient（命中率限制）、ChunkStatisticsLookupClient（统计）

## 9. Cache Controller

### 9.1 KV controller

**KVController** (`lmcache/v1/cache_controller/controllers/kv_controller.py:55-105`)

- 维护全局 KV pool：`(instance_id, worker_id) → {location → set[chunk_hash]}`
- 通过 `RegistryTree` 存储元数据
- 支持操作：
  - `handle_batched_kv_operations()` — 处理批量 ADMIT/EVICT 事件
  - `lookup()` — 全局 lookup（跨实例）
  - `pin()` / `move()` / `compress()` / `decompress()` — KV 管理
  - `clear()` — 清除指定实例的 KV
  - `check_finish()` — 检查事件完成状态

**FullSyncTracker** (line 68-72)
- 跟踪全量同步进度
- 支持配置完成阈值（默认 80%）和超时

### 9.2 Prefetch 机制

**Async Lookup + Prefetch** (`cache_engine.py:1301-1357` + `storage_manager.py:651-826`)

完整流程：
1. Scheduler 调用 `async_lookup_and_prefetch(lookup_id, tokens)`
2. 提交到 StorageManager 的 asyncio event loop
3. StorageManager 逐后端执行：
   a. `batched_async_contains()` — 确定每层命中 chunk 数
   b. 对命中 chunk 执行 `batched_get_non_blocking()` — 异步加载到 CPU
4. 所有 tier 加载完成后，通过 `async_lookup_server.send_response_to_scheduler()` 通知
5. Scheduler 收到通知，调度 retrieve 操作

**Prefetch 优先级**：
- 三类后端：(1) sync lookup + sync retrieval (CPU), (2) sync lookup + async retrieval (disk), (3) async lookup + async retrieval (P2P)
- 前缀模式：先加载 prefix chunk，后加载 suffix chunk

## 10. Offload Server

### 10.1 架构

**OffloadServerInterface** (`lmcache/v1/offload_server/abstract_server.py:11-37`)

- `offload(hashes, slot_mapping, offsets)` → `bool`
- `close()`

### 10.2 ZMQ server

**ZMQOffloadServer** (`lmcache/v1/offload_server/zmq_server.py:22-123`)

- 独立线程，ZMQ REP socket
- 接收 `OffloadMsg`（msgpack 编码），包含 hashes、slot_mapping、offsets
- 调用 `lmcache_engine.store(hashes=hashes, slot_mapping=slot_mapping, offsets=offsets)`
- 返回 `OffloadRetMsg(success=True/False)`

**用途**：
- vLLM v0 模式下的异步 offload
- Worker 在 prefill 完成后，通过 ZMQ 请求 offload server 将 KV cache 异步保存

## 11. Blend KV

### 11.1 Blend 机制

**CacheBlend** 核心思想：在 prefill 时，如果某段 KV cache 的 fingerprint 与已缓存 chunk 匹配，可以跳过该段的计算，直接复用 cached KV。

**SegmentTokenDatabase** (`lmcache/v1/token_database.py:451-579`)
- 按 `blend_special_str`（默认 " # # "）将 token 序列切分为 segments
- 每个 segment 独立计算 hash，不使用 prefix hash chain
- 允许非前缀位置的匹配（与 ChunkedTokenDatabase 的严格前缀匹配不同）

**BlendTokenRangeMatcherV3** (`lmcache/v1/multiprocess/modules/blend_v3.py:85-150`)
- V3 matcher：token-level probe + full-hash collision rejection
- 使用 Fibonacci hashing 常数的 rolling hash
- 维护 `token_hash → start position` 映射
- 支持 `match_sub_sequence()` 在任意偏移位置查找匹配

### 11.2 多进程 blend

**BlendV3 Module** (`lmcache/v1/multiprocess/modules/blend_v3.py`)

- 作为 `MPCacheEngine` 的 EngineModule 插入
- 注册 `CB_REGISTER_ROPE_V3` 处理器，接收 RoPE 状态
- 支持：
  - `cb_unified_lookup()` — 统一 lookup（prefix + sparse）
  - `cb_unified_retrieve()` — 统一 retrieve
  - `cb_register_token_hashes()` — 注册新 token hash
  - `cb_unregister_token_hashes()` — 注销 token hash

**_CBUnifiedJob** (line 66-82)
- Per-request poll state，支持非阻塞操作
- 两阶段：prefix leg → sparse leg
- Prefix leg：标准前缀匹配
- Sparse leg：token-level 匹配（允许非连续位置）

## 12. Agent 场景差距分析

### 12.1 当前不足

**1. 严格前缀匹配限制**
- ChunkedTokenDatabase 使用 prefix hash chain，仅支持从序列开头的连续前缀匹配
- Agent 场景中，多轮对话的 system prompt + 工具定义是共享前缀，但中间轮次的 KV cache 无法被后续请求复用（因为 prefix hash chain 在第一轮不同的 user input 后就分叉了）
- 源码位置：`token_database.py:357-364`（`_prefix_hash` 方法）

**2. 无 request-level 隔离和优先级**
- Cache key 不包含 request_id，所有请求共享同一 KV pool
- Agent 场景中，高优先级请求（当前执行的任务）可能被低优先级请求（历史对话）的 cache 驱逐
- 驱逐策略（LRU/LFU）不考虑请求优先级
- 源码位置：`local_cpu_backend.py:658-679`（allocate 中的驱逐逻辑）

**3. 无 partial block 复用**
- 最小复用粒度是 chunk_size（默认 256 tokens）
- Agent 场景中，共享前缀可能不是 chunk_size 的整数倍，导致部分 token 无法复用
- 源码位置：`token_database.py:408-411`（mask 中 False 数量必须是 chunk_size 倍数）

**4. 无主动 prefetch 策略**
- Prefetch 仅在 lookup 时触发（reactive），无 proactive prefetch
- Agent 场景中，可以预测下一步需要的 KV cache（如工具调用后的 continuation），但 LMCache 没有预测性加载机制
- 源码位置：`cache_engine.py:1301-1357`（`async_lookup_and_prefetch` 仅在 scheduler 调用时触发）

**5. 无 KV cache 版本/一致性管理**
- 同一 prefix 的 KV cache 可能因模型参数更新而失效
- Agent 长时间运行中，可能需要 invalidate 旧 cache
- 当前仅支持 `clear()` 全量清除，无细粒度 invalidation

**6. 无跨 agent 实例的 KV cache 共享协议**
- 虽然支持 RemoteBackend 和 Cache Controller，但缺少 agent-aware 的共享语义
- 多个 agent 实例可能需要共享"工具定义"的 KV cache，但当前复用依赖 prefix hash 完全匹配

**7. 同步 lookup 阻塞调度**
- 默认 lookup 是同步的，会阻塞 scheduler
- Agent 批量推理中，多个请求同时 lookup 可能成为瓶颈
- 异步模式（`enable_async_loading`）存在但不是默认

### 12.2 作为 agent-aware KV cache pool 基础的可行性

**优势**：
1. **成熟的分层存储架构**：GPU → CPU → Disk → Remote，层级间自动迁移
2. **灵活的存储后端插件系统**：StoragePluginInterface 支持动态加载自定义后端
3. **跨实例复用基础设施**：RemoteBackend + Cache Controller + Lookup Client 已实现
4. **引用计数和内存管理**：完善的 ref_count + pin_count 机制，防止内存泄漏
5. **多引擎适配**：已支持 vLLM 和 SGLang，GPUConnector 抽象良好
6. **Blend 机制**：SegmentTokenDatabase 和 CacheBlend 提供了非前缀匹配的原型

**劣势**：
1. **Prefix hash chain 是硬编码的**：要支持 agent 场景的灵活匹配，需要重构 key 生成逻辑
2. **驱逐策略不感知请求语义**：需要增加 priority-aware eviction
3. **无请求级 KV cache 生命周期管理**：需要增加 per-request scope 的 cache 管理
4. **同步 lookup 默认路径**：需要默认启用异步 lookup

### 12.3 通用接入 SGLang/vLLM 的设计启示

**从 LMCache 架构中得到的设计启示**：

1. **GPUConnector 抽象是关键**：
   - LMCache 通过 GPUConnector 隔离了 serving engine 的 KV buffer 布局差异
   - 通用 KV cache pool 应采用类似抽象：`from_gpu()` / `to_gpu()` 接口

2. **StorageManager 作为中间层**：
   - 统一管理多后端，协调层级迁移
   - 通用 pool 应有类似组件，但需要增加 agent-aware 的调度逻辑

3. **LookupClient/Server 分离**：
   - 将 lookup 逻辑与 cache engine 解耦，支持远程 lookup
   - 通用 pool 应支持多种 lookup 策略（prefix、semantic、tag-based）

4. **Cache Controller 的全局视图**：
   - 维护跨实例的 KV pool 元数据
   - 通用 pool 应扩展 controller，增加 agent 语义（如工具定义共享、session 管理）

### 12.4 扩展改动点

**要使 LMCache 适合 agent 批量推理，需要以下改动**：

1. **Key 生成重构**：
   - 增加 `TagBasedKey`：支持按 tag（如 "system_prompt", "tool_definition"）索引
   - 增加 `SemanticKey`：支持语义相似度匹配（而非精确 hash 匹配）
   - 保留 `PrefixHashKey` 作为默认，向后兼容

2. **驱逐策略增强**：
   - `PriorityAwareEviction`：考虑请求优先级
   - `SessionAwareEviction`：同一 agent session 的 cache 优先保留
   - `CostAwareEviction`：计算成本高的 KV cache 优先保留

3. **Proactive Prefetch**：
   - `PrefetchPredictor` 接口：预测下一步需要的 KV cache
   - Agent 场景实现：基于工具调用模式预测
   - 集成点：`CacheEngine` 增加 `predictive_prefetch()` 方法

4. **请求级生命周期**：
   - `CacheScope`：per-request / per-session / global
   - `invalidate(scope, condition)`：细粒度 invalidation
   - 集成点：`CacheEngineKey` 增加 `scope` 字段

5. **异步 lookup 默认化**：
   - 将 `enable_async_loading` 默认设为 True
   - 优化 `AsyncMultiSerializer` 的并发度

6. **Agent-aware Cache Controller**：
   - 增加 `AgentSessionManager`：管理 agent session 的 KV cache 生命周期
   - 增加 `ToolCacheManager`：管理工具定义的共享 KV cache
   - 增加 `CrossAgentSharingPolicy`：跨 agent 实例的共享策略

## 13. 关键源码文件索引

| 文件 | 关键类/函数 | 作用 |
|------|------------|------|
| `lmcache/v1/cache_engine.py` | `LMCacheEngine` | 核心 cache engine，store/retrieve/lookup 入口 |
| `lmcache/v1/cache_engine.py` | `LMCacheEngineBuilder` | Engine 工厂，get_or_create/destroy |
| `lmcache/v1/manager.py` | `LMCacheManager` | 组件生命周期管理 |
| `lmcache/v1/metadata.py` | `LMCacheMetadata` | 元数据（model_name, kv_shape, kv_dtype 等） |
| `lmcache/v1/token_database.py` | `ChunkedTokenDatabase` | Chunk 粒度 token → key 转换（prefix hash chain） |
| `lmcache/v1/token_database.py` | `SegmentTokenDatabase` | Segment 粒度 token → key 转换（blending） |
| `lmcache/v1/memory_management.py` | `TensorMemoryObj` | CPU/GPU tensor 包装，引用计数 |
| `lmcache/v1/memory_management.py` | `MixedMemoryAllocator` | Pinned + Buffer 混合分配器 |
| `lmcache/v1/memory_management.py` | `MemoryFormat` | 内存布局枚举（KV_2LTD, KV_T2D 等） |
| `lmcache/utils.py` | `CacheEngineKey` | Cache key 数据类 |
| `lmcache/utils.py` | `LayerCacheEngineKey` | Per-layer cache key |
| `lmcache/v1/config.py` | `LMCacheEngineConfig` | 配置类 |
| `lmcache/v1/storage_backend/abstract_backend.py` | `StorageBackendInterface` | 存储后端抽象接口 |
| `lmcache/v1/storage_backend/abstract_backend.py` | `AllocatorBackendInterface` | 带分配能力的存储后端接口 |
| `lmcache/v1/storage_backend/local_cpu_backend.py` | `LocalCPUBackend` | CPU DRAM 存储后端（热缓存） |
| `lmcache/v1/storage_backend/local_disk_backend.py` | `LocalDiskBackend` | Disk SSD 存储后端 |
| `lmcache/v1/storage_backend/remote_backend.py` | `RemoteBackend` | 远程存储后端 |
| `lmcache/v1/storage_backend/p2p_backend.py` | `P2PBackend` | 点对点传输后端 |
| `lmcache/v1/storage_backend/pd_backend.py` | `PDBackend` | Prefill/Decode 分离后端 |
| `lmcache/v1/storage_backend/gds_backend.py` | `GdsBackend` | GPU Direct Storage 后端 |
| `lmcache/v1/storage_backend/storage_manager.py` | `StorageManager` | 多后端管理器，协调层级迁移 |
| `lmcache/v1/storage_backend/cache_policy/` | `LRUCachePolicy` 等 | 缓存驱逐策略 |
| `lmcache/v1/storage_backend/connector/__init__.py` | `ConnectorManager`, `CreateConnector` | Connector 工厂和管理 |
| `lmcache/v1/storage_backend/native_clients/connector_client_base.py` | `ConnectorClientBase` | Native C++ connector client 基类 |
| `lmcache/v1/lookup_client/abstract_client.py` | `LookupClientInterface` | Lookup client 抽象接口 |
| `lmcache/v1/lookup_client/lmcache_lookup_client.py` | `LMCacheLookupClient/Server` | ZMQ RPC lookup client/server |
| `lmcache/v1/lookup_client/mooncake_lookup_client.py` | `MooncakeLookupClient` | Mooncake 分布式存储 lookup |
| `lmcache/v1/lookup_client/lmcache_async_lookup_client.py` | `LMCacheAsyncLookupClient/Server` | 异步 lookup + prefetch |
| `lmcache/v1/lookup_client/factory.py` | `LookupClientFactory` | Lookup client 工厂 |
| `lmcache/v1/offload_server/abstract_server.py` | `OffloadServerInterface` | Offload server 抽象 |
| `lmcache/v1/offload_server/zmq_server.py` | `ZMQOffloadServer` | ZMQ offload server |
| `lmcache/v1/cache_controller/controllers/kv_controller.py` | `KVController` | 全局 KV pool 控制器 |
| `lmcache/v1/multiprocess/modules/blend_v3.py` | `BlendTokenRangeMatcherV3` | CacheBlend V3 matcher |
| `lmcache/v1/multiprocess/modules/blend_v3.py` | `BlendV3` | Blend V3 engine module |
| `lmcache/integration/vllm/vllm_v1_adapter.py` | `LMCacheConnectorV1Impl` | vLLM v1 adapter |
| `lmcache/integration/vllm/vllm_v1_adapter.py` | `RequestTracker`, `ReqMeta` | 请求跟踪和元数据 |
| `lmcache/integration/sglang/sglang_adapter.py` | `LMCacheConnector` | SGLang adapter |
| `lmcache/integration/sglang/sglang_adapter.py` | `LMCacheLayerwiseConnector` | SGLang layerwise adapter |
| `lmcache/integration/sglang/multi_process_adapter.py` | `LMCacheMPConnector` | SGLang 多进程 adapter |
| `lmcache/v1/storage_backend/__init__.py` | `CreateStorageBackends` | 存储后端工厂 |
| `lmcache/v1/pin_monitor.py` | `PinMonitor` | Pin 超时监控 |

## 14. 未确认问题

1. **P2PBackend 的 NIXL 传输细节**：NIXL 的 RDMA 传输路径未完全追踪，涉及 C++ 层面的实现
2. **PDBackend 的 sender/receiver 协议**：PD 分离架构的完整握手协议未完全分析
3. **MaruBackend 的实现**：Maru 后端需要额外安装，未在源码中完整分析
4. **NixlStorageBackend 的实现**：NIXL 存储后端的完整实现未深入分析
5. **Cache Controller 的集群执行器**：`cluster_executor` 的远程执行机制未完全追踪
6. **vLLM v0 adapter 的区别**：v0 adapter（已废弃）与 v1 adapter 的具体差异未详细对比
7. **Blend V3 的完整 retrieve 流程**：Blend 的 GPU 端 retrieve（scatter to paged blocks）的完整实现未完全追踪
8. **GPUConnector 的具体实现**：`VLLMPagedKVGPUConnector` 和 `SGLangGPUConnector` 的 from_gpu/to_gpu 实现未深入分析
9. **LazyMemoryAllocator**：代码中标注为 "temporarily unavailable"，具体状态不确定
10. **EC (Encoder Cache) 的完整路径**：encoder cache 的 store/retrieve 流程未完全追踪
