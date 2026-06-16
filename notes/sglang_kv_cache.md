# SGLang KV Cache 源码分析

## 1. KV cache 基本抽象

### 1.1 核心数据结构

**TreeNode**（`radix_cache.py:201-262`）是 Radix Tree 的基本节点：

| 字段 | 类型 | 含义 |
|------|------|------|
| `key` | `RadixKey` | 该节点对应的 token id 序列（逻辑键） |
| `value` | `Optional[torch.Tensor]` | GPU HBM 上的 KV cache 索引（int64 tensor），`None` 表示已驱逐 |
| `host_value` | `Optional[torch.Tensor]` | CPU DRAM 上的 KV cache 索引 |
| `lock_ref` | `int` | 引用计数，>0 时不可驱逐 |
| `last_access_time` | `float` | 最近访问时间（用于 LRU 驱逐） |
| `children` | `defaultdict(TreeNode)` | 子节点字典，键为 `child_key` |
| `parent` | `TreeNode` | 父节点 |
| `hash_value` | `Optional[List[str]]` | 每个 page 的 SHA256 哈希（用于 storage 层匹配） |
| `hit_count` | `int` | 命中次数（触发 write-through 阈值） |
| `host_ref_counter` | `int` | 主机层引用计数（保护存储操作期间 host_value 不被驱逐） |
| `priority` | `int` | 优先级（用于优先级感知驱逐） |
| `write_through_pending_id` | `Optional[int]` | 正在写穿的节点 ID |

**RadixKey**（`radix_cache.py:56-198`）是查找键的抽象：

| 字段 | 含义 |
|------|------|
| `token_ids` | `array[int]`，原始 token id 序列 |
| `extra_key` | `Optional[str]`，命名空间隔离键（如 LoRA ID、cache salt） |
| `is_bigram` | `bool`，EAGLE 投机解码下使用 bigram 模式 |

**UnifiedTreeNode**（`unified_radix_cache.py:77-133`）是统一缓存中的多组件节点：

- `component_data: list[ComponentData]`：按 ComponentType 索引，支持 Full/SWA/Mamba 三种组件
- 每个 ComponentData 独立持有 `value`（设备端）、`host_value`（主机端）、`lock_ref`、`host_lock_ref`
- 替代了 TreeNode 的单一 value/lock_ref，实现细粒度多组件管理

**Req**（`schedule_batch.py`）中与 KV cache 相关的字段：

| 字段 | 含义 |
|------|------|
| `prefix_indices` | 命中的 GPU KV cache 索引列表 |
| `last_node` | 最后命中的 TreeNode |
| `last_host_node` | 最后命中的主机端 TreeNode |
| `best_match_node` | 最佳匹配节点（所有组件验证通过的锚点） |
| `host_hit_length` | 主机端命中的 token 数（需 load_back） |
| `cache_protected_len` | 受 cache 保护的长度 |
| `num_matched_prefix_tokens` | 匹配的 prefix token 总数 |

### 1.2 Key 设计

**两层 key 结构**：

1. **child_key**（`radix_cache.py:173-183`）：树遍历的哈希键
   - `page_size=1`：单个 token id（bigram 模式下为 `(t[i], t[i+1])` 元组）
   - `page_size>1`：`tuple(token_ids[:page_size])`
   - 若有 `extra_key`，则包装为 `(extra_key, plain)` 命名空间

2. **hash_value**（`radix_cache.py:185-198`）：存储层键
   - 每 page 一个 SHA256 哈希
   - 支持增量哈希（`prior_hash` 参数实现链式哈希）
   - `hash_page(start, end)` 方法计算单个 page 的哈希

**匹配粒度**：精确 prefix match + extra_key 命名空间隔离。不同 `extra_key` 的请求即使 token 相同也不共享 KV cache（`radix_cache.py:337-365` 的 match_prefix 文档明确说明）。

### 1.3 Value 设计

**三级 value 存储**：

| 层级 | 字段 | 物理位置 | 内容 |
|------|------|----------|------|
| L1 (GPU) | `node.value` | GPU HBM | `torch.Tensor` (int64)，KV pool 中的索引 |
| L2 (CPU) | `node.host_value` | CPU DRAM | `torch.Tensor` (int64)，host pool 中的索引 |
| L3 (Storage) | 通过 `hash_value` 索引 | Disk/Remote | 序列化的 KV tensor 原始数据 |

**内存池架构**：

- `ReqToTokenPool`（`memory_pool.py:17`）：`req_to_token[req_idx, token_pos]` = KV pool 索引
  - 二维映射表：request → token positions → KV cache slots
  - `write((req_idx, slice), indices)` 写入匹配的 prefix 索引

- `TokenToKVPoolAllocator`：管理 KV cache 物理内存
  - `alloc(num_tokens)` 分配 token slots
  - `free(indices)` 释放 token slots
  - `available_size()` 返回可用空间

- `HostKVCache`（`memory_pool_host.py`）：CPU 端 KV cache pool
  - `MHATokenToKVPoolHost` / `MLATokenToKVPoolHost`
  - 通过 `hicache_ratio` 或 `hicache_size` 配置大小

**实际 KV tensor 存储**：由 `TokenToKVPool` 的子类持有（`memory_pool.py`）：
- `MHATokenToKVPool`：标准 Multi-Head Attention，`k_cache[layer][index]`, `v_cache[layer][index]`
- `MLATokenToKVPool`：Multi-head Latent Attention（DeepSeek），压缩表示
- `DSATokenToKVPool`：DeepSeek Attention

### 1.4 引用计数机制

**lock_ref**（`radix_cache.py:210`）的工作方式：

1. **增加引用** `inc_lock_ref(node)`（`radix_cache.py:566-579`）：
   - 从 node 向上遍历到 root_node
   - 每个 node 的 `lock_ref += 1`
   - 若 `lock_ref` 从 0 变为 1：`evictable_size_ -= len(key)`，`protected_size_ += len(key)`
   - 更新叶子节点状态

2. **减少引用** `dec_lock_ref(node)`（`radix_cache.py:581-600`）：
   - 从 node 向上遍历到 root_node
   - 每个 node 的 `lock_ref -= 1`
   - 若 `lock_ref` 从 1 变为 0：`evictable_size_ += len(key)`，`protected_size_ -= len(key)`
   - 更新叶子节点状态

3. **谁持有引用**：
   - 正在运行的请求持有其 `last_node` 的引用（`PrefillAdder.add_one_req` 中 `inc_lock_ref`，`release_kv_cache` 中 `dec_lock_ref`）
   - write-through 写入期间临时持有引用
   - load-back 操作期间临时持有引用
   - root_node 永久 `lock_ref = 1`

4. **host_ref_counter**（`radix_cache.py:217-246`）：
   - 保护 `host_value` 在存储操作期间不被驱逐
   - `protect_host()` 递增，`release_host()` 递减
   - 用于 prefetch/backup 异步操作期间保护节点

## 2. 生命周期

### 2.1 Allocate

**请求入口**：`_add_request_to_queue`（`scheduler.py:2178`）→ `waiting_queue`

**Prefill 分配**（`common.py:346-409`，`alloc_for_extend`）：

1. `alloc_req_slots`：从 `ReqToTokenPool` 分配请求行
2. `alloc_token_slots` 或 `alloc_paged_token_slots_extend`：
   - 先调用 `evict_from_tree_cache` 确保空间
   - 从 `TokenToKVPoolAllocator` 分配 KV cache slots
3. `write_cache_indices`：将 prefix 索引和新分配的索引写入 `req_to_token`

**Decode 分配**（`common.py:441-480`，`alloc_for_decode`）：

1. 每个 decode step 分配 1 个 token slot（或 spec decoding 下多个）
2. `alloc_token_slots` 或 `alloc_paged_token_slots_decode`
3. 写入 `req_to_token[req_pool_idx, seq_len]` = 新分配的 slot

### 2.2 Prefill 写入

**关键流程**：

1. `get_new_batch_prefill`（`scheduler.py:2571`）→ `policy.calc_priority`（计算 prefix match）
2. `req.init_next_round_input(tree_cache)`：调用 `match_prefix_for_req`（`schedule_policy.py:85-130`）
   - `tree_cache.match_prefix(MatchPrefixParams(key=RadixKey(...)))`
   - 结果写入 `req.prefix_indices`、`req.last_node`、`req.host_hit_length` 等
3. `PrefillAdder.add_one_req`（`schedule_policy.py:858-1023`）：
   - 若 `req.needs_host_load_back()`：调用 `tree_cache.init_load_back` 加载主机端 KV
   - 更新 `req.prefix_indices`，计算 `extend_input_len = total_tokens - prefix_len`
   - `inc_lock_ref(req.last_node)` 保护命中节点
4. `alloc_for_extend`：分配新 KV cache slots
5. 前向传播计算新 token 的 KV，写入 KV pool

### 2.3 Decode Append

1. `update_running_batch`（`scheduler.py:2864`）：
   - 检查 `check_decode_mem()`
   - 若内存不足，执行 `retract_decode` 驱逐部分请求
2. `alloc_for_decode`：为每个 decode token 分配 1 slot
3. 写入 `req_to_token[req_pool_idx, seq_len]`
4. 前向传播：使用 prefix_indices + 新分配位置做 attention

### 2.4 命中复用

**命中后的处理**：

1. `match_prefix`（`radix_cache.py:337-395`）：
   - 调用 `_match_prefix_helper` 沿树遍历
   - 返回 `MatchResult(device_indices=value, last_device_node=last_node, ...)`
   - 若匹配在节点内部结束，调用 `_split_node` 分裂节点

2. **跳过 prefill 的机制**：
   - `req.prefix_indices` = 命中的 GPU KV 索引
   - `req.extend_input_len = len(full_fill_ids) - len(prefix_indices)`
   - 只对未命中的 token 执行 prefill 计算
   - 命中部分的 KV cache 索引直接写入 `req_to_token`，无需重新计算

3. **跨 turn 复用**（Session/Streaming Session）：
   - `StreamingSession.try_match_prefix`（`streaming_session.py:237-276`）
   - 从 `SessionSlot` 恢复 `req_pool_idx`、`kv_committed_len`
   - `prefix_len = min(req.kv_committed_len, len(key.token_ids))`
   - 直接从 `req_to_token[req_pool_idx, :prefix_len]` 获取 KV 索引
   - 无需重新 prefill，因为 KV tensor 仍在 GPU pool 中

4. **非 streaming session 的跨 turn 复用**：
   - `Session.create_req`（`session_controller.py:103-256`）拼接前一轮的 `origin_input_ids + output_ids`
   - 新请求携带完整历史 token ids，自然命中 radix cache 中前一轮存入的 KV

### 2.5 Evict/Free/Offload

**GPU 驱逐**（`radix_cache.py:537-564`）：

1. 触发条件：`allocator.available_size() < num_tokens`（`common.py:264-267`）
2. 算法：最小堆 + `eviction_strategy.get_priority(node)`
   - 默认 LRU：按 `last_access_time` 排序
   - 支持自定义策略
3. 从 `evictable_leaves` 集合中选叶子节点
4. `token_to_kv_pool_allocator.free(x.value)` 释放物理内存
5. `_delete_leaf(x)` 从树中删除节点

**HiRadixCache 的层级驱逐**（`hiradix_cache.py:1033-1104`）：

1. **write_back 策略**：先 `write_backup(x, write_back=True)` 备份到 CPU，再 `_evict_backuped(x)` 从 GPU 驱逐
2. **write_through 策略**：若未备份，直接 `_evict_regular(x)` 删除（节点永久丢失）
3. `_evict_backuped`：`cache_controller.evict_device(node.value)` 释放 GPU，`node.value = None`

**CPU 驱逐**（`hiradix_cache.py:1106-1139`）：

1. `evict_host(num_tokens)`：从 `evictable_host_leaves` 中选节点
2. 仅驱逐已从 GPU 驱逐的节点（`not x.evicted` 则跳过）
3. `cache_controller.evict_host(x.host_value)` 释放 CPU 内存
4. 从树中完全删除节点

**UnifiedRadixCache 的驱逐**（`unified_radix_cache.py:578-1464`）：

- 多组件级联驱逐：`_cascade_evict` 按优先级从 trigger 向下级联
- 设备叶子（D-leaf）：Full KV 在设备上、无子节点在设备上、无锁
- 主机叶子（H-leaf）：evicted、Full host_value 存在、无子节点、无锁
- `_evict_device_leaf`：backuped → 降级到 host；未备份 + write_back → 先备份再降级；未备份 + write_through → 完全删除

### 2.6 Request 结束后的处理

**`release_kv_cache`**（`common.py:484-537`）：

1. `tree_cache.cache_finished_req(req, is_insert=...)`：
   - 获取完整 token_ids = `origin_input_ids + output_ids[:kv_committed_len]`
   - 获取 KV 索引 = `req_to_token[req_pool_idx, :len(token_ids)]`
   - 若 `is_insert`：`insert(InsertParams(key=radix_key, value=values))`
     - 插入 radix tree，RadixCache 接管 KV 索引
     - 释放 tree 中已存在的重复索引（`free(kv_indices[cache_protected_len:prefix_len])`）
   - 释放 page 未对齐的尾部（`free(kv_indices[key_len:])`）
2. `dec_lock_ref(req.last_node)` 释放请求持有的树锁
3. `req.pop_overallocated_kv_cache()` 处理超分配
4. 释放超分配部分的 KV cache slots
5. `req_to_token_pool.free(req)` 释放请求行

**缓存保留时长**：
- RadixCache 中已插入的节点保留直到被驱逐（LRU/优先级策略）
- 无显式 TTL；驱逐仅由内存压力驱动
- `lock_ref > 0` 的节点永远不会被驱逐

**StreamingSession** 下：
- `try_cache_finished_req`（`streaming_session.py:278-342`）将 KV 状态保存到 `SessionSlot`
- 不释放 KV cache，slot 持有 `req_pool_idx` 和 `kv_committed_len`
- 下一 turn 通过 `try_match_prefix` 恢复，无需重新 prefill
- Session 关闭时 `release_session` 释放所有资源

## 3. 内存层级

### 3.1 GPU HBM

- **存储内容**：KV cache tensor 的物理数据（`k_cache[layer]`, `v_cache[layer]`）
- **索引管理**：`TokenToKVPoolAllocator` 管理可用 slot
- **TreeNode.value**：int64 tensor，指向 KV pool 中的索引
- **大小**：由 `--mem-fraction-static` 决定，通常占 GPU 内存的 80-90%

### 3.2 CPU DRAM

- **存储内容**：KV cache 的备份拷贝（GPU → CPU 写穿/写回）
- **索引管理**：`HostKVCache`（`memory_pool_host.py`），`MHATokenToKVPoolHost` / `MLATokenToKVPoolHost`
- **TreeNode.host_value**：int64 tensor，指向 host pool 中的索引
- **大小**：由 `--hicache-ratio` 或 `--hicache-size` 配置
- **初始化**：在 `HiRadixCache.__init__`（`hiradix_cache.py:78-101`）中创建

### 3.3 Disk SSD

- **存储内容**：KV cache 页面的序列化二进制数据
- **实现**：`HiCacheFile`（`hicache_storage.py:319-614`）
  - 每 page 一个 `.bin` 文件，键为 SHA256 哈希 + `config_suffix`
  - `LRUFileEvictor` 管理 disk 空间，支持磁盘级 LRU 驱逐
  - `batch_exists_v2` / `batch_get_v2` / `batch_set_v2` 批量操作接口
- **大小**：无硬上限，由 evictor 的容量策略控制

### 3.4 Remote Memory

- **NIXL**（`hicache_nixl.py`）：高性能存储后端
  - 使用 NIXL 插件架构（RDMA、GDS 等）
  - `nixl_agent` 管理存储注册和传输
  - 支持 direct I/O 和对象存储插件
- **SIMM**（`hicache_simm.py`）：模拟存储后端，用于测试
- **LMCache**（`lmc_radix_cache.py`）：与 LMCache 库集成
  - 支持多进程模式（MP）和进程内模式（IP）
  - `LMCacheLayerwiseConnector` 支持分层加载
  - 通过外部 KV cache 存储服务提供远程访问

### 3.5 层级迁移机制

**GPU → CPU（Backup/Write-through）**：

1. **Write-through**（`hiradix_cache.py:759-789`，`write_backup`）：
   - 触发条件：`node.hit_count >= write_through_threshold`（默认 threshold=1 或 2）
   - 流程：`cache_controller.write(device_indices=node.value)` → DMA 传输 → `node.host_value = host_indices`
   - 异步：`_track_write_through_node` 跟踪，`writing_check` 确认完成

2. **Write-back**（`hiradix_cache.py:1050-1053`）：
   - 在驱逐时才写入 CPU
   - `write_backup(x, write_back=True)` 同步写入，等待 DMA 完成

**CPU → Storage（Storage Backup）**：

1. `write_backup_storage`（`hiradix_cache.py:835-860`）：
   - 在 write-through ACK 完成后触发
   - `cache_controller.write_storage(host_value, key, hash_value)` → 存储层写入
   - 异步：`ongoing_backup` 跟踪，`drain_storage_control_queues` 处理 ACK

**Storage → CPU（Prefetch）**：

1. `prefetch_from_storage`（`hiradix_cache.py:1471-1528`）：
   - 触发条件：`enable_storage` 且 `prefetch_length >= prefetch_threshold`（默认 256 tokens）
   - 在请求入队时触发（`scheduler.py:2156-2176`，`_prefetch_kvcache`）
   - 分配 host pool 空间 → `cache_controller.prefetch()` 异步预取
   - `check_prefetch_progress` 检查进度，完成后插入 host radix tree

**CPU → GPU（Load Back）**：

1. `load_back`（`hiradix_cache.py:1141-1211`）：
   - 触发条件：`match_prefix` 发现节点 evicted 但 backuped
   - 在 `PrefillAdder.add_one_req` 中调用 `init_load_back`（`schedule_policy.py:932-944`）
   - 流程：收集 evicted 节点的 host_value → `cache_controller.load()` DMA 传输 → 恢复 `node.value`
   - 保护 ancestor 节点不被驱逐（`inc_lock_ref` / `dec_lock_ref`）

**统一缓存中的层级迁移**（`unified_radix_cache.py:1466-1683`）：
- 所有迁移都通过组件化接口：`build_hicache_transfers` / `commit_hicache_transfer`
- 支持 sidecar pool（如 DSA indexer）的联合传输
- 多组件级联操作：Full KV + SWA + Mamba 同时迁移

## 4. Prefix cache / reuse 机制

### 4.1 RadixCache 匹配算法

**`_match_prefix_helper`**（`radix_cache.py:622-646`）：

```
输入: node=root_node, key=待匹配的 token 序列
输出: (value_list, last_node)

1. access_time = time.monotonic()
2. node.last_access_time = access_time
3. child_key = key.child_key(page_size)
4. while key 非空 且 child_key in node.children:
   a. child = node.children[child_key]
   b. child.last_access_time = access_time  # 刷新访问时间
   c. prefix_len = child.key.match(key, page_size)
      # match() 使用指数搜索 + 二分搜索找到第一个分歧点
   d. if prefix_len < len(child.key):
      # 部分匹配，分裂节点
      new_node = _split_node(child.key, child, prefix_len)
      value.append(new_node.value)
      return (value, new_node)
   e. else:
      # 完全匹配当前节点
      value.append(child.value)
      node = child
      key = key[prefix_len:]  # 剩余部分继续匹配
      if key 非空: child_key = key.child_key(page_size)
5. return (value, node)
```

**时间复杂度**：
- 最好 O(1)：第一个 child_key 不匹配
- 最坏 O(L/P)：L=token 长度，P=page_size，每层一个 page
- `_match_prefix_helper` 每层 O(1) 哈希查找
- `RadixKey.match`（`radix_cache.py:138-171`）：使用指数搜索（gallop）+ 二分搜索
  - 长共享前缀：O(log N) 而非 O(N)（N 为分歧点位置）
  - 短共享前缀：O(1) 到 O(log N)

**HiRadixCache 的 `match_prefix`**（`hiradix_cache.py:1438-1469`）：
- 额外跟踪 `host_hit_length`：遍历 evicted 节点累计 host_value 长度
- `last_host_node`：最后一个有 host_value 的祖先节点
- 统一缓存的 `match_prefix`（`unified_radix_cache.py:535-560`）还使用多组件验证器

### 4.2 Partial hit 处理

**节点分裂**（`_split_node`，`radix_cache.py:648-668`）：

当匹配在节点内部结束时：
1. 创建 `new_node` 包含匹配的前缀部分
2. 原 `child` 保留未匹配的尾部
3. `new_node.value = child.value[:split_len].clone()`
4. `child.value = child.value[split_len:].clone()`
5. `new_node` 继承 `child.lock_ref`
6. 调整 `hash_value` 分裂

**partial hit 后的处理**：
- `req.prefix_indices` = 匹配部分的 KV 索引
- `req.extend_input_len = total_len - matched_len`
- 只 prefill 未匹配的部分

### 4.3 跨请求/跨节点复用

**跨请求复用**：
- 所有请求共享同一棵 Radix Tree
- 命中已有节点时直接复用其 `value`（KV 索引）
- `extra_key` 隔离不同命名空间（LoRA、cache_salt 等）

**In-batch prefix caching**（`schedule_policy.py:247-293`）：
- 维护 `waiting_queue_radix_tree`（轻量模拟树）
- 若请求的 `prefix_indices` 长度 <= `IN_BATCH_PREFIX_CACHING_CHECK_THRESHOLD`（默认 32）
- 在 `waiting_queue_radix_tree` 中查找同 prefix 的请求
- 优先调度其中一个，使其他请求后续命中

**跨 worker 复用**：
- 同一 TP group 内所有 worker 维护相同的 radix tree 结构
- `HiRadixCache._all_reduce` / `_barrier_attn_groups` 同步操作结果
- KV cache 数据在所有 TP rank 上冗余存储

**跨节点复用**：
- Disaggregation 模式下通过 KV transfer 实现
- Prefill node 计算 KV → 传输到 Decode node
- Decode node 可启用 radix cache（`--disaggregation-decode-enable-radix-cache`）
- Storage backend（NIXL/LMCache）可实现跨节点 KV 共享

### 4.4 复用时的数据共享方式

**GPU 内复用**：指针共享（零拷贝）
- `req.prefix_indices` 直接引用 `node.value` 中的索引
- `write_cache_indices`（`common.py:64-110`）将 prefix 索引写入 `req_to_token`
- 多个请求的 `req_to_token[req_idx, :prefix_len]` 指向相同的 KV pool slots
- 引用计数通过 `inc_lock_ref` / `dec_lock_ref` 管理

**CPU → GPU 复用**：DMA 拷贝
- `load_back`（`hiradix_cache.py:1141-1211`）：`cache_controller.load()` DMA 传输
- 新分配的 GPU slots 存储拷贝的数据
- 拷贝后 `node.value` 更新为新 GPU 索引

**Storage → CPU 复用**：异步 I/O 拷贝
- `prefetch_from_storage`：从存储读取到 host pool
- `cache_controller.prefetch()` 异步操作
- 完成后插入 host radix tree

## 5. 调度器与 KV cache 的关系

### 5.1 Cache 命中信息传递

**调用链**：
1. `policy.calc_priority(waiting_queue, running_batch)`（`schedule_policy.py:170-221`）
2. 对每个请求调用 `match_prefix_for_req(tree_cache, req)`（`schedule_policy.py:85-130`）
3. `match_prefix_for_req` 调用 `tree_cache.match_prefix(MatchPrefixParams(key=...))`
4. 结果写入请求字段：
   - `req.prefix_indices` = 命中的 GPU KV 索引
   - `req.last_node` = 命中的树节点
   - `req.last_host_node` = 命中的主机端节点
   - `req.best_match_node` = 最佳匹配节点
   - `req.host_hit_length` = 主机端命中 token 数
   - `req.num_matched_prefix_tokens` = 匹配的 prefix 总 token 数

### 5.2 Cache 命中对 prefill 的影响

1. `req.init_next_round_input(tree_cache)`（在 `scheduler.py:2716` 调用）：
   - 内部调用 `match_prefix_for_req`，设置 `req.prefix_indices`
   - `req.extend_input_len = len(full_untruncated_fill_ids) - len(req.prefix_indices)`
   - 命中的 token 不需要 prefill

2. `PrefillAdder.add_one_req`（`schedule_policy.py:858-1023`）：
   - `prefix_len = len(req.prefix_indices)`
   - `real_input_tokens = req.extend_input_len - req.host_hit_length`
   - `total_tokens = req.extend_input_len + max_new + page_size`
   - 若 `req.needs_host_load_back()`：调用 `tree_cache.init_load_back` 从主机加载

3. **命中节省的 prefill**：
   - 直接命中（GPU）：跳过 `len(req.prefix_indices)` 个 token 的 prefill
   - 主机命中（需 load_back）：需 DMA 传输，但仍跳过计算
   - 存储命中（需 prefetch + load_back）：需存储 I/O + DMA，但仍跳过计算

### 5.3 Schedule Policy 实现

**`SchedulePolicy`**（`schedule_policy.py:149-416`）：

| 策略 | 类型 | 实现 |
|------|------|------|
| LPM | CacheAware | 按 `num_matched_prefix_tokens` 降序排序 |
| DFS-weight | CacheAware | 按 radix tree 的 DFS 权重排序（同节点请求聚合） |
| FCFS | CacheAgnostic | 按 `wait_queue_entry_time` 排序 |
| LOF | CacheAgnostic | 按 `max_new_tokens` 降序 |
| RANDOM | CacheAgnostic | 随机排序 |
| ROUTING_KEY | CacheAgnostic | 按 `routing_key` 在 running batch 中的频率排序 |

**LPM 实现**（`schedule_policy.py:296-306`）：
- `_compute_prefix_matches` 对每个请求计算 `num_matched_prefix_tokens`
- 按 `-num_matched_prefix_tokens` 排序（命中多的先调度）
- in-batch prefix caching 降优先级：命中 >= `DEPRIORITIZE_THRESHOLD`（默认 32）的请求被移到队尾

**DFS-weight 实现**（`schedule_policy.py:308-328`）：
- 构建节点到请求的映射 `last_node_to_reqs`
- 计算每个节点的权重 = 子请求数量
- `_calc_weight`：自底向上累加权重
- `_get_dfs_priority`：DFS 遍历，按权重降序访问子节点
- 效果：同 prefix 的请求被连续调度，最大化 cache 局部性

**降级机制**（`schedule_policy.py:223-227`）：
- `LPM` 在 `len(waiting_queue) > 128` 时降级为 `FCFS`
- 避免 O(N) 的 prefix match 计算开销

### 5.4 Preemption 处理

**Priority Preemption**（`schedule_policy.py:1025-1094`，`preempt_to_schedule`）：
1. 当高优先级请求无法调度（`NO_TOKEN`）时触发
2. 从 running batch 中选最低优先级的请求
3. 验证：优先级差 > `priority_scheduling_preemption_threshold`
4. 验证：释放的 token 足够新请求使用
5. 执行：`running_batch.release_req(i, ...)` → `release_kv_cache`
6. 被抢占的请求重新加入 waiting queue

**Retract Decode**（`scheduler.py:2879-2940`）：
1. 触发条件：`not batch.check_decode_mem()`（KV 空间不足）
2. `batch.retract_decode(server_args)`：按策略选择请求驱逐
3. `release_kv_cache` 释放 KV cache
4. 被收回的请求标记 `is_retracted=True`，加入 waiting queue
5. 重新调度时可能命中 radix cache（`retracted_stain` 标记影响 hit rate 统计）

**Retract 后的 KV cache 处理**：
- `cache_finished_req` 在 retract 前被调用，将 KV 插入 radix tree
- 请求重新调度时 `match_prefix_for_req` 命中 radix tree
- 需要重新 prefill 驱逐后缺失的部分

## 6. Session 机制

### 6.1 SessionController

**`SessionController`**（`session_controller.py:272-404`）：

| 方法 | 功能 |
|------|------|
| `open(recv_req)` | 创建新 Session，指定 `capacity_of_str_len`、`streaming`、`timeout` |
| `close(recv_req)` | 关闭 Session，释放 KV cache |
| `maybe_reap(now, interval)` | 定期清理超时 Session（默认 1s 间隔） |

**Session 生命周期**：
1. 客户端调用 `open_session` → `SessionController.open`
2. 每轮对话通过 `session_params` 指定关联的 session
3. `Session.create_req`（`session_controller.py:103-256`）：
   - 拼接上一轮的 `origin_input_ids + output_ids[:max_new_tokens]`
   - 支持 `replace`（替换分支）、`drop_previous_output`、`offset` 等操作
   - 新请求携带完整历史，自然命中 radix cache
4. 客户端调用 `close_session` → `SessionController._close`
   - 释放 radix tree lock（`tree_cache.release_session(session_id)`）
   - 释放 multimodal features
   - 处理 inflight 请求的延迟关闭

### 6.2 跨 turn KV 持久化

**非 streaming session**：
- 依赖 radix cache 的自然持久化
- 上一轮结束时 `cache_finished_req` 将 KV 插入 radix tree
- 下一轮的新请求携带完整 token ids，命中 radix cache
- KV cache 保留到被驱逐为止，无显式保护

**Streaming session**（`streaming_session.py:128-638`）：
- **SessionSlot**（`streaming_session.py:39-122`）保存跨 turn 状态：
  - `req_pool_idx`：请求行索引
  - `kv_committed_len` / `kv_allocated_len`：KV 长度信息
  - `last_node`：radix tree 节点（持有 lock_ref）
  - `cache_protected_len`：受保护长度
  - Mamba 状态等

- **KV 持久化机制**：
  1. Turn 结束时 `try_cache_finished_req`（`streaming_session.py:278-342`）
     - `slot.save_from_req(req)` 保存状态到 slot
     - **不释放** `req_pool_idx`，KV tensor 仍在 GPU pool 中
     - `req.session.finish_req(req)` 更新 session 的 req_nodes
  2. 下一 turn `try_match_prefix`（`streaming_session.py:237-276`）
     - `slot.restore_to_req(req)` 恢复状态到新请求
     - `prefix_len = min(req.kv_committed_len, len(key.token_ids))`
     - 直接从 `req_to_token[req_pool_idx, :prefix_len]` 获取 KV 索引
     - 无需重新 prefill，KV tensor 从未离开 GPU
  3. Session 关闭时 `release_session`（`streaming_session.py:399-433`）
     - `dec_lock_ref(slot.last_node)` 释放树锁
     - 释放 [cache_protected_len, kv_allocated_len) 范围的 KV slots
     - 释放 mamba 状态

- **优势**：零开销跨 turn 复用，无需 prefill，无需 DMA
- **代价**：占用 GPU 内存直到 session 关闭

## 7. HiCache 层级架构

### 7.1 HiCache storage backend

**抽象接口 `HiCacheStorage`**（`hicache_storage.py:140-316`）：

| 方法 | 功能 |
|------|------|
| `exists(key)` | 检查键是否存在 |
| `batch_exists(keys)` | 返回连续存在的键数量 |
| `batch_exists_v2(keys, pool_transfers)` | 多池前缀匹配 |
| `get(key, target_location)` | 读取单个键 |
| `batch_get_v2(transfers)` | 批量读取到 host pool |
| `set(key, value)` | 写入单个键 |
| `batch_set_v2(transfers)` | 批量写入 |

**PoolTransfer**（`hicache_storage.py:91-106`）：统一传输描述符
- `name`：PoolName（KV/MAMBA/SWA/INDEXER/DRAFT）
- `host_indices` / `device_indices`：传输地址
- `keys`：存储层键
- `hit_policy`：ALL_PAGES 或 TRAILING_PAGES

**三种存储后端**：

1. **HiCacheFile**（`hicache_storage.py:319-614`）：
   - 本地磁盘文件存储
   - 每个 page 一个 `.bin` 文件
   - `LRUFileEvictor` 管理磁盘空间
   - 适用于开发/测试

2. **HiCacheNixl**（`hicache_nixl.py:33`）：
   - 基于 NIXL 高性能 I/O 框架
   - 支持多种后端插件（RDMA、GDS 等）
   - `NixlFileManager` 管理文件或对象存储
   - 适用于生产环境高性能场景

3. **LMCache 集成**（`lmc_radix_cache.py`）：
   - 与外部 LMCache 服务集成
   - 支持 MP（多进程）和 IP（进程内）模式
   - `LMCacheLayerwiseConnector` 支持分层加载
   - 适用于分布式 KV cache 共享

### 7.2 Unified radix cache

**`UnifiedRadixCache`**（`unified_radix_cache.py:261-2179`）：

**设计目标**：统一管理 Full KV、SWA、Mamba 三种组件的 cache

**核心组件**：
- `UnifiedTreeNode`：多 component_data 的树节点
- `UnifiedLRUList`：每个组件独立的 LRU 链表
- `TreeComponent` 子类：`FullComponent`、`SWAComponent`、`MambaComponent`
- `StreamingSession`：嵌入的流式会话管理

**组件化操作**：
- `match_prefix`：多组件验证器（`create_match_validator`）协同验证
- `insert`：每个组件独立 `update_component_on_insert_overlap`
- `evict`：级联驱逐（`_cascade_evict`）
- `inc_lock_ref` / `dec_lock_ref`：每个组件独立锁管理

**HiCache 集成**（`init_hicache`，`unified_radix_cache.py:464-530`）：
- 调用 `attach_hybrid_pool_to_unified_cache` 初始化
- 支持 `HybridCacheController` 和 `HybridCacheController`（DSA 模型）
- 统一的 backup/load_back/prefetch 流程

### 7.3 LMCache/NIXL/SIMM 集成

**LMCache**（`lmc_radix_cache.py`）：
- `LMCacheRadixCache` 继承自 `RadixCache`
- 重写 `match_prefix`：先查本地 radix tree，未命中则查 LMCache
- `init_load_back`：从 LMCache 加载到 GPU
- 支持两种模式：
  - IP（进程内）：`LMCacheLayerwiseConnector` 直接调用
  - MP（多进程）：`LMCacheMPConnector` 通过 IPC 通信

**NIXL**（`hicache_nixl.py`）：
- 实现 `HiCacheStorage` 接口
- 通过 NIXL 插件提供高性能 I/O
- 支持多种存储后端（本地文件、RDMA、对象存储）
- `NixlRegistry` 管理已注册的存储对象

**SIMM**（`hicache_simm.py`）：
- 模拟存储后端，用于测试
- 延迟/带宽可配置
- 验证 HiCache 逻辑的正确性

## 8. Disaggregation 架构

### 8.1 Prefill node

**`SchedulerDisaggregationPrefillMixin`**（`prefill.py`）：

- 接收请求 → Bootstrap Queue → Waiting Queue → Prefill → Transfer to Decode node
- `PrefillBootstrapQueue`：初始化 KV transfer sender
- Prefill 计算完成后，KV cache 通过 transfer backend 发送到 Decode node
- 不保留 KV cache（请求完成后释放）

### 8.2 Decode node

**`SchedulerDisaggregationDecodeMixin`**（`decode.py`）：
- 接收从 Prefill node 传输的 KV cache
- `DecodePreallocQueue`：预分配请求 slot
- `DecodeTransferQueue`：管理 KV transfer 接收
- 可选启用 radix cache（`--disaggregation-decode-enable-radix-cache`）

**DecodeHiCachePreallocMixin**（`decode_hicache_mixin.py:58-97`）：
- `_build_decode_prefix_match`：构建三层命中信息
  - L1：GPU 直接命中
  - L2：CPU host_value 命中
  - L3：Storage 命中（`query_storage_hit_length`）
- `_start_hicache_prefetch`：启动 storage → host 预取

### 8.3 KV cache 传输

- 通过 `CommonKVManager`（`disaggregation/common/conn.py`）管理
- 支持 NCCL / MOFEDED / Mooncake 等传输后端
- Transfer 过程：sender 注册 buffer → receiver 拉取数据 → 确认完成
- DecodeKVCacheOffloadManager（`decode_kvcache_offload_manager.py`）：可选的 decode 端 KV offload

## 9. Agent 场景差距分析

### 9.1 当前不足

1. **无 Agent Group 概念**：
   - Session 机制是 1:1（一个 session 对应一个对话流）
   - Agent 场景中多个 LLM 调用（planner、coder、reviewer）属于同一任务但使用不同 session
   - 无法按任务组共享/保护 KV cache

2. **无 Agent-Aware 调度**：
   - 调度策略（LPM/DFS/FCFS）不感知 agent 工作流
   - Agent 的多轮调用可能被分散调度，无法保证同组请求的 cache 局部性
   - 无 "agent batch" 概念，无法将同一 agent 的多个子请求批处理

3. **KV cache 保护不足**：
   - `lock_ref` 由单个请求持有，请求结束后释放
   - Agent 场景中，多轮调用之间需要保持 KV cache，但当前 radix cache 的 LRU 驱逐可能在不相关请求的压力下驱逐 agent 的 prefix
   - StreamingSession 可以保持 KV，但只支持单 session 内的 append-only 模式

4. **跨 session KV 共享缺失**：
   - Agent 的多个角色（planner/coder/reviewer）可能共享 system prompt
   - 当前 radix cache 通过 prefix match 隐式共享，但无显式保护
   - 任何角色的新请求都可能导致驱逐其他角色的 prefix

5. **无 Agent-Aware 驱逐**：
   - 驱逐策略（LRU/优先级）不考虑 agent 任务结构
   - 一个长任务的中间 KV 可能被短任务挤出
   - 无 "任务完成前不驱逐" 的语义保证

6. **批量推理效率问题**：
   - Agent 通常同时发起多个结构化请求（如并行工具调用）
   - 当前调度器逐个处理，无法利用 in-batch prefix caching 的最大潜力
   - 无 agent-pattern 感知的前瞻调度

### 9.2 扩展改动点

1. **AgentGroup 抽象**（新增模块）：
   - 文件：`python/sglang/srt/agent/agent_group.py`（新建）
   - 职责：管理同一 agent 任务的所有 session/KV cache
   - 提供组级 lock_ref、组级驱逐策略、组级预算

2. **调度器扩展**（修改 `schedule_policy.py`）：
   - 新增 `AGENT_GROUP` 策略
   - `_compute_prefix_matches` 增加组感知排序
   - 同组请求优先连续调度（类似 DFS-weight 但基于 agent group）
   - 改动量：约 200 行

3. **RadixCache 扩展**（修改 `radix_cache.py`、`unified_radix_cache.py`）：
   - `TreeNode` 增加 `group_id` 字段
   - `evict` 方法增加组感知驱逐：同组 KV 最后驱逐
   - `inc_lock_ref` / `dec_lock_ref` 支持组级引用
   - 改动量：约 300 行

4. **SessionController 扩展**（修改 `session_controller.py`）：
   - `Session` 增加 `group_id` 字段
   - `SessionController` 增加 `group_sessions` 索引
   - 组关闭时批量释放所有 session 的 KV
   - 改动量：约 100 行

5. **HiCache 集成**（修改 `hiradix_cache.py`）：
   - Storage backend 键增加 `group_id` 命名空间
   - 组级 prefetch 策略：预取同组常用 prefix
   - 改动量：约 150 行

### 9.3 改动量评估

| 模块 | 改动类型 | 改动量 | 复杂度 |
|------|----------|--------|--------|
| AgentGroup 抽象 | 新增 | ~300 行 | 中 |
| schedule_policy.py | 修改 | ~200 行 | 中 |
| radix_cache.py | 修改 | ~300 行 | 高 |
| unified_radix_cache.py | 修改 | ~200 行 | 高 |
| session_controller.py | 修改 | ~100 行 | 低 |
| hiradix_cache.py | 修改 | ~150 行 | 中 |
| API 层（io_struct.py） | 修改 | ~50 行 | 低 |
| 测试 | 新增 | ~500 行 | 中 |
| **总计** | | **~1800 行** | |

核心挑战：
- 引用计数从单请求语义扩展到组语义，需保证正确性
- 组感知驱逐需平衡公平性和效率
- 多组件（Full/SWA/Mamba）的组感知驱逐级联逻辑复杂
- Disaggregation 模式下的组感知 KV 传输需额外设计

## 10. 关键源码文件索引

| 文件 | 关键类/函数 | 作用 |
|------|------------|------|
| `mem_cache/radix_cache.py` | `RadixCache`, `TreeNode`, `RadixKey` | Radix Tree 核心实现 |
| `mem_cache/base_prefix_cache.py` | `BasePrefixCache`, `MatchResult`, `EvictParams` | Prefix cache 抽象基类 |
| `mem_cache/common.py` | `alloc_for_extend`, `alloc_for_decode`, `release_kv_cache` | KV cache 分配/释放工具函数 |
| `mem_cache/hiradix_cache.py` | `HiRadixCache` | 层级 Radix Cache（GPU+CPU+Storage） |
| `mem_cache/unified_radix_cache.py` | `UnifiedRadixCache`, `UnifiedTreeNode` | 统一多组件缓存 |
| `mem_cache/hicache_storage.py` | `HiCacheStorage`, `HiCacheFile`, `PoolTransfer` | 存储后端抽象和文件实现 |
| `mem_cache/chunk_cache.py` | `ChunkCache` | 禁用 radix cache 时的简单缓存 |
| `mem_cache/mamba_radix_cache.py` | `MambaRadixCache`, `TreeNode` | Mamba 模型的混合缓存 |
| `mem_cache/memory_pool.py` | `ReqToTokenPool`, `MHATokenToKVPool`, `MLATokenToKVPool` | 内存池管理 |
| `mem_cache/events.py` | `KVCacheEventMixin` | KV cache 事件发射 |
| `mem_cache/storage/lmcache/lmc_radix_cache.py` | `LMCacheRadixCache` | LMCache 集成 |
| `mem_cache/storage/nixl/hicache_nixl.py` | `HiCacheNixl` | NIXL 存储后端 |
| `managers/scheduler.py` | `Scheduler` | 主调度器 |
| `managers/schedule_policy.py` | `SchedulePolicy`, `PrefillAdder`, `match_prefix_for_req` | 调度策略和 prefill 预算管理 |
| `managers/cache_controller.py` | `HiCacheController`, `LayerDoneCounter` | HiCache 控制器（DMA 传输） |
| `session/session_controller.py` | `SessionController`, `Session` | Session 生命周期管理 |
| `session/streaming_session.py` | `StreamingSession`, `SessionSlot` | 流式 session KV 持久化 |
| `disaggregation/prefill.py` | `PrefillBootstrapQueue` | Prefill 端 disaggregation |
| `disaggregation/decode_hicache_mixin.py` | `DecodeHiCachePreallocMixin` | Decode 端 HiCache 集成 |
| `managers/scheduler_components/kv_events_publisher.py` | `SchedulerKvEventsPublisher` | KV 事件发布 |

## 11. 未确认问题

1. **`HybridCacheController`** 的完整实现未详细阅读（`hybrid_cache/hybrid_cache_controller.py`），其对 DSA 模型的特殊处理逻辑待确认。

2. **`SIMM` 存储后端**（`hicache_simm.py`）未详细阅读，其对延迟/带宽的模拟机制待确认。

3. **`ComponentData`** 和各 `TreeComponent` 子类（`FullComponent`、`SWAComponent`、`MambaComponent`）的具体实现在 `unified_cache_components/` 目录下，未详细阅读其 `create_match_validator`、`evict_component`、`commit_hicache_transfer` 等关键方法。

4. **Speculative decoding**（EAGLE）下的 bigram key 模式和 KV cache 管理逻辑未深入分析。

5. **`SWATokenToKVPoolAllocator`** 的滑动窗口注意力与 KV cache 交互逻辑未详细确认。

6. **`DeepSeekV4TokenToKVPool`** 和 DSA（DeepSeek Attention）的特殊内存管理逻辑未详细确认。

7. **`Req.init_next_round_input`** 的具体实现（在 `schedule_batch.py` 中）未完整阅读，其对 retract 后 prefix 恢复的逻辑待确认。

8. **跨 TP rank 的 radix tree 一致性保证**：代码中有大量 `_all_reduce` / `_barrier` 调用，但具体的一致性模型和边界条件未完全确认。

9. **`PrefetchOperation`** 的完整生命周期管理（在 `cache_controller.py` 和 `hybrid_cache_controller.py` 中）未详细追踪。
