# Mooncake KV Cache 源码分析

## 1. KV cache 基本抽象

### 1.1 核心数据结构

Mooncake 将 KV cache 抽象为一个 **分布式对象存储系统**，而非传统意义上的 KV cache manager。核心数据结构层次如下：

**对象层（Object）**：
- `ObjectMetadata`（`master_service.h:795-1093`）：每个 KV cache 对象的元数据，包含 `client_id`、`size`、`data_type`（含 `KVCACHE` 枚举值，`types.h:141`）、`tenant_id`、`user_key`、`lease_timeout`、`soft_pin_timeout`、`hard_pinned` 标志、以及 `replicas_` 列表。
- 对象由用户自定义的 `ObjectKey`（即 `std::string`，`types.h:180`）唯一标识。

**副本层（Replica）**：
- `Replica`（`replica.h:205-683`）：对象的物理副本，支持四种类型：
  - `MemoryReplicaData`：内存副本，持有 `std::unique_ptr<AllocatedBuffer>`，数据存储在 DRAM 段中
  - `NoFReplicaData`：NVMe-oF SSD 副本，同样持有 `AllocatedBuffer`
  - `DiskReplicaData`：分布式文件系统（3FS/NFS）副本，存储 `file_path` 和 `object_size`
  - `LocalDiskReplicaData`：本地 SSD 副本，存储 `client_id`、`object_size`、`transport_endpoint`
- 每个 Replica 有 `ReplicaStatus`：`UNDEFINED` → `INITIALIZED` → `PROCESSING` → `COMPLETE` → `REMOVED`/`FAILED`
- Replica 有原子引用计数 `refcnt_`（`replica.h:582`），通过 `inc_refcnt()`/`dec_refcnt()` 管理

**缓冲区层（AllocatedBuffer）**：
- `AllocatedBuffer`（`allocator.h:36-100`）：实际内存分配的 RAII 封装，持有 `buffer_ptr_`、`size_`、`segment_name_`、`protocol`，以及可选的 `OffsetAllocationHandle`。
- `AllocatedBuffer::Descriptor`（`allocator.h:77-84`）：可序列化的传输描述符，包含 `size_`、`buffer_address_`、`protocol_`、`transport_endpoint_`。

**段层（Segment）**：
- `Segment`（`types.h:447-457`）：一个连续内存区域，包含 `id`（UUID）、`name`、`base`（基地址）、`size`、`te_endpoint`（Transfer Engine 端点）、`protocol`。
- `NoFSegment`（`types.h:471-480`）：NVMe-oF SSD 段的描述。
- 段通过 `MountSegment` 注册到 Master，由 `SegmentManager` 管理。

**存储后端层（StorageBackend）**：
- `StorageBackendInterface`（`storage_backend.h:249-290`）：抽象接口，提供 `BatchOffload`、`BatchLoad`、`IsExist`、`ScanMeta`。
- 三个实现：
  - `StorageBackendAdaptor`（FilePerKey，`storage_backend.h:619-684`）：每个 key 一个文件
  - `BucketStorageBackend`（`storage_backend.h:686-990`）：多个 key 打包成 bucket，默认后端
  - `OffsetAllocatorStorageBackend`（`storage_backend.h:992-1207`）：单文件 + 偏移分配器

**热缓存层（LocalHotCache）**：
- `LocalHotCache`（`local_hot_cache.h:37-158`）：本地 DRAM 热缓存，基于 `HotMemBlock` 和 LRU 队列实现。
- `HotMemBlock`（`local_hot_cache.h:25-32`）：热缓存块，包含 `addr`、`size`、`ref_count`、`key_`、`accessed` 标志。

### 1.2 Key 设计

Mooncake Store 的 key 设计是 **扁平字符串（flat string）**，而非 token ID、hash 或 prefix tree path。

- **ObjectKey** = `std::string`（`types.h:180`）
- KV cache 的 key 由调用方（vLLM/SGLang）自定义，通常编码为请求 ID 或 block ID 的字符串表示
- 在 MasterService 中，key 通过 **tenant scoping** 扩展：`MakeTenantScopedKey(tenant_id, key)` 将 tenant_id 和 key 用 `\0` 分隔连接（`types.h:230-239`）
- 元数据分片：通过 `std::hash<std::string>{}(key) % kNumShards`（1024 个分片）进行分片路由（`master_service.h:1241-1249`）
- **没有内置的 prefix/token-level 匹配机制**。Key 的语义完全由上层应用定义

在 vLLM connector 中，key 的使用方式：
- `MooncakeAgentMetadata`（`mooncake_connector_v1.py:74-83`）使用 `request_ids`（即 `ReqId = str`）作为 key
- KV cache 按 block 粒度传输，key 并不直接对应 token prefix

### 1.3 Value 设计

Value 是一个 **任意字节序列**，存储为 `std::vector<Slice>`：

- `Slice`（`types.h:435-438`）：`{void* ptr, size_t size}`，表示一段连续内存
- 存储位置取决于 replica 类型：
  - **MEMORY replica**：Value 存储在注册到 Transfer Engine 的 DRAM 段中，通过 RDMA/TCP 可远程访问。数据指针为 `AllocatedBuffer::buffer_ptr_`，大小为 `AllocatedBuffer::size_`
  - **NOF_SSD replica**：Value 存储在 NVMe-oF SSD 段中
  - **DISK replica**：Value 存储在分布式文件系统（3FS/NFS）的文件中
  - **LOCAL_DISK replica**：Value 存储在本地 SSD 上，通过 RPC + Transfer Engine 间接访问

- Value 的序列化格式（BucketStorageBackend）：
  - 每个 bucket 包含 `.bucket`（数据文件）和 `.meta`（元数据文件）
  - 数据布局：`[BucketObjectMetadata: {offset, key_size, data_size}] + [key bytes] + [data bytes]`（`storage_backend.h:26-31`）

- Value 的序列化格式（OffsetAllocatorStorageBackend）：
  - 单文件 `kv_cache.data`，记录格式：`[u32 key_len][u32 value_len][key bytes][value bytes]`（`storage_backend.h:1067-1100`）

**关键区别**：Mooncake Store 不理解 KV cache 的内部结构（哪部分是 K tensor，哪部分是 V tensor）。它将整个 KV cache 块视为不透明的字节序列。KV cache 的内部格式由推理引擎（vLLM/SGLang）定义。

### 1.4 引用计数机制

Mooncake Store 实现了多层引用计数：

**Replica 级引用计数**：
- `Replica::refcnt_`（`replica.h:582`）：`std::atomic<uint32_t>`，表示正在使用该 replica 的传输操作数
- `inc_refcnt()`/`dec_refcnt()`（`replica.h:444-446`）：原子操作
- `is_busy()`（`replica.h:325`）：`refcnt_.load() > 0`，busy 的 replica 不能被 eviction
- 用途：保证正在传输的 replica 不会被 evict

**Lease 机制（软引用计数）**：
- `ObjectMetadata::lease_timeout_`（`master_service.h:851-852`）：硬 lease，客户端通过 Ping 续约
- `ObjectMetadata::soft_pin_timeout_`（`master_service.h:853-854`）：软 pin，可选，30 分钟默认 TTL（`types.h:88`）
- `GrantLease()`（`master_service.h:1013-1024`）：续约，取 max(当前, now+ttl)
- `IsLeaseExpired()`（`master_service.h:1039-1041`）：检查是否过期

**Bucket 读取引用计数**：
- `BucketMetadata::inflight_reads_`（`storage_backend.h:41`）：`std::atomic<int32_t>`，追踪正在进行读操作的 bucket
- `BucketReadGuard`（`storage_backend.h:105-147`）：RAII guard，构造时 `fetch_add(1)`，析构时 `fetch_sub(1)`
- 确保安全删除：`DeleteBucket` 在 `inflight_reads_ == 0` 后才删除文件

**OffsetAllocator 引用计数**：
- `RefCountedAllocationHandle`（`storage_backend.h:1104-1116`）：包装 `OffsetAllocationHandle`，通过 `shared_ptr` 管理生命周期
- `ObjectEntry::allocation`（`storage_backend.h:1133`）：`AllocationPtr`（即 `shared_ptr<RefCountedAllocationHandle>`），物理空间在最后一个引用释放时回收

**HotMemBlock 引用计数**：
- `HotMemBlock::ref_count`（`local_hot_cache.h:28`）：`std::atomic<int>`，标记 block 是否正在使用
- `GetHotKey()` 递增，`ReleaseHotKey()` 递减

## 2. 生命周期

### 2.1 Allocate/Store

KV cache 对象的存储流程（Put 路径）：

1. **PutStart**（`master_service.h:308-311`）：
   - 客户端调用 `PutStart(client_id, key, tenant_id, slice_length, config)`
   - MasterService 通过 `AllocateAndInsertMetadata`（`master_service.h:1285-1291`）：
     a. 根据 `AllocationStrategy` 选择 segment 并分配 buffer
     b. 创建 `Replica`（状态 `PROCESSING`）
     c. 创建 `ObjectMetadata` 并插入 `metadata_shards_`
     d. 将 key 加入 `processing_keys` 集合
   - 返回 `Replica::Descriptor` 列表给客户端

2. **数据写入**：
   - 客户端通过 `TransferSubmitter::submit()`（`transfer_task.h:550`）选择传输策略：
     - `LOCAL_MEMCPY`：同一进程内内存拷贝
     - `TRANSFER_ENGINE`：跨节点 RDMA/TCP 传输
     - `FILE_READ`：从磁盘读取
     - `SPDK_NVMF`：NVMe-oF 操作
   - `selectStrategy()`（`transfer_task.h:605`）根据 replica descriptor 判断本地/远程

3. **PutEnd**（`master_service.h:319-321`）：
   - 客户端通知 Master 写入完成
   - Master 将 Replica 状态从 `PROCESSING` → `COMPLETE`
   - 从 `processing_keys` 中移除 key
   - 如果 PutEnd 超时（`put_start_discard_timeout_sec_`，默认 30 秒），进入 `discarded_replicas_` 列表，延迟释放内存

**Allocation 策略**（`allocation_strategy.h`）：
- `RandomAllocationStrategy`（`allocation_strategy.h:202-364`）：随机选择 segment 分配
- `FreeRatioFirstAllocationStrategy`（`allocation_strategy.h:382-539`）：采样 6N 个候选 segment，按空闲率排序选择，最佳负载均衡
- `CxlAllocationStrategy`（`allocation_strategy.h:541-600`）：指定 CXL segment 分配

### 2.2 命中复用/Retrieve

KV cache 的检索和复用流程（Get 路径）：

1. **GetReplicaList**（`master_service.h:297-298`）：
   - 客户端调用 `Get(object_key, slices)`
   - Client 内部先调用 `Query(object_key)` → `BatchQuery` → MasterService `GetReplicaList`
   - Master 返回 `Replica::Descriptor` 列表和 lease timeout
   - **Promotion-on-hit**：如果 key 只有 LOCAL_DISK replica，`TryPushPromotionQueue`（`master_service.h:1366`）会将 promotion 任务推给持有 SSD 数据的客户端

2. **Replica 选择**：
   - `GetPreferredReplica`（`client_service.h:588-589`）：优先选择本地内存 replica
   - `FindFirstCompleteReplica`（`client_service.h:747-749`）：找第一个 COMPLETE 状态的 replica

3. **Hot Cache 检查**：
   - `RedirectToHotCache(key, replica)`（`client_service.h:726-727`）：如果 key 在 LocalHotCache 中命中，重定向到本地缓存地址
   - `ShouldAdmitToHotCache(key, cache_used)`（`client_service.h:640-648`）：基于 CountMinSketch 的频率准入，只有访问次数 >= `admission_threshold_` 的 key 才被缓存

4. **数据传输**：
   - 通过 `TransferSubmitter` 从选中的 replica 读取数据
   - 读完后通过 `ProcessSlicesAsync`（`client_service.h:736-738`）异步写入 Hot Cache

**重要：Mooncake Store 没有内置的 prefix 匹配或 token-level 复用机制**。复用完全依赖于：
- 客户端知道要查询的 key（精确匹配）
- Hot Cache 的 LRU 淘汰策略
- Master 的 lease 续约防止过早 evict

### 2.3 Evict/Free

**内存 Eviction**：

1. **触发条件**：
   - `need_mem_eviction_` 标志（`master_service.h:1386-1387`）：当 `PutStart` 分配失败时设置
   - `eviction_high_watermark_ratio_`（默认 0.95，`types.h:91`）：内存使用率超过阈值时触发

2. **BatchEvict**（`master_service.h:769`）：
   - 第一轮：只 evict 无 soft pin 的对象
   - 第二轮：优先 evict 无 soft pin 的对象，如果 `allow_evict_soft_pinned_objects_` 为 true，也允许 evict soft pinned 对象
   - Eviction 策略：`EvictionStrategy` 接口（`eviction_strategy.h`），提供 LRU 和 FIFO 两种实现
   - 选择 lease timeout 最小的对象优先 evict（近似 LRU）

3. **Offload-on-evict**（`master_service.h:1736`）：
   - 当 `offload_on_evict_` 为 true 时，evict 前先将数据 offload 到 SSD
   - 如果 `offload_force_evict_` 为 true，允许不经过 SSD offload 直接 evict

**SSD Eviction**（`storage_backend.h`）：

1. **触发条件**：
   - `max_total_size > 0` 且新 bucket 写入后总大小超出限制
   - 由 `PrepareEviction(required_size)` 触发（`storage_backend.h:901`）

2. **Bucket Eviction 策略**（`storage_backend.h:179-183`）：
   - `FIFO`：选择 `buckets_.begin()`（最老 bucket，因为 ID 单调递增）
   - `LRU`：选择 `last_access_ns_` 最小的 bucket

3. **两阶段 Eviction 协议**：
   - Phase 1 `PrepareEviction`：在排他锁下从元数据中移除 bucket，收集待删除信息
   - 通知 Master：通过 `BatchEvictDiskReplica` RPC 原子移除 disk replica
   - Phase 2 `FinalizeEviction`：等待 `inflight_reads_ == 0`，然后删除物理文件

**NoF SSD Eviction**（`master_service.h:770`）：
- `NoFBatchEvict`：类似内存 eviction，但针对 NVMe-oF SSD 段

### 2.4 过期和清理

**Lease 过期**：
- 客户端必须定期调用 `Ping(client_id)` 续约（`master_service.h:546`）
- `client_live_ttl_sec_`（默认 10 秒，`types.h:95`）：客户端存活 TTL
- `default_kv_lease_ttl_`（默认 5000 毫秒，`types.h:85`）：KV 对象的默认 lease TTL
- `default_kv_soft_pin_ttl_`（默认 30 分钟，`types.h:88`）：软 pin TTL

**客户端死亡清理**：
- `ClientMonitorFunc`（`master_service.h:1693`）：每 1 秒检查一次
- `ClearInvalidHandles`（`master_service.h:779-780`）：清理已卸载 segment 对应的无效 replica
- 死亡客户端的 segment 自动 unmount

**Processing Key 超时**：
- `put_start_discard_timeout_sec_`（默认 30 秒，`types.h:118`）：PutStart 后未 PutEnd 的超时
- `put_start_release_timeout_sec_`（默认 600 秒，`types.h:119`）：discarded replica 的最终释放超时
- `DiscardExpiredProcessingReplicas`（`master_service.h:1296-1298`）：清理超时的 processing key
- `ReleaseExpiredDiscardedReplicas`（`master_service.h:1303-1305`）：释放超期的 discarded replica 内存

**Promotion Task 超时**：
- Promotion task 也有 `put_start_release_timeout_sec_` 作为 reaper 截止时间
- `NotifyPromotionFailure`（`master_service.h:649-651`）：客户端失败时主动释放

## 3. 内存层级

### 3.1 GPU HBM

Mooncake Store **不直接管理 GPU HBM**。GPU 内存的 KV cache 由推理引擎（vLLM/SGLang）自行管理。Mooncake 的角色是：
- 通过 Transfer Engine 的 P2P transport 支持 GPU 内存注册（`transfer_engine.h:159-167`）
- 在 vLLM connector 中，GPU KV cache 的基地址通过 `register_kv_caches`（`mooncake_connector_v1.py:694-742`）注册到 Transfer Engine
- RDMA 写入时，通过 IBGDA（InfiniBand GPUDirect Async）直接写入 GPU 内存

### 3.2 CPU DRAM

CPU DRAM 是 Mooncake Store 的 **主存储层**：

- **Segment 注册**：通过 `MountSegment(buffer, size, protocol)` 将 DRAM buffer 注册为 segment（`client_service.h:298-300`）
- **Buffer Allocator**：
  - `CachelibBufferAllocator`（`allocator.h:130-150`）：基于 Facebook CacheLib 的 slab 分配器
  - `OffsetBufferAllocator`：基于偏移分配器的内存管理
- **默认段大小**：`DEFAULT_GLOBAL_SEGMENT_SIZE = 16MB`（`types.h:221`）
- **默认本地缓冲区**：`DEFAULT_LOCAL_BUFFER_SIZE = 16MB`（`types.h:222`）
- **LocalHotCache**：在 DRAM 中维护热数据的 LRU 缓存，块大小可配置，支持共享内存（`use_shm`）跨进程共享

### 3.3 Disk SSD

SSD 作为 **溢出/卸载层**，支持三种后端：

1. **BucketStorageBackend**（默认，`storage_backend.h:686-990`）：
   - 多个 key 打包成 bucket（默认 256MB/500 keys）
   - 支持 FIFO/LRU eviction
   - 支持 io_uring 和 O_DIRECT
   - 文件格式：`.bucket` + `.meta`

2. **StorageBackendAdaptor/FilePerKey**（`storage_backend.h:619-684`）：
   - 每个 key 一个文件
   - 两级 hash 分片目录结构

3. **OffsetAllocatorStorageBackend**（`storage_backend.h:992-1207`）：
   - 单文件 `kv_cache.data`
   - 1024 分片的元数据映射
   - 记录格式：`[key_len: u32][value_len: u32][key][value]`

**Offload 流程**（`ssd-offload.md`）：
1. Heartbeat 线程定期查询 Master 获取待 offload 对象列表
2. 从 DRAM 段读取数据 slice
3. 通过 StorageBackend 写入 SSD
4. 通知 Master 添加 LOCAL_DISK replica

**Load 流程**：
1. 请求方客户端查询 Master，获取 LOCAL_DISK replica 描述符（含 RPC 地址）
2. 向目标客户端发送 RPC 请求
3. 目标客户端从 SSD 读取数据到 ClientBuffer
4. 通过 Transfer Engine (RDMA/TCP) 零拷贝传输到请求方

### 3.4 Remote Memory (RDMA)

RDMA 是 Mooncake 跨节点数据传输的核心：

- **Transfer Engine**（`transfer_engine.h`）：统一的传输引擎接口
  - `registerLocalMemory(addr, length, location)`：注册本地内存区域
  - `submitTransfer(batch_id, entries)`：提交传输请求
  - `getTransferStatus(batch_id, task_id, status)`：查询传输状态

- **Transport 实现**（`transport/transport.h`）：
  - RDMA Transport：基于 IB Verbs 的高性能传输
  - TCP Transport：基于 socket 的回退传输
  - NVLink Transport：GPU P2P 传输
  - SHM Transport：共享内存传输
  - CXL Transport：CXL 内存传输
  - GDS Transport：GPUDirect Storage
  - Ascend Transport：华为 NPU 传输

- **SegmentDesc**（`transfer_metadata.h:88-121`）：远程节点的段描述，包含：
  - `name`：段名称（通常为 ip:port）
  - `protocol`：传输协议
  - `devices`：RDMA 设备列表（lid, gid）
  - `buffers`：缓冲区描述列表（addr, length, lkey, rkey）

### 3.5 层级迁移机制

**MEMORY → LOCAL_DISK（Offload）**：
- 由 heartbeat 线程驱动（`ssd-offload.md`）
- Master 决定哪些对象需要 offload（`OffloadObjectHeartbeat`）
- 数据从 DRAM segment 读取 → 写入本地 SSD
- Master 添加 LOCAL_DISK replica，保留 MEMORY replica（取决于配置）

**LOCAL_DISK → MEMORY（Promotion）**：
- 由 `PromotionObjectHeartbeat`（`client_service.h:438-439`）驱动
- Master 维护 `promotion_tasks` 队列（`master_service.h:1149`）
- Promotion-on-hit：当 Get 请求发现只有 LOCAL_DISK replica 时自动触发（`master_service.h:1743`）
- 频率门控：使用 `CountMinSketch`（`master_service.h:1759`）过滤低频 key

**MEMORY → 远程 MEMORY（Copy/Move）**：
- 通过 `CopyStart`/`MoveStart`（`master_service.h:449-486`）操作
- Master 在目标 segment 分配新 replica
- 通过 Transfer Engine 跨节点传输数据

**Hot Cache 层级**：
- L1：GPU HBM（由推理引擎管理）
- L2：CPU DRAM（LocalHotCache + DRAM segment）
- L3：分布式存储（Mooncake Store 集群 + SSD offload）

## 4. Prefix store / reuse 机制

### 4.1 存储接口

**Mooncake Store 本身不提供 prefix 级别的存储和匹配**。它的存储接口是简单的 key-value 操作：

- `Put(key, slices, config)`：存储一个完整对象
- `Get(key, slices)`：按精确 key 检索
- `Query(key)`：查询对象的 replica 信息
- `BatchGet/BatchPut`：批量操作
- `Upsert(key, slices, config)`：更新或插入

**HiCache 提供 prefix 匹配**（`hicache-design.md`）：
- HiCache 是 SGLang 端的组件，不是 Mooncake 内置功能
- HiRadixTree：基于 RadixAttention 的前缀树，节点对应连续 token span
- 每个节点记录 KV cache 的存储位置（GPU/CPU/L3）
- L3 查询是实时查询，不在本地维护远程元数据

### 4.2 匹配粒度

- **Mooncake Store 粒度**：**Object/Key 级别**（整个 KV cache 块作为一个对象）
  - 没有 token-level、block-level 或 prefix-level 的匹配
  - 匹配完全基于 key 的精确字符串比较

- **HiCache 粒度**：**Page 级别**（`hicache-design.md`）
  - 每个页面对应一段连续 token 的 KV cache
  - `page_size` 可配置
  - 支持三种数据布局：`layer first`、`page first`、`page first direct`

- **vLLM connector 粒度**：**Block 级别**
  - KV cache 按 block 组织，每个 block 包含 `block_size` 个 token
  - 传输粒度是 block（`mooncake_connector_v1.py:648-664`）
  - key 对应 `request_id`，不是 prefix

### 4.3 Partial hit

**Mooncake Store 不支持 partial hit**。Get 操作要么找到完整对象，要么返回 `OBJECT_NOT_FOUND`。

**HiCache 支持 partial hit**：
- 本地匹配（HiRadixTree）后，可能只有部分 prefix 在 L1/L2 命中
- 剩余部分从 L3 预取
- 预取可以部分完成：`best_effort`/`timeout` 策略允许在 GPU 就绪时终止预取

**vLLM connector 的 partial prefix cache hit**：
- `mooncake_connector_v1.py:643`：`if num_local_blocks > num_remote_blocks`，只传输未计算的 block
- `get_num_new_matched_tokens`（`mooncake_connector_v1.py:252-283`）：返回可以从远程加载的 token 数

### 4.4 跨节点复用

跨节点 KV cache 复用的路径：

**路径 1：Mooncake Store 分布式存储**
1. 节点 A 将 KV cache `Put` 到 Mooncake Store（数据存储在 A 的 DRAM segment）
2. 节点 B `Get` 同一个 key → Master 返回 A 的 replica 描述符
3. B 通过 Transfer Engine（RDMA）从 A 的 DRAM 直接读取

**路径 2：vLLM PD 分离**
1. Prefill 节点完成 prefill，KV cache 在 GPU/DRAM 中
2. Prefill 节点通过 Transfer Engine 将 KV cache 块发送到 Decode 节点
3. Decode 节点接收后用于 decode 推理
4. 使用 ZMQ side channel 协调传输

**路径 3：HiCache L3 共享**
1. SGLang 实例将 KV cache 写回 Mooncake Store（L3）
2. 其他 SGLang 实例查询 Mooncake Store，预取命中的 KV cache
3. 写回策略：`write_through`/`write_through_selective`/`write_back`

## 5. Transfer Engine

### 5.1 架构设计

Transfer Engine 是 Mooncake 的核心传输层，负责跨节点零拷贝数据传输。

**核心类**（`transfer_engine.h`）：
- `TransferEngine`：顶层 API，包装 `TransferEngineImpl`（旧版）和 `tent::TransferEngine`（新版 tent）
- `TransferMetadata`：元数据服务，管理段描述符的注册和发现
- `Transport`：抽象传输层接口，支持多种协议

**传输请求**（`transport/transport.h:60-71`）：
```cpp
struct TransferRequest {
    OpCode opcode;      // READ or WRITE
    void* source;       // 源地址
    SegmentID target_id; // 目标段 ID
    uint64_t target_offset; // 目标偏移
    size_t length;      // 传输长度
};
```

**传输任务**（`transport/transport.h:289-326`）：
- `TransferTask`：跟踪一批 slice 的传输进度
- `Slice`：最小传输单元，包含源地址、长度、状态、协议特定字段（RDMA/TCP/NVLink/CXL 等）
- `BatchDesc`：一个 batch 内的多个 TransferTask

**Slice 状态机**：`PENDING` → `POSTED` → `SUCCESS`/`TIMEOUT`/`FAILED`

### 5.2 传输协议

**Metadata 同步协议**：
- 基于 HTTP 或 etcd 的元数据存储
- `TransferMetadata::SegmentDesc`（`transfer_metadata.h:88-121`）描述每个节点的段信息
- `syncSegmentCache()`：同步远程段描述符到本地缓存
- `HandShake`：RDMA 连接建立握手（`transfer_metadata.h:202-209`）

**数据传输协议**：
1. **注册阶段**：`registerLocalMemory(addr, length, location)` → 元数据发布
2. **发现阶段**：`openSegment(segment_name)` → 获取远程段描述符
3. **提交阶段**：`submitTransfer(batch_id, requests)` → 创建 slice 并提交到 transport
4. **完成阶段**：`getTransferStatus(batch_id, task_id, status)` → 轮询完成状态

**Notify 机制**：
- `sendNotifyByID`/`sendNotifyByName`（`transfer_engine.h:144-148`）：节点间通知
- `getNotifies`（`transfer_engine.h:142`）：获取通知列表

### 5.3 RDMA 传输

RDMA 是 Mooncake 的主要高性能传输方式：

**架构**（tent 实现）：
- `RdmaTransport`（`tent/include/tent/transport/rdma/rdma_transport.h`）：RDMA 传输实现
- `Context`（`tent/include/tent/transport/rdma/context.h`）：IB Verbs 上下文管理
- `Endpoint`（`tent/include/tent/transport/rdma/endpoint.h`）：QP 连接端点
- `Workers`（`tent/include/tent/transport/rdma/workers.h`）：CQ 轮询工作线程
- `Quota`（`tent/include/tent/transport/rdma/quota.h`）：传输流量控制
- `RailMonitor`（`tent/include/tent/transport/rdma/rail_monitor.h`）：多 NIC 监控

**RDMA 连接建立**：
1. 本地节点发布 `SegmentDesc`（含 `devices`: lid, gid, `buffers`: lkey, rkey）
2. 远程节点通过 `HandShake` 交换 QP 信息
3. 建立 RC（Reliable Connection）QP 对

**RDMA 传输流程**：
1. 源地址 → 目标地址的 RDMA WRITE/READ
2. Slice 包含 `rdma.dest_addr`、`rdma.source_lkey`、`rdma.dest_rkey`、`rdma.endpoint`
3. 多 rail 并行：支持多 NIC 并行传输

**RDMA 切片**：
- 大传输被切分为多个 Slice
- 每个 Slice 独立提交到 QP
- 通过 `transferred_bytes` 和 `success_slice_count` 跟踪进度

### 5.4 Segment 管理

**Segment 生命周期**：

1. **注册**：`openSegment(segment_name)` → 从 metadata 获取 SegmentDesc
2. **本地注册**：`registerLocalMemory(addr, length)` → 注册到 transport + 发布 metadata
3. **使用**：`submitTransfer` 引用 segment ID 进行读写
4. **关闭**：`closeSegment(handle)` → 清理本地资源
5. **移除**：`removeLocalSegment(name)` → 从 metadata 中移除

**Segment 描述**（`transfer_metadata.h:88-121`）：
```cpp
struct SegmentDesc {
    string name;              // 段名称 (ip:port)
    string protocol;          // 传输协议
    vector<DeviceDesc> devices; // RDMA 设备
    vector<BufferDesc> buffers; // 缓冲区列表
    string rdma_server_name;  // RDMA 地址
};
```

**Buffer 描述**（`transfer_metadata.h:52-65`）：
```cpp
struct BufferDesc {
    string name;
    uint64_t addr;           // 虚拟地址
    uint64_t length;
    vector<uint32_t> lkey;   // 本地访问 key
    vector<uint32_t> rkey;   // 远程访问 key
    string shm_name;         // 共享内存名
};
```

## 6. Disaggregated 架构

### 6.1 Prefill-Decode 分离

Mooncake 支持 Prefill-Decode 分离架构，但实现方式有两种：

**方式 1：vLLM 原生 PD 分离（通过 MooncakeConnector）**
- Prefill 节点角色：`kv_producer`
- Decode 节点角色：`kv_consumer`
- Proxy 节点：协调调度

**方式 2：SGLang HiCache + Mooncake Store**
- 任意 SGLang 实例都可以是 producer 和 consumer
- Mooncake Store 作为共享的 L3 缓存
- 无需显式的角色分配

**PD 分离的 KV cache 流动**（vLLM connector）：

1. 请求到达 Prefill 节点，执行 prefill
2. Prefill 完成，`request_finished`（`mooncake_connector_v1.py:345-392`）：
   - 返回 `delay_free_blocks=True`，延迟释放 block
   - 返回 `kv_transfer_params`：`{do_remote_prefill: True, remote_host, remote_port, remote_request_id}`
3. Decode 节点通过 `get_num_new_matched_tokens`（`mooncake_connector_v1.py:252-283`）识别需要远程 prefill
4. Decode 节点通过 ZMQ + Transfer Engine 从 Prefill 节点拉取 KV cache
5. 传输完成后，Prefill 节点释放 block

**PD 分离的配置**（`mooncake_store_service.py:183-284`）：
- `/api/reconfigure` 端点支持动态切换 Prefill/Decode 模式
- Decode 模式：mount segment 到本地 DRAM
- Prefill 模式：unmount segment，释放内存

### 6.2 Controller/Conductor

**MasterService** 是 Mooncake 的中心控制器（`master_service.h:67`）：

核心职责：
- **元数据管理**：维护所有对象的元数据（`metadata_shards_`，1024 分片）
- **Segment 管理**：`SegmentManager` 管理所有注册的内存/SSD 段
- **分配调度**：`AllocationStrategy` 决定数据存储在哪个 segment
- **Eviction 控制**：后台 `EvictionThreadFunc` 执行内存和 SSD eviction
- **任务调度**：`ClientTaskManager` 和 `DrainJob` 管理复制/迁移任务
- **客户端监控**：`ClientMonitorFunc` 检测客户端存活，清理失效资源

**没有独立的 Conductor/Indexer 组件**。MasterService 承担了所有控制面职责。

**Promotion-on-hit 机制**（`master_service.h:1743-1759`）：
- `CountMinSketch promotion_sketch_`：频率统计
- `promotion_admission_threshold_`：准入阈值（默认 2）
- `promotion_queue_limit_`：队列上限（默认 50000）
- `TryPushPromotionQueue`：Get 请求发现只有 SSD replica 时触发 promotion

### 6.3 KV cache 流动路径

**Prefill → Decode（PD 分离）**：
```
Prefill Node                    Decode Node
GPU HBM (prefill)               
  │ D2H (cudaMemcpy)            
  ▼                             
CPU DRAM (registered segment)   
  │ Transfer Engine (RDMA WRITE) 
  └──────────────────────────────▶ CPU DRAM (registered segment)
                                     │ H2D (cudaMemcpy)
                                     ▼
                                   GPU HBM (decode)
```

**跨节点共享（HiCache L3）**：
```
SGLang Instance A               Mooncake Store            SGLang Instance B
GPU HBM (prefill)               
  │ write_back (L1→L2)          
  ▼                             
CPU DRAM                        
  │ write_backup_storage (L2→L3)
  │ Transfer Engine (RDMA WRITE)
  └──────────────────────────────▶ Remote DRAM segment
                                     │                     
                                     │ Transfer Engine (RDMA READ)
  ◀──────────────────────────────────┘                     
  │ prefetch (L3→L2)                
  ▼                                
CPU DRAM                        
  │ H2D (cudaMemcpyAsync)        
  ▼                                
GPU HBM (decode)                
```

**SSD Offload/Load**：
```
DRAM segment ──Offload──▶ Local SSD
Local SSD ──Load──▶ ClientBuffer ──Transfer Engine──▶ Remote DRAM
```

## 7. 与 SGLang/vLLM 的集成

### 7.1 HiCache 集成

HiCache 是 SGLang 端的分层缓存系统，Mooncake 作为其 L3 后端。

**集成架构**（`hicache-design.md`）：

- **HiRadixTree**：SGLang 的元数据组织，每个节点记录 KV cache 的存储层级
- **L3 接口**：HiCache 通过 Mooncake Store 的 Python API 与 Mooncake 交互
- **零拷贝传输**：Mooncake 提供零拷贝读写接口，RDMA 直接在 L2 内存和远程存储间传输
- **Page 粒度存储**：HiCache L3 以 page 为粒度存储和传输 KV cache

**Prefetch 优化**（`hicache-design.md`）：
- 两个后台线程：`prefetch_thread_func`（查询命中）+ `prefetch_io_aux_func`（提交 IO）
- Mooncake 使用 RDMA 并行从多个远程节点读取
- 三种预取策略：`best_effort`/`wait_complete`/`timeout`
- 动态超时：`timeout = prefetch_timeout_base + prefetch_timeout_per_ki_token * num_token_to_fetch / 1024`

**Write-back 优化**（`hicache-design.md`）：
- 异步写入：`backup_queue` + `backup_thread_func`
- 三种策略：`write_through`/`write_through_selective`/`write_back`
- MLA 优化：多 TP 场景下只有一个 rank 执行写回

### 7.2 vLLM connector

`MooncakeConnector`（`mooncake_connector_v1.py:122`）实现 vLLM 的 `KVConnectorBase_V1` 接口：

**Scheduler 端**：
- `MooncakeConnectorScheduler`（`mooncake_connector_v1.py:232`）：
  - `get_num_new_matched_tokens`：确定可以从远程加载的 token 数
  - `update_state_after_alloc`：标记需要 recv/send 的请求
  - `request_finished`：决定是否延迟释放 block，返回 `kv_transfer_params`

**Worker 端**：
- `MooncakeConnectorWorker`（`mooncake_connector_v1.py:395`）：
  - `register_kv_caches`：将 GPU KV cache 注册到 Transfer Engine
  - `start_load_kv`：触发异步 KV cache 接收/发送
  - ZMQ side channel：P/D 节点间的协调通道
  - `batch_transfer_sync_write`：批量 RDMA 写入

**传输流程**：
1. Decode 节点通过 ZMQ 向 Prefill 节点发送 `MooncakeAgentMetadata`
2. Prefill 节点收到后，通过 Transfer Engine 将 KV cache 块写入 Decode 节点
3. 传输完成后通过 ZMQ 返回确认

**支持的 vLLM 版本**：0.10.x、0.11.0-0.11.2、0.12.0（`mooncake_connector_v1.py:487-510`）

### 7.3 集成接口设计

**C++ 层接口**（`mooncake-integration/store/store_py.cpp`）：
- `MooncakeDistributedStore`：Python 绑定的分布式存储类
- `put(key, value)`/`get(key)`：基本的 key-value 操作
- `mount_segment`/`unmount_segment`：段管理
- `batch_put_from`/`batch_get_into`：零拷贝批量操作
- `register_buffer`/`unregister_buffer`：缓冲区注册

**Python 层接口**（`structured_object_store.py`）：
- `MooncakeBundleTransfer`：结构化对象传输
- `BundleStore` Protocol：put/get/remove 接口
- `StructuredObjectPayload`：结构化对象编码（metadata + named buffers）
- 支持分块传输、并行上传、范围读取

**Transfer Engine Python 接口**（`mooncake-integration/transfer_engine/transfer_engine_py.cpp`）：
- `TransferEngine.initialize(hostname, session, protocol, device)`
- `batch_register_memory(ptrs, lens)`
- `batch_transfer_sync_write(session, src_ptrs, dst_ptrs, lengths)`

## 8. Agent 场景差距分析

### 8.1 当前不足

1. **无 Token-Level Prefix 匹配**：
   - Mooncake Store 的 key 是扁平字符串，不支持 token prefix 匹配
   - Agent 场景中，多个请求共享 system prompt prefix，但 Mooncake 无法自动发现和复用这些 prefix
   - HiCache 的 prefix 匹配在 SGLang 端实现，不是 Mooncake 内置能力

2. **无增量更新**：
   - `Put` 操作是完整替换，不支持 append 或增量写入
   - Agent 多轮对话中，KV cache 是逐步增长的，每次需要重新写入整个 cache
   - `Upsert` 支持同大小原地更新，但不支持 append

3. **Eviction 策略不适配 Agent 模式**：
   - 当前 eviction 基于 lease timeout 和 LRU，不考虑 prefix 共享关系
   - Agent 场景中，system prompt 的 KV cache 应该被保护（hard pin 存在但需要显式配置）
   - 没有"保护共享 prefix"的智能 eviction 策略

4. **跨节点复用延迟**：
   - RDMA 传输延迟约 10-100us/MB，对于长 context（如 128K tokens）可能需要 10ms+
   - Agent 批量推理中，多个 agent 共享同一 system prompt，串行传输效率低
   - 没有 broadcast/multicast 机制

5. **无 Block/Token 粒度管理**：
   - Mooncake 以整个 object 为单位管理，不理解 KV cache 的 block 结构
   - 无法在 store 层面实现 block-level 的共享和复用
   - 无法感知哪些 block 是共享 prefix，哪些是 request-specific

6. **Promotion-on-hit 不足**：
   - 只在 Get 请求时触发，不能主动预热
   - 频率门控（CountMinSketch）可能在 agent 冷启动时过滤掉有用数据
   - promotion 队列限制（50000）在大规模 agent 场景下可能不足

7. **缺乏请求级关联**：
   - 没有"session"或"conversation"的概念
   - 无法将同一 agent 的多轮 KV cache 关联起来
   - 无法实现"同一 agent 的 KV cache 应该在同一节点"的亲和性调度

8. **PD 分离模式局限**：
   - 当前 PD 分离中，KV cache 只从 P 传到 D 一次，不复用
   - 没有实现"P 保留 KV cache 供后续 D 复用"的机制
   - vLLM connector 中的 block 传输是 per-request 的，不跨请求共享

### 8.2 扩展改动点

1. **Prefix-aware Key 设计**（需要修改 MasterService + Client）：
   - 扩展 ObjectKey 为结构化 key：`{session_id, prefix_hash, block_range}`
   - 在 MasterService 中增加 prefix 索引（基于 RadixTree 或 hash prefix table）
   - 支持按 prefix 查询：`QueryByPrefix(prefix_hash)` → 返回所有匹配的 KV cache block

2. **Block-level 存储接口**（需要修改 StorageBackend + Client API）：
   - 新增 `PutBlocks(key, block_ids, block_data)` 接口
   - 新增 `GetBlocks(key, block_ids)` 接口
   - 允许不同请求共享相同 block 的存储
   - 参考 HiCache 的 page-first 布局

3. **Append/增量更新**（需要修改 PutStart/PutEnd 流程）：
   - 新增 `AppendStart(key, additional_length)` → 在现有对象后追加空间
   - 新增 `AppendEnd(key)` → 完成追加
   - 需要处理跨 segment 边界的情况

4. **智能 Eviction**（需要修改 EvictionStrategy）：
   - 实现 `PrefixAwareEvictionStrategy`：保护被多个请求引用的 prefix block
   - 基于 reference counting 的 eviction：prefix block 的引用计数等于依赖它的请求数
   - 支持配置 eviction 优先级：system prompt > few-shot examples > user context

5. **Broadcast/Multicast 传输**（需要修改 TransferEngine）：
   - 新增 `BroadcastWrite(source, target_ids[], offset, length)` 接口
   - RDMA 支持一侧写入多侧（需要硬件支持或软件多播）
   - 降低 Agent 场景中多个 Decode 节点获取相同 prefix 的延迟

6. **Session 亲和性**（需要修改 AllocationStrategy + MasterService）：
   - 新增 `SessionAffinityAllocationStrategy`：同一 session 的 KV cache 优先分配在同一 segment
   - MasterService 维护 session → segment 的映射
   - 减少 Agent 多轮对话中的跨节点传输

7. **主动预热**（需要修改 Promotion 机制）：
   - 支持 `PrefetchByPrefix(prefix_hash)` 主动触发
   - 取消频率门控对 agent 场景的限制
   - 在 agent 批量推理开始前，预加载所有 agent 的 system prompt KV cache

8. **跨请求 Block 共享**（需要修改 Replica 管理和引用计数）：
   - 允许多个 ObjectMetadata 引用同一个 Replica（block 共享）
   - 增加 block-level 引用计数
   - 当最后一个引用者释放时才 evict

## 9. 关键源码文件索引

| 文件 | 关键类/函数 | 作用 |
|------|------------|------|
| `mooncake-store/include/types.h` | `ObjectKey`, `Slice`, `Segment`, `NoFSegment`, `ObjectDataType`, `ReplicateConfig` | 核心类型定义 |
| `mooncake-store/include/replica.h` | `Replica`, `Replica::Descriptor`, `ReplicaStatus`, `ReplicaType` | 副本抽象和生命周期 |
| `mooncake-store/include/allocator.h` | `AllocatedBuffer`, `BufferAllocatorBase`, `AllocatedBuffer::Descriptor` | 内存分配抽象 |
| `mooncake-store/include/allocation_strategy.h` | `AllocationStrategy`, `RandomAllocationStrategy`, `FreeRatioFirstAllocationStrategy` | 分配策略 |
| `mooncake-store/include/eviction_strategy.h` | `EvictionStrategy`, `LRUEvictionStrategy`, `FIFOEvictionStrategy` | Eviction 策略 |
| `mooncake-store/include/storage_backend.h` | `StorageBackendInterface`, `BucketStorageBackend`, `OffsetAllocatorStorageBackend`, `BucketMetadata` | SSD 存储后端 |
| `mooncake-store/include/local_hot_cache.h` | `LocalHotCache`, `HotMemBlock`, `LocalHotCacheHandler` | 本地热缓存 |
| `mooncake-store/include/master_service.h` | `MasterService`, `ObjectMetadata`, `MetadataShard`, `PromotionTask` | Master 中心控制器 |
| `mooncake-store/include/client_service.h` | `Client`, `QueryResult` | 客户端 API |
| `mooncake-store/include/transfer_task.h` | `TransferSubmitter`, `TransferFuture`, `TransferStrategy`, `OperationState` | 传输任务管理 |
| `mooncake-transfer-engine/include/transfer_engine.h` | `TransferEngine` | 传输引擎顶层 API |
| `mooncake-transfer-engine/include/transfer_metadata.h` | `TransferMetadata`, `SegmentDesc`, `BufferDesc`, `HandShakeDesc` | 传输元数据 |
| `mooncake-transfer-engine/include/transport/transport.h` | `Transport`, `TransferRequest`, `TransferTask`, `Slice`, `BatchDesc` | 传输层抽象 |
| `mooncake-wheel/mooncake/mooncake_connector_v1.py` | `MooncakeConnector`, `MooncakeConnectorWorker`, `MooncakeConnectorScheduler` | vLLM PD 分离 connector |
| `mooncake-wheel/mooncake/mooncake_store_service.py` | `MooncakeStoreService` | Store REST 服务 |
| `mooncake-wheel/mooncake/structured_object_store.py` | `MooncakeBundleTransfer`, `StructuredObjectPayload` | 结构化对象传输 |
| `docs/source/design/hicache-design.md` | HiCache 设计 | HiCache + Mooncake L3 集成设计 |
| `docs/source/design/ssd-offload.md` | SSD Offload 设计 | SSD offload 架构和数据流 |

## 10. 未确认问题

1. **Transfer Engine 的 IBGDA 支持**：代码中有 `USE_CUDA` 条件编译和 `device::RdmaTransport`，但具体的 IBGDA（GPU Direct RDMA）实现细节未在已读文件中完全确认。

2. **tent 架构**：`TransferEngine` 同时持有 `impl_`（旧版）和 `impl_tent_`（tent 版），tent 的切换条件和具体优势未完全确认。

3. **HiCache 的具体 Python 绑定**：HiCache 作为 SGLang 组件，其调用 Mooncake Store 的具体 API 路径（put/get/batch_get_into 等）未在已读文件中完全追踪。

4. **分布式文件系统（3FS/NFS）的 DISK replica**：`DiskReplicaData` 存储了 `file_path`，但具体的分布式文件系统访问路径和与 Transfer Engine 的集成方式未完全确认。

5. **CXL Transport 的实际部署**：`CxlAllocationStrategy` 和 CXL 相关代码存在，但 CXL 内存的实际使用场景和性能特征未确认。

6. **Multi-Protocol 模式**：`ENABLE_MULTI_PROTOCOL` 条件编译下的 `mp_registerLocalMemory` 和 `mp_submitTransfer` 的具体使用场景未确认。

7. **Agent 场景的具体性能瓶颈**：当前分析基于源码阅读，缺乏实际 agent workload 下的性能数据验证。特别是 prefix 共享比例、跨节点传输延迟、eviction 命中率等关键指标。
