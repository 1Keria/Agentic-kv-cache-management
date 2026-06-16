# KV Cache 关键源码文件索引

> 日期：2026-06-12
> 用途：快速定位四大框架的 KV cache 相关核心源码

---

## SGLang

### 核心缓存模块 (`python/sglang/srt/mem_cache/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `radix_cache.py` | `RadixCache`, `TreeNode` | Radix tree KV cache 核心 | 核心数据结构，prefix 匹配算法 |
| `base_prefix_cache.py` | `BasePrefixCache` | Prefix cache 基类 | 抽象接口定义 |
| `common.py` | `ReqToTokenPool`, `TokenToKVPool` | Token 级内存池 | GPU 内存分配管理 |
| `chunk_cache.py` | `ChunkCache` | Chunk 级缓存 | Chunked prefill 支持 |
| `hiradix_cache.py` | `HiRadixCache` | 层级 RadixCache | GPU/CPU/Disk 层级 |
| `unified_radix_cache.py` | `UnifiedRadixCache` | 统一缓存组件 | 多种缓存策略统一管理 |
| `swa_radix_cache.py` | `SWARadixCache` | Sliding Window Attention 缓存 | 长上下文支持 |
| `mamba_radix_cache.py` | `MambaRadixCache` | Mamba 模型缓存 | Mamba 架构支持 |
| `radix_cache_cpp.py` | C++ RadixCache 绑定 | 高性能实现 | 性能优化 |
| `hicache_storage.py` | `HiCacheStorage` | HiCache 存储后端 | 层级存储抽象 |

### 存储后端 (`python/sglang/srt/mem_cache/storage/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `lmcache/lmc_radix_cache.py` | `LMCRadixCache` | LMCache 集成 | 外部 KV 存储集成 |
| `nixl/hicache_nixl.py` | `HiCacheNIXL` | NIXL 存储 | RDMA/远程存储 |
| `simm/hicache_simm.py` | `HiCacheSIMM` | SIMM 存储 | SSD offload |
| `hf3fs/storage_hf3fs.py` | `StorageHF3FS` | 3FS 存储 | 分布式文件系统存储 |

### 调度器 (`python/sglang/srt/managers/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `scheduler.py` | `Scheduler` | 核心调度器 | cache-aware 调度 |
| `schedule_policy.py` | `SchedulePolicy`, `LPM`, `DFSWeight` | 调度策略 | prefix 匹配优先级 |
| `cache_controller.py` | `CacheController` | Cache 控制器 | cache 状态管理 |

### Session 管理 (`python/sglang/srt/session/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `session_controller.py` | `SessionController` | Session 控制器 | 跨 turn KV 持久化 |
| `streaming_session.py` | `StreamingSession` | 流式 session | streaming 模式支持 |

### Disaggregation (`python/sglang/srt/disaggregation/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `prefill.py` | Prefill node 逻辑 | Prefill 分离 | disaggregated 架构 |
| `decode.py` | Decode node 逻辑 | Decode 分离 | disaggregated 架构 |
| `decode_hicache_mixin.py` | `DecodeHiCacheMixin` | Decode HiCache | decode 端缓存管理 |

### 其他

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `model_executor/pool_configurator.py` | `PoolConfigurator` | 内存池配置 | GPU 内存配置 |
| `observability/metrics_collector.py` | 指标收集 | cache 命中率监控 | 可观测性 |
| `kv_canary/radix_cache_walker.py` | Cache 遍历 | cache 状态检查 | 调试/监控 |

---

## vLLM

### v1 核心 (`vllm/v1/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `core/sched/scheduler.py` | `Scheduler` | v1 调度器 | cache-aware 调度 |
| `core/sched/interface.py` | `SchedulerInterface` | 调度器接口 | 抽象定义 |
| `core/sched/output.py` | `SchedulerOutput` | 调度输出 | cache 命中信息 |
| `worker/block_table.py` | `BlockTable` | Block table | block 管理 |
| `worker/gpu/block_table.py` | `GPUBlockTable` | GPU block table | GPU 端 block |
| `kv_cache_interface.py` | `KVCacheInterface` | KV cache 接口 | 抽象接口 |
| `metrics/stats.py` | 统计信息 | cache 命中统计 | 可观测性 |

### 配置 (`vllm/config/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `scheduler.py` | `SchedulerConfig` | 调度器配置 | cache 相关配置 |

### 分布式/传输 (`vllm/distributed/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `kv_transfer/kv_connector/v1/offloading/scheduler.py` | Offloading 调度 | KV offload | offload 调度 |
| `ec_transfer/` | EC transfer | Engine 间传输 | 跨 engine 复用 |

---

## LMCache

### 核心 (`lmcache/v1/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `cache_engine.py` | `CacheEngine` | Cache engine 核心 | 主入口 |
| `manager.py` | `Manager` | 管理器 | 生命周期管理 |

### Storage Backend (`lmcache/v1/storage_backend/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `abstract_backend.py` | `StorageBackend` | 存储后端抽象 | 接口定义 |
| `storage_backend_listener.py` | 监听器 | 异步事件 | 异步存储 |
| `connector/__init__.py` | Connector | 连接器 | 远程存储连接 |
| `connector_client_base.py` | `ConnectorClientBase` | 连接器基类 | 远程存储客户端 |

### Lookup Client (`lmcache/v1/lookup_client/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `abstract_client.py` | `LookupClient` | Lookup 抽象 | 接口定义 |
| `lmcache_lookup_client.py` | `LMCacheLookupClient` | LMCache lookup | 本地/远程查找 |
| `mooncake_lookup_client.py` | `MooncakeLookupClient` | Mooncake lookup | Mooncake 集成 |
| `lmcache_async_lookup_client.py` | 异步 lookup | 异步查找 | 性能优化 |
| `hit_limit_lookup_client.py` | Hit limit | 命中限制 | 容量控制 |
| `chunk_statistics_lookup_client.py` | Chunk 统计 | 统计分析 | 分析工具 |
| `factory.py` | 工厂方法 | 客户端创建 | 实例化 |

### Offload Server (`lmcache/v1/offload_server/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `abstract_server.py` | `OffloadServer` | Offload 服务抽象 | 接口定义 |
| `zmq_server.py` | `ZMQServer` | ZMQ 服务 | 通信实现 |

### Cache Controller (`lmcache/v1/cache_controller/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `controllers/kv_controller.py` | `KVController` | KV 控制器 | cache 控制 |

### Multiprocess (`lmcache/v1/multiprocess/modules/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `gpu_transfer.py` | GPU transfer | GPU 数据传输 | 跨进程传输 |
| `lookup.py` | Multiprocess lookup | 多进程查找 | 多进程支持 |
| `blend_v3.py` | Blend v3 | KV blend | KV 混合 |

### Integration (`lmcache/integration/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `vllm/vllm_v1_adapter.py` | `VLLMV1Adapter` | vLLM v1 适配器 | vLLM 集成 |
| `sglang/sglang_adapter.py` | `SGLangAdapter` | SGLang 适配器 | SGLang 集成 |
| `sglang/multi_process_adapter.py` | 多进程适配器 | 多进程 SGLang | 多进程支持 |

### 其他

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `utils.py` | 工具函数 | cache key 等 | 辅助功能 |
| `observability.py` | 可观测性 | 指标/日志 | 监控 |
| `v1/api_server/__main__.py` | API server | 服务入口 | 独立服务 |
| `v1/internal_api_server/vllm/cache_api.py` | vLLM cache API | vLLM 接口 | vLLM 集成 |

---

## Mooncake

### Mooncake Store (`mooncake-store/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `include/storage_backend.h` | `StorageBackend` | 存储后端 | 核心存储接口 |
| `include/transfer_task.h` | `TransferTask` | 传输任务 | 数据传输 |
| `include/allocation_strategy.h` | `Allocator` | 分配策略 | 内存分配 |
| `include/local_hot_cache.h` | `LocalHotCache` | 本地热缓存 | 本地缓存 |
| `include/master_service.h` | `MasterService` | Master 服务 | 元数据管理 |
| `include/replica.h` | `Replica` | 副本管理 | 数据复制 |
| `src/storage_backend.cpp` | 存储后端实现 | 核心实现 | 实现细节 |
| `src/master_service.cpp` | Master 实现 | 元数据服务 | 实现细节 |
| `src/rpc_service.cpp` | RPC 服务 | 远程调用 | 通信实现 |

### Transfer Engine (`mooncake-transfer-engine/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `include/transfer_engine.h` | `TransferEngine` | 传输引擎 | 核心传输接口 |
| `include/transfer_engine_impl.h` | `TransferEngineImpl` | 传输引擎实现 | 实现细节 |
| `include/transfer_metadata.h` | `TransferMetadata` | 传输元数据 | 元数据管理 |
| `include/transport/transport.h` | `Transport` | 传输层抽象 | 传输抽象 |
| `src/transfer_metadata.cpp` | 元数据实现 | 实现细节 | 实现细节 |

### TENT (下一代传输引擎) (`mooncake-transfer-engine/tent/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `include/tent/transfer_engine.h` | TENT 引擎 | 新一代传输 | 未来架构 |
| `include/tent/runtime/transfer_engine_impl.h` | TENT 实现 | 实现细节 | 实现细节 |
| `include/tent/runtime/control_plane.h` | 控制平面 | 控制逻辑 | 控制面 |
| `include/tent/runtime/proxy_manager.h` | 代理管理 | 代理服务 | 代理 |
| `include/tent/runtime/progress_worker.h` | 进度工作器 | 进度跟踪 | 进度管理 |

### Python Integration (`mooncake-integration/`, `mooncake-wheel/`)

| 文件 | 关键类/函数 | 作用 | 为什么相关 |
|------|------------|------|-----------|
| `mooncake-integration/store/store_py.cpp` | Python 绑定 | Store Python API | Python 接口 |
| `mooncake-integration/transfer_engine/transfer_engine_py.cpp` | Python 绑定 | Transfer Python API | Python 接口 |
| `mooncake-wheel/mooncake/mooncake_connector_v1.py` | vLLM connector v1 | vLLM 集成 | vLLM 集成 |
| `mooncake-wheel/mooncake/mooncake_store_service.py` | Store 服务 | Python Store | Python 服务 |
| `mooncake-wheel/mooncake/structured_object_store.py` | 结构化存储 | 对象存储 | 高级 API |

### 设计文档 (`docs/source/design/`)

| 文件 | 内容 | 为什么相关 |
|------|------|-----------|
| `hicache-design.md` | HiCache 设计 | 层级缓存设计 |
| `ssd-offload.md` | SSD offload 设计 | SSD offload 设计 |
| `transfer-engine/efa_transport.md` | EFA 传输 | RDMA 传输设计 |
| `conductor/conductor-architecture-design.md` | Conductor 架构 | 分布式调度 |
| `conductor/indexer-api-design.md` | Indexer API | 索引设计 |

---

## 总结

### 框架定位对比

| 框架 | 定位 | 核心数据结构 | 主要语言 |
|------|------|-------------|---------|
| SGLang | Engine 内部 KV 管理 | RadixTree (TreeNode) | Python + C++ |
| vLLM | Engine 内部 KV 管理 | Block (BlockTable) | Python |
| LMCache | 外部 KV 存储层 | CacheEngine + StorageBackend | Python |
| Mooncake | 分布式 KV 存储 + 传输 | StorageBackend + TransferEngine | C++ + Python |

### 关键差异

- **SGLang**: Token-level prefix 匹配，RadixTree 结构天然支持 L0/L1/L2
- **vLLM**: Block-level hash 匹配，线性 prefix only
- **LMCache**: 外部存储层，可同时接入 SGLang 和 vLLM
- **Mooncake**: 分布式架构，跨节点 KV cache 传输
