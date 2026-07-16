# vLLM KV Cache 管理 PPT 文案（逐页）

> 日期: 2026-06-30（源码核对: 2026-06-26）
> 范围: vLLM v1 block-hash 架构 + OffloadingConnector CPU/SSD tier；**主线 = FullAttention、无 SWA**（Mamba/hybrid/SWA 路径见脚注，不展开）
> 依据: 全部结论经源码确认（file:line 见每页脚注），非记忆
> 路径: 相对 `Engine/vllm/vllm/`；offloading 调度层 = `distributed/kv_transfer/kv_connector/v1/offloading/scheduler.py`
> 结构: 按 `docs/27_ppt_plan_kv_cache_lifecycle.md` 的"一个 block 的一生"主线
> 用法: 每页给【画什么】【写什么】【数字/证据】三栏，先画图后填字

---

## 第 0 页：标题页

【写什么】

- 标题：vLLM 的 KV Cache 是怎么管理的——一个 block 的一生
- 副标题：从注册到消亡，看现有 cache 管理在 Agent 场景下的盲点

【画什么】

- 一条横向时间轴占位（注册→查找→跨层→驱逐→生命周期），后续每页展开一环

---

## 第一部分：心智模型——cache 管理"管什么"（含时机）

> 第 1 页用 **T0~T8 时机轴** 串起全流程；第 2 页起补数据结构与部署参数。



### 第 1 页：KV cache 在 serving 里的位置（架构 + 时机）

> 这页是全 PPT 的地图。**左半：按时间顺序**——一个请求从进来到结束，每个决策点发生在**哪一时刻**（schedule 步 / forward 步 / 请求结束）。**右半：三级存储与两套索引**——各层数据存在哪、谁查谁写。  
> 四个必须讲对的前提：**两套索引、两次查找、GPU 注册≠CPU store、store≠swap**。

【画什么】一张图，**上：时机轴（横轴 = 时间）**，**下：存储与索引（结构）**。

```
═══════════════════════════════════════════════════════════════════════════════
Engine step 骨架（一个 step = schedule → execute → update）  engine/core.py:443-470
═══════════════════════════════════════════════════════════════════════════════
  schedule()          execute_model()         update_from_output()
  T0~T2, T4, T7       T3 forward + T5 DMA     T6 complete_store（worker 回调）

═══════════════════════════════════════════════════════════════════════════════
上：时机轴 —— 从 Server 启动到第一个请求（标注 T0~T8，讲 PPT 时用手指沿轴走）
═══════════════════════════════════════════════════════════════════════════════

T0  Server 启动
    │  BlockPool 初始化：N 个 GPU 物理块 + free queue
    │  cached_block_hash_to_block = {}     ← GPU 注册表空
    │  （若开 offload）CPU _policy = {}，SSD 目录空
    ▼
T1  HTTP 请求到达 → 构造 Request
    │  update_block_hashes()               ← 只算 hash 链 [H0,H1,...]，**还不注册**
    ▼
T2  Scheduler.schedule() — 本 engine step，处理 waiting 请求（CPU，同步）
    │
    ├─ T2a 【查找·第一段】GPU prefix cache     scheduler.py:660
    │      get_computed_blocks → find_longest_cache_hit → get_cached_block
    │      命中 → touch(ref_cnt+1)；miss → 继续
    │      ⚠️ GPU miss **不会**自动查 CPU，本段到此结束
    │
    ├─ T2b 【查找·第二段】CPU/SSD（仅配 connector） scheduler.py:672
    │      connector.get_num_new_matched_tokens → _lookup → manager.lookup
    │      有外部命中 → load_kv_async=True → **本 step 该请求不 forward**（WAITING_FOR_REMOTE_KVS）
    │      ext_tokens=None（SSD promotion / in-flight defer）→ **本 step 跳过请求**
    │      → 得到 num_computed_tokens
    │
    ├─ T2c 【分配 + GPU 注册】                  scheduler.py:819
    │      allocate_slots → cache_full_blocks
    │      为「未命中」的满 block：hash → block_id 写入 GPU dict
    │      ⚠️ **发生在 execute_model 之前**——此时 KV 内容还是空的，只建了索引
    │      ⚠️ **只写 GPU dict**，不写 CPU/SSD
    │      prefix 几乎全命中时仍常 schedule ≥1 tok（重算末 token 拿 logits，kv_cache_manager.py:221-227）
    ▼
T3  execute_model() — Worker forward（**同一 engine step**）  gpu_model_runner
    │  Prefill/Decode：把 KV **写入** T2c 已分配/命中的 physical block
    │  Running decode：**不再** T2a lookup；每 step allocate_slots → 满 block 在 forward 前注册
    ▼
T4  schedule() 末尾 — _build_store_jobs → prepare_store  scheduler.py:1014
    │  CPU _policy.insert(OffloadKey)，BlockStatus ref_cnt=-1（**is_ready=False，占位**）
    │  构造 store_spec，排 GPU→CPU 传输任务
    │  ⚠️ 不是「GPU 满了才搬」；与 T2a/T2c/T7 **无联动**
    ▼
T5  execute_model() — Worker 异步 DMA（**与 T3 同一步**）
    │  GPU → CPU（pinned memory /dev/shm），KV 数据物理写入
    ▼
T6  update_from_output() — complete_store（worker completed_jobs 回调）
    │  CPU：ref_cnt→0 → is_ready=True（可读）；cascade → 异步写 SSD .bin
    │  ⚠️ insert 在 T4，就绪 + cascade 在 T6——两层「进表」时刻不同
    ▼
T7  后续任意 schedule() 的 allocate_slots
    │  get_new_blocks → _maybe_evict_cached_block
    │  从 free queue 头取 ref_cnt=0 的块 → **删 GPU hash 映射**（不是 swap）
    │  ⚠️ **不调 connector**，不保证已 store；物理块随后被新 KV 覆盖
    │
    ├─ T7' **Running** 请求 allocate 失败 → preempt  scheduler.py:472-514
    │      free 低优先级 **running** 请求 → 腾 GPU **物理块**
    │      ⚠️ **Waiting** 请求 allocate 失败 → break，**不 preempt**（scheduler.py:833-840）
    │      ⚠️ v1 默认 **不** swap 到 CPU，直接 free
    ▼
T8  请求结束 → kv_cache_manager.free()
       ref_cnt→0，block 进 free queue 尾部
       GPU hash **仍保留** → 下一请求 T2a 还能命中（直到 T7 驱逐）

───────────────────────────────────────────────────────────────────────────────
同批并发 Turn0（Agent P1）在时机轴上的位置 —— 解释「为何 cached 相同」
───────────────────────────────────────────────────────────────────────────────
  请求 A/B/C 几乎同时进 T2：
    T2a 时大家查同一张 GPU 表 → 只能命中 **T0 之后已在表里的** 公共 prefix（如 7824）
    T2c 各自 register **本 session 特有** L1 → hash 不同，**不能互蹭**
  ⚠️ 串行 vs 并发：**T2a 的 cached 数量可相同**；差别在 TTFT/排队，不在「串行 magically 多注册」

═══════════════════════════════════════════════════════════════════════════════
下：三级存储与两套索引与两套索引（结构图，与时机轴对照）
═══════════════════════════════════════════════════════════════════════════════

  时机        GPU 层                    CPU primary              SSD (fs)
  ─────────────────────────────────────────────────────────────────────────
  T2a 查     cached_block_hash_to_block  _policy (OrderedDict)   os.path.exists
  T2c 写     ✅ insert hash→block        —                       —
  T4 占位    —                           ✅ insert（未就绪）      —
  T5 写数据  （KV 仍在 GPU）              ✅ DMA 写入 physical    —
  T6 就绪    —                           ✅ is_ready + cascade   ✅ .bin 文件
  T7 驱逐    ❌ pop hash，块复用          ❌ LRU evict（独立*）     ❌ 无统一 LRU*
  * CPU evict 可在 T4 prepare_store 时触发，与 GPU T7 无关

  GPU HBM ◄──DMA──► CPU /dev/shm ◄──I/O──► /mnt/kv_cache/...

  * fs tier 默认无容量淘汰，靠磁盘空间；obj/example 见第 2 页

  ⚠️ 不是 OS swap：GPU 满 ≠ 自动 LRU 搬到 CPU
  ⚠️ store = 「算完备份一份」；evict = 「删 GPU 索引、复用物理块」——两条线
```

**时机速查表（口播用，可单独做 slide 小表）：**


| 时刻  | 发生什么           | GPU dict      | CPU tier                   | KV 内容         |
| --- | -------------- | ------------- | -------------------------- | ------------- |
| T1  | 算 block_hashes | —             | —                          | —             |
| T2a | GPU lookup     | 读             | —                          | 旧请求留下的        |
| T2b | CPU/SSD lookup | —             | 读                          | —             |
| T2c | **GPU 注册**     | **写 hash→id** | —                          | **尚未写入**      |
| T3  | forward        | —             | —                          | **写入 GPU**    |
| T4  | CPU 占位 insert  | 仍在            | insert（未就绪）                | GPU 有         |
| T5  | worker DMA     | 仍在            | **数据写入**                   | GPU 有 + CPU 有 |
| T6  | complete_store | 仍在            | **is_ready** + SSD cascade | 同上            |
| T7  | GPU 驱逐         | **删 hash**    | 独立 LRU 可能 evict            | 块将被覆盖         |
| T8  | 请求结束           | hash 保留       | copy 保留                    | ref_cnt=0     |


**找到之后怎么用（命中层 → 该请求本 step 是否 forward）：**


| 命中层                             | 发生在     | 后续                                     | 本 step forward？        |
| ------------------------------- | ------- | -------------------------------------- | ---------------------- |
| GPU dict                        | T2a     | touch + 少算 prefill                     | **是**（若 allocate 成功）   |
| CPU/SSD 有额外命中                   | T2b     | load_kv_async → WAITING_FOR_REMOTE_KVS | **否**（下 step load 完再排） |
| SSD promotion / in-flight defer | T2b     | ext_tokens=None → skipped queue        | **否**                  |
| 全 miss                          | T2a/T2b | T2c prefill + 注册                       | **是**                  |


【写什么】

- **管什么** = 在 T2/T3~T6/T7/T8 做决策：查、GPU 注册、算 KV、CPU 备份、驱逐、释放
- **一个 engine step** = `schedule()`（T2/T4/T7）→ `execute_model()`（T3/T5）→ `update_from_output()`（T6）
- **和「swap 直觉」的区别**（口播 20 秒）：offload 是 T4~T6「算完就备份」，不是 T7「GPU 满了才搬」；T7 只删 GPU 索引，**不保证** CPU 还有 copy（P6 load=0 根因）
- **GPU vs CPU「进表」**：GPU hash→id 在 **T2c**（forward 前）；CPU `_policy.insert` 在 **T4**，`is_ready=True` 在 **T6**
- **两次查找**：T2a 与 T2b 是 scheduler **两次独立调用**，非 GPU miss 自动 fall-through
- **Preempt 仅 running**：waiting 队列 allocate 失败只 break，不抢 running 请求
- **请求视角 vs block 视角**：本页是**单次请求时间线**；第二部分第 3 页是 **block 跨请求** 的生命周期（顺序相反，勿混）

> 跨机 KV connector（NIXL/Mooncake 等）是**另一套机制**，与本页 T2b/T5-T6 的本机 tier 独立，不展开。

【数字/证据】

- engine step 三段：`v1/engine/core.py:443-470`
- 时机 T1 hash 预计算：`v1/request.py:175-180,233-236`
- T2a GPU 查找：`v1/core/sched/scheduler.py:660-662` → `kv_cache_manager.py:202` → `block_pool.py:184`
- T2b CPU 查找 + defer：`scheduler.py:672-686,732-735,863-883` → `distributed/kv_transfer/kv_connector/v1/offloading/scheduler.py:545,579,395` → `tiering/manager.py:228`
- T2c GPU 注册（forward 前）：`scheduler.py:819` → `kv_cache_manager.py:444-456,221-227` → `block_pool.py:211,281`
- T3/T5 worker：`execute_model()` 与 schedule 同 step
- T4 CPU insert 占位：`offloading/scheduler.py:729-902` → `kv_offload/cpu/manager.py:202-203`（`BlockStatus` ref_cnt=-1，`policies/base.py:24-33`）
- T6 就绪 + cascade：`offloading/scheduler.py:996-1013` → `cpu/manager.py:224-228` → `tiering/manager.py:480-534`
- T7 GPU 驱逐：`block_pool.py:352,365`（无 connector 调用）
- T7' preempt（仅 running）：`scheduler.py:472-514`；waiting break：`scheduler.py:833-840`
- T8 free 保留 hash：`block_pool.py:419-441`
- offload 设计语义「extend prefix cache as produced」：`docs/features/kv_offloading_usage.md:3`
- ⚠️ `cpu_offload_gb` = 模型权重 UVA，与 KV tier 无关

---



### 第 2 页：vLLM 的 KV cache 长什么样（数据结构）

【画什么】

```
GPU 层：
  cached_block_hash_to_block : dict[hash → KVCacheBlock]   ← prefix index
  free_block_queue           : LRU 队列（ref_cnt=0 的块）   ← 驱逐候选池
  KVCacheBlock 字段: {block_id, ref_cnt, _block_hash, 链表指针}
                     ⚠️ 没有任何 value/priority/protected 字段

CPU 层（primary tier，CPUPrimaryTierOffloadingManager）：
  CachePolicy._store : OrderedDict[OffloadKey → BlockStatus]  ← 独立 LRU/ARC
  BlockStatus 字段: {ref_cnt, block_id}   ⚠️ 同样无价值字段；ref_cnt=-1 表示 store 未就绪
  prepare_store 时 protected=set(keys)：本批待写 key 不参与 CPU evict（cpu/manager.py:177-181）
  cascade 期间 prepare_read 临时 ref_cnt+1 防 CPU evict（tiering/manager.py:514-516）
  物理: /dev/shm mmap (DRAM, 跨 worker 共享)

secondary 层（平级 alternative，物理位置不同，本地部署默认用 fs）：
  fs  (FileSystemTierManager):     本机磁盘 .bin 文件，O_DIRECT I/O   ← 本 PPT 主线
  obj (ObjectStoreSecondaryTierManager): 远程 S3 对象存储 (NIXL OBJ backend, HTTP/TCP)  ← 只标注
  example (ExampleSecondaryTierManager): 进程内 dict, 只记存在性不搬数据 (测试用)  ← 只标注
  fs 的 index = os.path.exists，⚠️ 无任何容量淘汰/LRU，假设磁盘无限

  ⚠️ 三层各有独立 index（GPU dict / CPU OrderedDict / fs 文件名）
     无 HiCache 式统一树，由 TieringOffloadingManager 显式 cascade/promotion 协调
  ⚠️ secondary 可同时配多个（list）；store 时对所有 secondary 各写一份，load 时命中第一个即停
  ⚠️ fs 跨机需挂共享存储 + 固定 PYTHONHASHSEED（源码本身无网络层）

  另有跨机 KV connector 体系（factory 注册 14 个，NIXL/Mooncake 等），独立于本机三级，不展开
```

【写什么】

- 三个关键事实，每个都为后面埋伏笔：
  1. **GPU block 没有价值字段**——只有 ref_cnt 和 LRU 顺序（伏笔：第 7 页"判据缺失"）
  2. **三层各有一个独立 index**——GPU dict、CPU OrderedDict、fs 文件名，不是一个统一结构；**无 HiCache 式统一树**（伏笔：第 5 页"跨层"）
  3. **SSD 层连淘汰都没有**——比 GPU/CPU 更彻底（伏笔：第 5、7 页）
- GPU 和 CPU 共用同一条 block hash 链作为 key（`make_offload_key` 派生自 `req.block_hashes`），但两个 dict 各自维护、各自淘汰
- **secondary 三种 backend 物理位置不同**：fs=本机磁盘、obj=远程 S3 对象存储、example=进程内测试 stub。不是都本机。本地部署主线只讲 fs
- 点一句但不展开：secondary 可同时配多个（写时全写、读时取第一个）；另有跨机 connector 体系独立存在

【数字/证据】

- GPU block 字段无 value：`vllm/v1/core/kv_cache_utils.py:116-162`
- CPU BlockStatus 仅 ref_cnt+block_id：`vllm/v1/kv_offload/cpu/policies/base.py:10-33`
- CPU 物理 mmap：`vllm/v1/kv_offload/cpu/shared_offload_region.py:56`
- secondary 三种 backend：`vllm/v1/kv_offload/tiering/factory.py:55-71`
  - fs 本机磁盘 O_DIRECT：`tiering/fs/io.py:11-12,32-72,75-102`
  - obj 远程 S3（NIXL OBJ backend，HTTP/TCP 非 RDMA）：`tiering/obj/manager.py:84-89,101-105`，`tiering/obj/config.py:8-17`
  - example 进程内 dict（测试）：`tiering/example/manager.py:3-10,63-64`
- fs 无淘汰、靠 exists 去重：`vllm/v1/kv_offload/tiering/fs/io.py:42-43`
- fs 跨机需共享存储+固定 PYTHONHASHSEED：`tiering/fs/manager.py:73-81`
- 多 secondary 可同配、store 全写：`tiering/manager.py:517-534`；load 取第一个：`manager.py:258-265`
- 无统一树（grep host_value/HiCache 零命中）：`vllm/v1/` 全仓
- 两层共享 hash 链：`v1/kv_offload/base.py:36-38`，`distributed/kv_transfer/kv_connector/v1/offloading/scheduler.py:214-228`
- 跨机 connector 14 个：`distributed/kv_transfer/kv_connector/factory.py:152-230`

---



### 第 2.1 页：怎么部署开启 offload（服务器参数）

> 这一页讲"怎么启动 vLLM 开启这些 tier"，纯部署参数，理解机制时可跳过。

【画什么】

入口：`--kv-transfer-config`（内联 JSON），或简式 `--kv-offloading-size <GiB>`（仅单层 CPU）。所有 tier 参数嵌在 `kv_connector_extra_config` 里。

```
# 单层 CPU（最简）
vllm serve <model> --kv-offloading-size 10 --kv-offloading-backend native
#  (10 GiB CPU offload，内部转 cpu_bytes_to_use bytes)

# 三级 CPU+fs（主线场景）
vllm serve <model> --kv-transfer-config '{
  "kv_connector": "OffloadingConnector",
  "kv_role": "kv_both",
  "kv_connector_extra_config": {
    "spec_name": "TieringOffloadingSpec",   # 多层必须，默认 CPUOffloadingSpec 是单层
    "cpu_bytes_to_use": 10737418240,         # bytes（必填），TP>1 为所有 rank 之和
    "eviction_policy": "lru",                # lru(默认) | arc
    "offload_prompt_only": true,             # 默认 true，decode block 不 store
    "secondary_tiers": [
      { "type": "fs", "root_dir": "/mnt/kv_cache", "n_read_threads": 16, "n_write_threads": 16 }
    ]
  }}'
```

各 tier 参数表：


| 层           | 参数                                   | 默认                  | 说明                                                                                  |
| ----------- | ------------------------------------ | ------------------- | ----------------------------------------------------------------------------------- |
| CPU primary | `cpu_bytes_to_use`                   | —（必填，bytes）         | CPU tier 容量，所有 worker 总和                                                            |
| CPU primary | `eviction_policy`                    | `lru`               | `lru` / `arc`                                                                       |
| CPU primary | `offload_prompt_only`                | `true`              | true=只 store prefill block，跳 decode                                                 |
| CPU primary | `store_threshold`                    | `0`                 | block 被 store 前最少 lookup 次数（TieringSpec 不支持 ≥2）                                     |
| 选中 spec     | `spec_name`                          | `CPUOffloadingSpec` | 单层=CPUOffloadingSpec；多层=TieringOffloadingSpec                                       |
| fs          | `root_dir`                           | —（必填）               | 本机磁盘基目录；跨机共享需挂共享PVC+`PYTHONHASHSEED=0`                                              |
| fs          | `n_read_threads` / `n_write_threads` | `16` / `16`         | I/O 线程数                                                                             |
| obj         | `store_config`                       | —（必填 dict）          | `bucket`/`endpoint_override`/`access_key`/`secret_key`/`scheme`(默认http)/`ca_bundle` |
| obj         | `io_threads`                         | `4`                 | NIXL OBJ backend 线程数                                                                |
| obj         | `prefix`                             | `""`                | 对象 key 前缀                                                                           |


【写什么】

- 两个入口：简式 CLI（仅单层 CPU）和完整 `--kv-transfer-config` JSON（多层）
- 重点参数：`cpu_bytes_to_use`（**单位是 bytes 不是 GiB**，简式 CLI 才用 GiB）、`spec_name`（选单层/多层）、`secondary_tiers`（list，配 fs/obj）
- ⚠️ 易混：`--cpu-offload-gb` 是**模型权重** UVA offload，与 KV cache offload 完全无关
- 官方文档：`docs/features/kv_offloading_usage.md`（覆盖 CPU+fs，未覆盖 obj；obj 参数见源码 `tiering/obj/config.py:8-17`）

【数字/证据】

- 部署入口 CLI：`engine/arg_utils.py:1166-1171`（`--kv-offloading-size`/`--kv-offloading-backend`）、`:1477`（`--kv-transfer-config` 内联 JSON）
- CPU 参数：`kv_offload/cpu/spec.py:49-53,90,103`（cpu_bytes_to_use 必填、eviction_policy、store_threshold）、`kv_offload/base.py:431-433`（offload_prompt_only）
- spec 选择：`kv_offload/factory.py:37,57-58,66-73`（CPUOffloadingSpec 默认 / TieringOffloadingSpec 多层）
- fs 参数：`tiering/fs/manager.py:88-90`（root_dir 必填、n_read/write_threads 默认16）
- obj 参数：`tiering/obj/config.py:8-17`（ObjStoreConfig 字段）、`tiering/obj/manager.py:91-99`（store_config/prefix/io_threads）
- 官方文档：`docs/features/kv_offloading_usage.md`

---



### 第 2.2 页：offload 机制的类层次（三层，理解第 6 页跨层路径时回来对照）

【画什么】

```
vLLM Scheduler
   │ 调用 connector 接口
   ▼
OffloadingConnector                    [接口层] offloading_connector.py:46
   │ 继承 KVConnectorBase_V1；只按 role 转发，不含业务逻辑
   │ 字段: connector_scheduler, connector_worker
   ▼
OffloadingConnectorScheduler           [调度层] offloading/scheduler.py:263
   │ 持有 self.manager = spec.get_manager()  (:271)
   │ 决定何时 store/lookup/load，把 request 拆成 block 级 job，跟踪 job 生命周期
   │ 例: get_num_new_matched_tokens (:545) → _lookup (:395) → manager.lookup
   ▼
TieringOffloadingManager               [存储实现层] tiering/manager.py:111
   │ 字段: primary_tier (CPUPrimaryTierOffloadingManager, :142)
   │       secondary_tiers: list[SecondaryTierManager] (:143)
   │ 实现 cascade(store: primary→所有secondary) / promotion(load: secondary→primary→GPU)
   │ 关键方法: lookup(:227) / complete_store(:480) / _initiate_promotion(:271)
   ├──▶ CPU primary tier  (manager.py:62)
   └──▶ secondary tier 列表 (fs/obj/example)
```

【写什么】

- offload 机制不是单一类，是**三层类层次**：接口层 → 调度层 → 存储实现层
- `OffloadingConnector`**（接口）→** `OffloadingConnectorScheduler`**（调度，持有 manager）→** `TieringOffloadingManager`**（存储）**。connector 不直接持有 manager，中间隔了 scheduler
- 各层职责：
  - 接口层：挂在 scheduler/worker 上，只按 role 转发，不含逻辑
  - 调度层：决定何时 store/lookup/load，把 request 拆成 block 级 job
  - 存储层：持有 CPU primary + secondary 列表，实现 cascade/promotion
- manager 类型由 spec 选：默认 `CPUOffloadingSpec`（单层，无 secondary），配 `TieringOffloadingSpec` 才有多层。本 PPT 讲的多级都是 `TieringOffloadingSpec` 配置下

【数字/证据】

- 接口层：`distributed/kv_transfer/kv_connector/v1/offloading_connector.py:46`
- 调度层：`distributed/kv_transfer/kv_connector/v1/offloading/scheduler.py:263`（类）、`:271`（持有 manager）、`:545,579,395`（lookup/load defer）
- 存储层：`v1/kv_offload/tiering/manager.py:111`（类）、`:142,143`、`:227,480,271`
- spec 选 manager：`v1/kv_offload/factory.py:66-73`

---



### 第 2.5 页：hash 链——vLLM prefix cache 的核心机制

> 这页是理解后面注册（④）、查找（⑤）、并发（P1）三页的前提，单独提前讲清楚。

【画什么】

```
prompt 按 16 token 切 block，每个 block 的 hash 依赖上一个 block：

  block0: hash = hash(NONE_HASH,    token[0:16])     = h0
  block1: hash = hash(h0,           token[16:32])    = h1   ← 把 h0 折叠进去了
  block2: hash = hash(h1,           token[32:48])    = h2   ← 把 h1 折叠进去了
  block3: hash = hash(h2,           token[48:64])    = h3
  ...

  → 每个 block 的 hash 隐含了它前面所有 block 的内容
  → block3 的 hash 不只代表 token[48:64]，而是代表"从头到第64token的完整前缀"
```

再画一个"两 session 发散"的图：

```
session A: [L0][L1_shared][L1_unique_A][...]
           h0 → h1 → h2_A → h3_A → ...   (h0,h1 与 B 相同)
                              ↑
session B: [L0][L1_shared][L1_unique_B][...]   ← L1_unique 不同，hash 从此分叉
           h0 → h1 → h2_B → h3_B → ...
```

【写什么】

**什么是 hash 链**：vLLM 把 prompt 按 16 token 一块切，每个 block 的 hash **不是独立算的，而是依赖上一个 block 的 hash**：

```
block_N 的 hash = hash( block_{N-1} 的 hash, block_N 的 token )
```

每个 block 的 hash 像链条一样扣住前一个——一环扣一环，所以叫"链式 hash"。

**为什么这么设计**：prefix cache 的本质是"前缀匹配"。链式 hash 让"两个请求的前面 N 个 token 完全一样"这件事，可以用"第 N 个 block 的 hash 相同"直接表示——不用逐 token 比对，一次 dict 查找就判定。所以 `cached_block_hash_to_block` 这个 dict 的 key = block hash，查 prefix 命中 = 沿着 hash 链逐个查 hash 在不在 dict。

**链式 hash 带来三个关键性质**（后面三页都用到）：

1. **遇第一个 miss 就停**——查 prefix 时从 block 0 逐个查，block 2 miss 就 break。因为链式：block 3 的 hash = `hash(block2的hash, ...)`，block 2 不在 dict（前缀没缓存）→ block 3 的 hash 也必然不在（父链断了后面全断）。源码注释明说："following block hashes are not computed yet for sure"。（→ 第 5 页查找）
2. **内容发散点后全 miss**——看上图两 session：block 0、1（L0+L1_shared）相同 → h0、h1 相同 → 能命中；block 2 起是 L1_unique（各自的 issue/代码），内容不同 → h2_A ≠ h2_B → **从发散点开始后面整条链的 hash 全不一样**。session B 查到 block 2 就 miss break，L1_unique 之后全断。不是单个 block 没缓存，是发散点之后整条链都断了。（→ P1 的机制根因，L1_unique 无法跨 session 复用）
3. **hash 算得早、GPU 注册得早、KV 填得晚**——block hash 在 Request `__init__` 时就算好（T1）；**GPU dict 注册**在 `allocate_slots`→`cache_full_blocks`（T2c，**forward 之前**）；**KV 内容**在 Worker forward（T3）才写入。并发时 B 在 T2a 查表时，A 可能尚未 T2c 注册 → 同批互不可见。（→ 第 4 页注册、P1）

**一句话**：hash 链 = 每个 block 的 hash 把前面所有内容折叠进去，查 prefix = 沿链逐个查 dict，一旦内容发散（hash 不同），后面整条链必然全断，直接停。好处是查 prefix 极快（dict O(1)），坏处是**对内容发散极度敏感**——agent 不同 session 的 L1_unique 一旦不同，发散点之后所有复用都断，不管后面有没有共同内容。

【数字/证据】

- 链式 hash 定义：`vllm/v1/core/kv_cache_utils.py:563-590`（`hash_block_tokens`，`:584` 用 `parent_block_hash`，`:588-590` 传入）
- 逐块算链：`kv_cache_utils.py:667-708`（`request_block_hasher`，`:683-685` 上一块 hash 作下一块输入）
- 遇 miss 即停 + 注释：`single_type_kv_cache_manager.py:548-558`（注释 :549-551）
- block size=16：`vllm/config/cache.py:46`（`DEFAULT_BLOCK_SIZE=16`）

---



## 第二部分：一个 block 的一生（主体）



### 第 3 页：时间轴总览

【画什么】横向时间轴，五环排开，每环下面挂"现状 / agent 问题"两行：

```
一个 KV block 的生命周期
─────────────────────────────────────────────────────────────────────►
   ①注册      ②查找      ③跨层      ④驱逐      ⑤生命周期
   (出生)    (被使用)   (备份)    (被动死亡)  (真死亡·缺失)
     │          │          │          │          │
  T2c 写     T2a/T2b   T4-T6     T7 删hash   T8 free
  GPU dict   查 prefix  store     复用块     ref_cnt=0
  (forward前) (新请求)  备份CPU/SSD (任意alloc) (session结束)
     │          │          │          │          │
  索引先于KV  hash链式   store≠swap  纯LRU无    无显式生命周期
  内容T3填   遇miss即停  与驱逐不联动 价值判据    垃圾滞留(待测)
```

【写什么】

- 这页是后续 5 页的目录。强调两句：
  1. **驱逐（④）只是末端一环，前面环节失管才把问题堆到驱逐爆发**
  2. **跨层（③）是备份不是舍弃**——store 后 block 还在 GPU；备份和驱逐是两条不联动路径
- ⑤标注"待测"——这是我们推断但还没实测的环节（诚实标注）

---



### 第 4 页：① 注册（出生）

【画什么】

```
T2c allocate_slots（schedule 步，forward 之前）
        │
        ▼
满 block（16 tok）？ ─否→ 暂不注册（尾块等下次 schedule）
        │是
        ▼
hash 已在 T1 算好：hash(parent_hash, token_ids)
        │
        ▼
cached_block_hash_to_block[hash] = block_id   ← GPU 注册（索引）
        │
        ▼
T3 Worker forward → KV 写入该 physical block   ← 内容填充（晚于注册）
```

【写什么】

- **做什么**：为满 block 建立 **hash → GPU block_id** 索引（不是把 KV 写进 CPU）
- **时机**（与第 1 页 T2c/T3 对照）：
  - **T1**：hash 链预计算
  - **T2c**：`cache_full_blocks` 写 GPU dict——**在 execute_model 之前**
  - **T3**：forward 才把 KV 写入 physical block
  - **CPU tier**：T4 `prepare_store` → `_policy.insert`（未就绪）；T6 `complete_store` → `is_ready=True` + SSD cascade
- **现状**：
  - 被动注册——只有 schedule 分配到的新满 block 才 insert dict
  - 链式 hash；只注册满 block（16 tok），尾块不缓存
  - ⚠️ **注册只写 GPU**；store 是 T4-T6 另一条路径
  - ⚠️ **注册 ≠ store ≠ prefill 完成**：索引先于 KV 内容就绪
- **agent 问题**：L0/L1_shared 可预知，为何不能 T0 前 eager 预注册？

【数字/证据】

- 链式 hash：`vllm/v1/core/kv_cache_utils.py:563-590`（`hash_block_tokens`），`:667-708`（`request_block_hasher` 逐块算）
- 只 hash 满 block：`kv_cache_utils.py:689-691`（注释 "We only hash full blocks"）
- block size=16：`vllm/config/cache.py:46`（`DEFAULT_BLOCK_SIZE=16`）
- 注册写 GPU dict：`block_pool.py:280-281`（`cache_full_blocks`，全函数无 connector 调用）
- 注册生产路径：`single_type_kv_cache_manager.py:331` → `block_pool.cache_full_blocks`（测试亦直接调）
- 注册时机（schedule 中段）：`v1/core/sched/scheduler.py:819`（`allocate_slots` 内）
- store 时机：`scheduler.py:1014` → `distributed/kv_transfer/kv_connector/v1/offloading/scheduler.py:729-902`

---



### 第 5 页：② 查找/命中（被使用）

【画什么】

```
新请求到达，token 序列 → 算 block hash 链
        │
        ▼
get_computed_blocks → find_longest_cache_hit
        │
   逐 block 查 cached_block_hash_to_block
        │
   ┌────┴────┐
   命中      miss → break（父 miss 则后续全 miss）
   │
   ├─ block 是 free 状态？→ touch 捞回（ref_cnt+1，移出 free queue）
   └─ 正常命中 → 复用
```

**三层接力查找图**（GPU/CPU/SSD 怎么衔接，这是本页最容易讲错的地方）：

```
block:     0      1      2      3      4      5      6      7   ...
           │      │      │      │      │      │      │      │
GPU 查:   命中   命中   命中   miss──┐
                                   │ GPU 查到 block3 miss，break
                                   │ GPU 命中的 0,1,2 不再查 CPU（已有）
                                   ▼
CPU 查:                          block3 命中   block4 命中   miss──┐
                                   ↑ 起点=GPU的miss点            │ CPU 查到 block5 miss
                                   │                              │ break
                                   ▼                              ▼
SSD 查:                                                       block5 ...（CPU miss 才轮到 SSD）
                                   ↑ 起点=CPU的miss点
```

要点（图上三句话）：

1. **逐 block 顺序查，遇 miss 即停**——GPU 和 CPU/SSD 两边都是 `for key in keys` 一个个查，第一个 miss 就 break
2. **每层起点 = 上一层 miss 点**——CPU 从 GPU 命中末尾开始（`start_block_idx = num_computed_tokens // block_size`），不重复查 GPU 已命中的；SSD 从 CPU miss 点开始
3. **不回头**——CPU 命中后继续查下一个 block 还是 CPU，不会"回 GPU 再试"；GPU 能命中的已经命中了，剩下的交给下层接力

【写什么】

- **做什么**：新请求来，在 index 里找已有 prefix
- **现状**：
  - 逐 block 查 hash 链，**遇第一个 miss 就 break**（链式 hash 的特性：父 miss 则子必 miss）
  - 命中 free 状态的块也能复用——`touch` 把它从 free queue 捞回（这是 vLLM 的隐式复用机制）
  - **三层接力**：GPU 查到 miss 后，CPU 从 GPU 的 miss 点接着查；CPU 也 miss 才轮到 SSD。每层起点 = 上一层 miss 点，不回头、不重复查上层已命中的
  - **GPU 和 CPU/SSD 是调度器的两次独立调用**（先 `get_computed_blocks` 查 GPU，再 `connector.get_num_new_matched_tokens` 查 CPU/SSD），靠 `num_computed_tokens`（GPU 命中数）衔接起点；**CPU 和 SSD 是同一次** `manager.lookup` **内部接力**（CPU 先、CPU miss 才查 SSD）
- **agent 问题**：
  - 并发时同批请求看不到彼此正在算的 prefix（P1）；T2c 注册后 T3 前同 step 内后续 waiting 请求**可能**看到空 KV 的 hash 索引
  - 链式 hash 遇内容发散点全 miss——不同 session 的 L1_unique 不同，发散点后整条链断掉
- **Running decode 不查 prefix**：只有 waiting/preempted 走 `get_computed_blocks`（`scheduler.py:660`）；running 用已有 `num_computed_tokens`
- 关键澄清（讲 P6 时别讲错）：**GPU miss 后 lookup 不会放弃**，会继续查 CPU tier（见上"三层接力查找图"）
- **CPU/SSD 额外命中**：`load_kv_async=True` → 本 step 不 forward（`scheduler.py:732-735,863-883`）

【数字/证据】

- 逐 block 查遇 miss 即停：`vllm/v1/core/single_type_kv_cache_manager.py:548-558`（注释 :549-551 明确）
- `get_computed_blocks`：`vllm/v1/core/kv_cache_manager.py:202-242`
- touch 捞回 free 块：`vllm/v1/core/block_pool.py:402-417`
- GPU/CPU 两次独立调用：`v1/core/sched/scheduler.py:660-662`（GPU）+ `:672-678`（CPU/SSD），靠 `num_new_local_computed_tokens` 衔接
- CPU 起点 = GPU 命中末尾：`offloading/scheduler.py:442`（`start_block_idx = num_computed_tokens // offloaded_block_size`），切片 `:443`
- CPU/SSD 逐 block 顺序查：`offloading/scheduler.py:336-348`（`_maximal_prefix_lookup` 的 `for key in keys`，miss 即 break）
- CPU miss 才查 SSD：`tiering/manager.py:251-269`（`:251` CPU 先，`:258` CPU miss 遍历 secondary）

---



### 第 6 页：③ 跨层移动（备份）—— 三级架构

> ⚠️ **关键澄清（源码核实）**：offload store **不是"舍弃"**，是**备份**。store 之后 block **还在 GPU**，并不因 store 了就从 GPU 消失。store 决定"CPU/SSD 有没有副本"，和"block 从 GPU 消失"（驱逐，见第 7 页）是**两条独立路径，不联动**。

【画什么】

**一张主图：三级结构 + 读（lookup/恢复）+ 写（store/备份）+ 淘汰**

> 全是「复制」不是「搬走」；SSD 不能直连 GPU（须 ④→②）。store 与驱逐（第 7 页）**不联动**。

```
═══════════════════════════════════════════════════════════════════════════════
                    跨层一张图：索引 · 五条路径 · 读/写分工
═══════════════════════════════════════════════════════════════════════════════

  索引（各层独立）          GPU                    CPU                  SSD
  ─────────────    cached_block_hash_to_block   OrderedDict           .bin 文件
                   (hash→block_id)              (OffloadKey→status)   (exists)

                        ┌──────────────┐
                        │     GPU      │  KV 在 HBM
                        └──────┬───────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │ 写·备份              │              读·恢复 │
         │                     │                     │
    ① store ──────────────────►│                     │  T4-T6 活请求每 step
    T4 占位→T5 DMA→T6就绪      │◄──────────────── ② load  T2b CPU 命中
    源 GPU 仍在                │    pre_forward      源 CPU 仍在
         │                     │    本 step 常不 forward
         │                     ▼
         │              ┌──────────────┐
         │              │     CPU      │  /dev/shm
         │              └──────┬───────┘
         │                     │
         │    ③ cascade ───────┼──────► SSD   T6 后无条件（非 CPU 满才写）
         │    源 CPU 仍在       │◄────── ④ promotion  T2b CPU miss & SSD hit
         │                     │        本 step 跳过；下 step 再 ②
         │                     ▼
         │              ┌──────────────┐
         └──────────────│     SSD      │
                        └──────────────┘
  ⑤ SSD ──×──► GPU 不存在（必须 ④ promotion → ② load）

───────────────────────────────────────────────────────────────────────────────
读路径（T2a + T2b lookup，决定 ② 或 ④，与 store 无关）
───────────────────────────────────────────────────────────────────────────────
  block:    0      1      2      3      4      5
  GPU 查:  命中   命中   miss ──────────────────────────┐
  CPU 查:                 从2起 命中   命中   miss ────┤→ ② load
  SSD 查:                                   从5起 查 ───┘→ ④ promotion
  GPU 命中 → touch 复用，不 load；每层 miss 即停，起点 = 上层 miss 点

───────────────────────────────────────────────────────────────────────────────
写路径（备份，每 step 活请求增量，不等 request 结束；默认只 prompt block）
───────────────────────────────────────────────────────────────────────────────
  ① GPU→CPU：next_stored_block_idx 起新满 block → T4 占位 → T5 拷数据 → T6 就绪
  ③ CPU→SSD：① 的 T6 成功后 cascade；GPU/CPU 副本都保留

───────────────────────────────────────────────────────────────────────────────
五条路径速查
───────────────────────────────────────────────────────────────────────────────
  #  方向      名称        触发                    源层还在？
  ① GPU→CPU   store      活请求每 step T4         GPU ✓
  ② CPU→GPU   load       T2b CPU 命中             CPU ✓
  ③ CPU→SSD   cascade    ① 成功 T6                CPU ✓
  ④ SSD→CPU   promotion  T2b SSD 命中             SSD ✓
  ⑤ SSD→GPU   （无）      ④→② 间接                —

───────────────────────────────────────────────────────────────────────────────
淘汰（与 store 独立，三层互不协调）          GPU LRU  │ CPU LRU  │ SSD 无淘汰
  GPU 驱逐只摘 hash，不查 CPU/SSD 有无副本    ○──✗──○──✗──○
  ⚠️ store 不防驱逐；驱逐不触发 store
═══════════════════════════════════════════════════════════════════════════════
```

**同一块的多层分布**（副本独立累积，不保证一致）：

```
状态                      GPU   CPU   SSD    经哪条路径
──────────────────────────────────────────────────────
prefill 注册，未 store       ✓     ✗     ✗     仅 GPU 注册
① 完成                      ✓     ✓     ✗     store
①+③ 完成                    ✓     ✓     ✓     store+cascade
GPU 驱逐                     ✗*    ✓     ✓     *只摘 hash，显存可被覆盖
GPU+CPU 淘汰                 ✗     ✗     ✓     SSD 垃圾可滞留
④ 完成（SSD→CPU）            ✗     ✓     ✓     promotion，SSD 不删

Agent：A prefill 完 → ①③ 备份 L0；B Turn0 GPU L0 miss → T2b → ② load
      CPU 也无 → ④ promotion → ②；P2 真丢 = ① 未完成/job flush
```

【写什么】

- **做什么**：一张主图讲清三级 **索引 + 五条路径 + 读/写分工**（见上【画什么】）
- **口播顺序建议**：先指三层索引 → 左写路径 ①③ → 右读路径 ②④ → 中间 block 接力查表 → 底部淘汰
- **备份 vs 恢复**：
  - **备份（写）**：① GPU→CPU store + ③ CPU→SSD cascade——活请求每 step 增量，**不等 request 结束**
  - **恢复（读）**：② CPU→GPU load、④ SSD→CPU promotion——由 **T2b 查找命中**触发；SSD **不能**直连 GPU（⑤ 不存在）
- **现状（源码确认）**：
  - **store 是备份，不是舍弃**：store 之后 block 仍在 GPU，store 只是"顺便在 CPU/SSD 存一份副本"
  - **store 是复制不是移动——同一块可同时存在于多层**：GPU→CPU store 后 GPU 仍在（store 不调 `free`）；CPU→SSD cascade 后 CPU 仍在（`complete_store` 只 `prepare_read` 读 CPU 复制到 SSD，CPU 块不删）。所以一个块可同时有 GPU+CPU+SSD 三份副本，三层是累积关系不是移动关系
  - **三层副本独立淘汰、互不协调——同一块在三层命运不一致**：GPU 驱逐只摘 GPU hash（不查 CPU/SSD 有没有副本）；CPU LRU 淘汰只删 CPU policy（不通知 SSD、不 cascade）；SSD 连淘汰都没有。没有任何机制保证三层副本一致：该删的没删（死 session 块在 SSD 滞留成垃圾）、该留的没留（GPU 驱逐时 CPU 可能还没副本→P2 真丢）。这正是"三级各自为政、无统一判据"的根源——复用价值应贯穿三层，现状是三层各算各的
  - **store 的触发**：每步调度对**活 request**（有 `num_scheduled_tokens` 的）发起，从上次 store 到的位置继续 store 新满块（`next_stored_block_idx` 游标推进）
  - **store 有门控，不是全量备份**：
    - `offload_prompt_only=True`（默认）时，**decode 阶段的 block 不 store**（游标不推进过 prompt 边界）
    - `store_threshold`（默认 **0**，不过滤；**≥2** 才启用 lookup 计数过滤；TieringSpec **不支持** ≥2）
  - **store 完成后无条件 cascade 到 SSD**（`complete_store` 里对所有 secondary tier，与 CPU 满不满无关）；不是"CPU 满才搬"
  - **store 落 CPU 是三阶段、跨步完成，最后真的把数据写进去了**（不是"只占位不写"）：
    1. `prepare_store`（schedule 末尾）：`_policy.insert` 把 key 插进 CPU 表 + 分好 CPU 块 + 构造 `store_spec` 传输任务，但 `is_ready=False`——这是"**占位**"，登记了 key、位分了，但 KV 数据还没拷过来
    2. **worker 执行拷贝（真正写入数据）**：`store_spec` 下发到 worker，worker 真的把 GPU 上那个 block 的 KV 张量数据复制到 CPU 占位块——**数据物理上写进了 CPU 内存（**`/dev/shm` **mmap），不是空壳**
    3. `complete_store`（拷完回调）：数据已到 CPU，把 `is_ready` 置真（可读了）+ 触发 cascade 到 SSD（同样 worker 拷贝写入 SSD `.bin`）。拷贝失败（`success=False`）则 `_policy.remove`+`_free_block`——占位块被删，数据确实没写进去
  - **"占位"是第1步的中间态，不是最终状态**：最终数据是真写进 CPU 和 SSD 的（否则 load 回来读什么）。占位态(`is_ready=False`)期间 lookup 返回 `None`（"有但没就绪，retry"），而不是 `False`（"真没有"），避免"数据正在搬"被误判成"CPU 没有"导致全量重算
  - **P6 load=0 的准确归因**：不是"数据没就绪"，是"store 拷贝没完成"——若 block 在 worker 拷完前被驱逐/in-flight job 被 flush（`success=False`），占位块被删，数据**没真正写到 CPU**，lookup 自然找不到。lookup 确实查 CPU（源码确凿），load=0 是 store 侧拷贝没落盘
  - **lookup**：先查 GPU，再以 GPU 命中末尾为起点查 CPU，再查 SSD——三层**顺序查**，不是统一 index
  - **淘汰**：三层各自独立 LRU/淘汰，**互不通知**
    - GPU LRU、CPU LRU/ARC、SSD **无淘汰**（靠文件名去重）
    - GPU 驱逐不通知 CPU，CPU 驱逐不通知 SSD
    - CPU 淘汰也是直接扔（`del` 或移 ghost），**不 cascade 到 SSD**；SSD 那份若之前 cascade 过则保留
- **agent 问题**：
  - store 只备份活 request 的 prompt 段，**不保证覆盖即将被驱逐的高价值 block**——驱逐和备份各干各的
  - 三级各自为政，没有任何统一判据贯穿
- ⚠️ **实测范围**：我们 P6 只测了 GPU↔CPU（load=0）；CPU↔SSD 行为是**源码确认**但**未实测**
- ⚠️ **P6 load=0 归因见上**（store 拷贝没落盘，不是"lookup 不查 CPU"——lookup 确实查 CPU）

【数字/证据】

- store 是备份、触发于活 request：`offloading/scheduler.py:729-902`（`_build_store_jobs`，`:735` 遍历 `num_scheduled_tokens`）
- **CPU→GPU load**：`scheduler.py:672-678,732-735,863-883` → `update_state_after_alloc`（`:581-648`）→ worker `start_load_kv`（`v1/worker/gpu/kv_connector.py:70-75`）
- **SSD→CPU promotion**：`tiering/manager.py:251-318`（lookup→`_initiate_promotion`→`on_schedule_end` flush）
- **CPU→SSD cascade**：`tiering/manager.py:517-534`（`complete_store` 后无条件）
- SSD 无直连 GPU：`docs/features/kv_offloading_usage.md:15`（Only CPU primary has direct GPU access）
- `offload_prompt_only` 跳过 decode block：`offloading/scheduler.py:749-756`
- `store_threshold` 默认 0、≥2 才过滤：`kv_offload/cpu/spec.py:100-103,68`；Tiering 禁 ≥2：`tiering/spec.py:148-150`
- cascade 无条件到 SSD：`tiering/manager.py:517-534`（`complete_store`）
- **store 落 CPU 三阶段**：占位 `prepare_store` → `_policy.insert` + 构造 `store_spec`（`cpu/manager.py:202-206`，`is_ready=False`）；worker 按 `store_spec` 把 GPU KV 数据拷进 CPU 块（真正写入）；就绪 `complete_store` → `is_ready` 置真（`cpu/manager.py:215-228`，`:226` 检查 `not block.is_ready`），失败则 `_policy.remove`+`_free_block`（`:229-234`）
- **占位→None**：`cpu/manager.py:118-122`（`_policy.get` 非 None 但 `is_ready=False` → 返回 `None`）
- **store 是复制不删 GPU**：store 路径全程不调 `free_blocks`/`kv_cache_manager.free`（`offloading/scheduler.py:729-902`）
- **cascade 不删 CPU**：`complete_store` 用 `primary_tier.prepare_read` 读 CPU（ref_cnt+1 临时保护）+ `tier.submit_store` 复制到 SSD，CPU 块不删（`tiering/manager.py:505-534`，注释 `:514-516` "protecting blocks from eviction during async transfer"）
- **lookup 命中不删其他层副本**：CPU 命中返回 True 不动 SSD；SSD 命中走 `_initiate_promotion` 复制回 CPU，SSD 不删（`tiering/manager.py:251-269`，`:261-263`）
- CPU 淘汰不 cascade 到 SSD：`kv_offload/cpu/manager.py:174-186`（只发 removed 事件），`policies/lru.py:42-57`（`del`）
- lookup 顺序查 GPU→CPU：`vllm/v1/core/sched/scheduler.py:660-698`（先 `get_computed_blocks` 得 local，再 `connector.get_num_new_matched_tokens`）
- connector `_lookup` 从 GPU 末尾继续：`offloading/scheduler.py:395-531`（`:404` 起点，`:442` start_block_idx）
- SSD 无淘汰：`tiering/fs/io.py:42-43`
- GPU 驱逐不通知 CPU：`block_pool.py:365-400`（`_maybe_evict_cached_block` 无 connector 调用）
- CPU LRU/ARC：`kv_offload/cpu/manager.py:26-29`

---



### 第 7 页：④ 驱逐（摘 hash 标记）+ ④' 抢占 preempt（真正腾 GPU 空间）

> ⚠️ **关键澄清（源码核实）**：
>
> - **驱逐** `_maybe_evict_cached_block` **不腾 GPU 空间**——只摘 hash 索引；块本已在 free queue
> - **腾 free 块数量**靠 `free_blocks` / preempt 后的 `free`
> - **Running** 请求 allocate 失败 → preempt 循环（`scheduler.py:472-514`）
> - **Waiting** 请求 allocate 失败 → break，**不 preempt**（`scheduler.py:833-840`）
> - store 不释放 GPU 块——与「GPU 腾空间」无关

【画什么】

```
═══════════════════════════════════════════════════════════════════════
④ 驱逐 = 分配新块时，摘掉复用块的 hash 标记（不删数据，不腾空间）
═══════════════════════════════════════════════════════════════════════

需要新 block → get_new_blocks → free_block_queue.popleft_n  (block_pool.py:333-347)
                                        │
                                        │ 弹出的块 ref_cnt==0
                                        ▼
                          _maybe_evict_cached_block  (block_pool.py:365)
                                        │
                          ┌─────────────┴─────────────┐
                          这个块还带 hash？            │
                          │是                          │否
                          ▼                            ▼
                  pop hash (从 GPU index 摘掉)    直接复用
                  reset_hash                        ref_cnt+=1
                          │
                          ▼
                  块变干净，供新数据覆盖
                  ⚠️ 全程不调 connector，不触发 store
                  ⚠️ 不删 KV 数据，不腾空间——块本来就在 free queue 里

  ⚠️ 触发条件：不是"GPU 满才触发"！是"分配新块时，弹出的 free 块恰好还挂在 hash 表"
  ⚠️ free 不够时根本走不到这里（allocate_slots 在 kv_cache_manager.py:418 先 return None）
  ⚠️ 判据 = free queue 弹出顺序（LRU），无 "if 高价值 then skip" 分支

═══════════════════════════════════════════════════════════════════════
④' 抢占 preempt = Running 请求 allocate 失败时腾空间（Waiting 只 break）
═══════════════════════════════════════════════════════════════════════

Running: allocate_slots 返回 None  (kv_cache_manager.py:418-420)
        │
        ▼ 循环直到成功或无可抢
_preempt_request  (scheduler.py:472-514,1033-1054)
        │
        ▼
kv_cache_manager.free(preempted_req)  ← 释放低优先级 running request 的所有 block
        │
        ▼
这些 block ref_cnt→0，进 free queue  (block_pool.py:433-441)

Waiting: allocate_slots 返回 None → break（scheduler.py:833-840），本 step 不再接纳新 waiting

  ⚠️ store 不释放 GPU 块；驱逐④不增加 free 数量
  ⚠️ watermark 也可能让 waiting 提前 return None（kv_cache_manager.py:363-420），仍不 preempt
```

再画一个"被驱逐的 block 有没有备份"的三种结局：

```
被驱逐的 block，CPU/SSD 有副本吗？(取决于时序，无保证)
   │
   ├── store 已完成 → CPU 有副本 → GPU 驱逐后能从 CPU load 回 (可恢复)
   ├── store 还在 in-flight 且 block 被重分配 → job 被 flush → 副本未落盘 → 真丢
   └── 根本没发起 store (decode block / 未调度 / 没过 threshold) → 真丢
```

【写什么】

- **做什么**：
  - **驱逐**：分配新块时，把从 free queue 弹出的复用块摘掉 hash 标记（让新内容能覆盖）
  - **preempt**：GPU 满到分配失败时，释放低优先级 running request 的 block 腾空间
- **现状（源码确认）**：
  - **驱逐不腾 GPU 空间**：`_maybe_evict_cached_block`（`block_pool.py:365`）只 `pop` hash + `reset_hash`，不删 KV 数据、不释放 block。块本来就在 free queue 里（已被 `popleft_n` 弹出），驱逐只是摘掉 hash 标记让它能被新数据覆盖
  - **驱逐触发条件不是"GPU 满"**：是 `get_new_blocks`（`:333`）分配新块时，弹出的 free 块恰好还挂在 hash 表。free 不够时 `allocate_slots` 在 `kv_cache_manager.py:418` 直接 return None，根本走不到驱逐
  - **preempt 仅 running**：`allocate_slots` 失败时 scheduler 抢低优先级 **running** 请求（`scheduler.py:472-514`）。**Waiting** 失败只 `break`（`:833-840`），不会 preempt
  - **GPU 满靠 preempt（running）**：释放 running request 的 block 回 free queue，是**增加 free 块数**的主要手段
  - **判据只有 LRU 顺序**，没有价值跳过逻辑——`_maybe_evict_cached_block` 里没有任何"if 高价值 then skip"分支
  - **驱逐不触发 store，也不检查是否已备份**——`_maybe_evict_cached_block` 全程不调 connector（`BlockPool` 类根本没有 connector 字段）
  - **被驱逐的 block 有没有 CPU 副本，无保证**（见上图三种结局）：取决于 store 异步完成的时序，和 store 是否覆盖了这块（`offload_prompt_only` 跳过 decode、`store_threshold` 过滤）
- **三个动作要分清（重要！）**：

  | 动作                              | 腾 GPU 空间?                        | 触发                                 | 对象                       |
  | ------------------------------- | -------------------------------- | ---------------------------------- | ------------------------ |
  | `_maybe_evict_cached_block`（驱逐） | 否（只摘 hash 标记）                    | `get_new_blocks` 分配新块时             | ref_cnt==0 的 free 块      |
  | `store`（跨层备份）                   | 否（只复制，不释放 GPU 块）                 | 每步调度对活 request                     | ref_cnt>0 的活 request 块   |
  | `_preempt_request`→`free`（抢占）   | **是**（释放活 request 块回 free queue） | running 的 `allocate_slots` 返回 None | 低优先级 **running** request |

- **agent 问题**：
  - 判据里没有价值信息，L0（全员共享的高价值 prefix）被无脑驱逐（P2）
  - **备份和舍弃各干各的，都不看价值**：该备份的（高价值、即将被驱逐的）可能没备份就被扔了（P2 真丢）；备份了的可能是死 session 的垃圾（垃圾滞留）；备份到 CPU/SSD 后三层各自淘汰、找不回（P6）

【数字/证据】

- 驱逐定义：`block_pool.py:365-400`（`:385` pop hash，`:390` reset_hash，不删数据不释放 block）
- 驱逐调用点：`get_new_blocks`（`block_pool.py:333-347`，`:352` 逐块调 `_maybe_evict_cached_block`）
- free 不够时先 return None：`kv_cache_manager.py:418-420`（`required > available → return None`）
- preempt（仅 running）：`scheduler.py:472-514,1033-1054`；waiting break：`scheduler.py:833-840`
- free 释放回 free queue：`block_pool.py:419-441`（`:434` ref_cnt-=1，`:441` append free queue）
- store 不释放 GPU 块：`offloading/scheduler.py:729-902`（store 路径全程不调 `free_blocks`/`kv_cache_manager.free`）
- 驱逐不调 connector：`block_pool.py:365-400` 全文无 connector 调用；`BlockPool.__init__`（`:149-183`）无 connector 字段
- free queue 弹出顺序 = eviction order (LRU)：`block_pool.py:134-135`（注释），`popleft_n` 弹队首
- 无价值跳过分支：`block_pool.py:365-400` 全文无 if-priority
- store in-flight 且 block 重分配时 flush：`offloading/scheduler.py:919-931`
- BlockRemoved event 单向外发、connector 不消费：`scheduler.py:1659-1673`，`offloading/scheduler.py:1083-1102`（`take_events` 只产出）
- 补充：另有 `evict_blocks`（`block_pool.py:443-460`）由 KV connector 调用，可对 ref_cnt>0 块摘 hash（不释放 block），是 connector 侧另一条驱逐路径，与 `_maybe_evict_cached_block`（分配时触发）不同
- P2 实测：5,829 blocks 被驱逐（见 `docs/26` §2.1）

---



### 第 8 页：⑤ 生命周期（真正的死亡——缺失）

【画什么】

```
session/request 结束
        │
        ▼
_free_request → free_blocks
        │
        ▼
block.ref_cnt -= 1
        │
   ┌────┴────┐
   ref_cnt>0   ref_cnt==0
   │           │
   保留        append 到 free_block_queue 尾部
              │
              ⚠️ hash 保留在 index 里！block 还"活着"
              │
              后续 get_computed_blocks 仍能命中它（touch 捞回）
              │
              只有当它作为 LRU 候选被驱逐时，才真死（hash 删）
```

【写什么】

- **做什么**：block 什么时候该彻底失效
- **现状（源码确认）**：
  - vLLM **没有显式 session 生命周期**
  - request 结束只减 ref_cnt、把块放回 free queue，**不删 hash**——block 当 LRU 候选留着
  - 后续请求还能命中这些"死 session 的块"（touch 捞回）
  - 只有当块排到 free queue 头部被驱逐时，才真正死（hash 删）
- **agent 问题**：session 结束，它的 L1_unique/L2 本该立刻失效，但系统不知道 session 死了——**死 session 的垃圾 block 滞留在 cache 里**，占着容量，甚至可能因为还在 index 里而被误判可复用
- ⚠️ **未实测**：这是源码确认的机制，但"垃圾滞留造成多少浪费"还没量化。PPT 诚实标注，留作后续实验钩子

【数字/证据】

- free 只减 ref_cnt 不删 hash：`vllm/v1/core/block_pool.py:419-441`（`:434` ref_cnt-=1，`:441` append free queue，全程无 pop hash）
- `_free_request`：`vllm/v1/core/sched/scheduler.py:1947-1969`
- 尾块先释放（前缀留更久）：`single_type_kv_cache_manager.py:375`（`reversed`）

---



### 第 8.5 页：一个完整例子——serving 从无到有、到满、到驱逐

> 前面第二部分把注册、查找、跨层备份、驱逐、生命周期五个环节拆开讲了。这页用一个端到端例子把它们串起来，看整个 serving 真实运转时 KV cache 怎么从空→填满→preempt→驱逐。
>
> 设小数字方便讲：GPU 容量 **8 个 block**（16 tok/块 = 128 tok），配了 CPU offload。

【画什么】一个分 **8 步**（含步骤3'）的时序，每步标三层 index 状态 + free queue 剩余：

```
═══════════════════════════════════════════════════════════════════════
设定：GPU 8 个 block（128 tok），CPU offload 开启。block size=16 tok。
      请求都是 agent 场景：共享 L0(system prompt)，各自 L1_unique。

⚠️ 先分清两种「满」（后面步骤都按这个口径）：
  · **free queue 满**：session 一结束，块 ref_cnt→0 就回 free queue——步骤2、3' 都会回满 8 块
  · **ref_cnt 满**：只有多个 **running** 请求同时占块，free 才会变少——步骤5 的 preempt 靠这个
  · session 结束 **不删 hash**——free 回满后，dict/CPU/SSD 里的 prefix 仍留着（这才是垃圾/驱逐的问题）
═══════════════════════════════════════════════════════════════════════

【步骤0：冷启动】
  GPU free queue: [B0,B1,B2,B3,B4,B5,B6,B7]  全空，8 个都 free
  GPU index:      {} 空 dict
  CPU index:      {} 空
  SSD:            空
  → 三层全空，没有任何已缓存 prefix

【步骤1：请求A进来（含 L0(2块) + L1_unique_A(3块) = 5块=80tok）】
  查找①：GPU dict 空 → block0 就 miss → break；CPU/SSD 也空 → 全 miss
         num_computed_tokens=0
  注册②：allocate_slots → cache_full_blocks 写 h0..h4 进 GPU dict（forward 前）
  forward③：worker prefill，KV 写入 B0-B4
  store④（schedule 末尾 + 同 step worker/update）：
         T4 prepare_store → CPU 占位(is_ready=False)
         T5 worker DMA → T6 complete_store 置 is_ready=True → cascade SSD
  状态：
    GPU free: [B5,B6,B7] 剩3个（B0-B4 被 A 持有，ref_cnt>0）
    GPU index: {h0,h1(L0), h2,h3,h4(L1_unique_A)}
    CPU index: {h0..h4} 全就绪
    SSD:       {h0..h4} .bin 文件

【步骤2：请求A结束】
  生命周期⑤：_free_request → B0-B4 ref_cnt→0，进 free queue 尾部当 LRU 候选
         ⚠️ hash 不删！GPU dict 里 h0..h4 还在
  状态：
    GPU free: [B5,B6,B7, B0,B1,B2,B3,B4] **8 个全 free**（物理块全回收到 free queue）
    GPU index: {h0..h4} 还在（A 的 prefix 现在是可复用缓存）
    CPU/SSD:   不变，副本还在

  ⚠️ free 已回满，但 hash/CPU/SSD 副本没清——不是「GPU 被 A 占满了」，是「缓存索引还在」

【步骤3：请求B进来（含 L0(2块) + L1_unique_B(3块)，L0 与 A 相同）】
  查找①：GPU 查 → h0,h1 命中（L0 相同）→ touch 捞回 B0,B1（ref_cnt+1，移出 free queue）
         → h2 miss（L1_unique_B ≠ A 的 h2）→ break
         CPU 查（GPU 命中末尾=block2 起）→ h2,h3,h4 是 B 的独特内容，CPU 没有 → miss
         num_computed_tokens = 2块 = 32 tok（L0 复用了！）
  注册②+forward③：num_new_tokens=3，allocate+注册 h2_B..h4_B（forward 前），再 prefill 写 KV
         allocate 从 free **队首** pop → 取 B5,B6,B7（不是 B2-B4）
  store④：B 的 3 个新 block → CPU/SSD（T4~T6 流水线）
  状态（**B 尚未结束，仍在 running**——占 5 块 ref_cnt>0）：
    GPU used: B0,B1（L0 复用）+ B5,B6,B7（B 新块）= 5 块
    GPU free: [B2,B3,B4] 剩**3**个（A 的死 L1，free 但 dict 里 hash 还在）
    GPU index: {h0,h1, h2,h3,h4(A的), h2_B,h3_B,h4_B}
    CPU/SSD:   A 的 h0..h4 + B 的 h2_B..h4_B

  ⚠️ 注意：A 已结束，但 A 的 L1_unique_A(h2,h3,h4) 还在 GPU dict + CPU + SSD 滞留——死 session 垃圾
  ⚠️ B 还在 running 时 free 只有 3——这是因为 **ref_cnt 被 B 占着**，不是 A 没释放（A 早已释放）

【步骤3'：请求B结束】
  _free_request → B0,B1,B5,B6,B7 ref_cnt→0，append 到 free queue 尾部
  状态：
    GPU free: [B2,B3,B4, B0,B1,B5,B6,B7] **又一次 8 个全 free**（和步骤2 一样，结束就回满）
    GPU index: 同上（B 的 prefix 变成可复用缓存，hash 不删）

【步骤4：请求C进来要 4 块——free 仍充裕，pop 旧 cache 块触发驱逐④】
  ⚠️ C 来时 free 有 8 块，**并不缺物理块**——不是「GPU 快满了」
  ⚠️ 本步要讲的是：allocate 从 free 头 pop 到 **带 hash 的旧 cache 块**时，驱逐④摘 dict 索引
  allocate_slots 要 4 块 → get_new_blocks 从 free 头取 B2,B3,B4,B0
  驱逐④：4 块都带 hash → _maybe_evict_cached_block 摘掉 h2,h3,h4(A) + h0(L0) + reset_hash
         ⚠️ 不调 connector！不查 CPU/SSD 有没有副本！
         ⚠️ h0 是 L0（全员共享高价值），照样被摘——无价值判据
  C allocate+注册+forward，store...
  状态：
    GPU used: B2,B3,B4,B0 被 C 占用
    GPU free: [B1,B5,B6,B7] 剩4个（B 结束时留下的带 hash 块）
    GPU index: {h1, h2_B,h3_B,h4_B, h0_C..h3_C}  ← h0 被驱逐摘了！

  ⚠️ h0(L0) 被 GPU 驱逐，但 CPU/SSD 那份 h0 副本还在（步骤1 store 过）——
     以后有请求查 L0，GPU miss，能从 CPU load 回（这就是 offload 的意义）
  ⚠️ 但 h2,h3,h4(A的L1_unique) 如果当时 store 没 in-flight 完成 → 真丢（P2）

【步骤5：running 并发占满 ref_cnt——D 扩容时 free 不够，触发 preempt④'】
  ⚠️ 这步才是真的「free 不够」——靠 **C、D 同时 running** 占块，不是死 session 占着不还
  承接步骤4：C running 占 4 块（B2,B3,B4,B0），free=[B1,B5,B6,B7] 共 4 个
  D 先 schedule 进来 prefill，allocate 3 块 → 从 free 头取 B1,B5,B6
         pop B1 时驱逐 h1(L0)；D running 占 3 块
  状态：C 占 4 + D 占 3 = 7 块，free 只剩 [B7] **1** 个
  下一步 D 再 decode 扩容要 3 块 → running 路径 allocate_slots 返回 None
         → preempt④' 抢 C（scheduler.py:472-514）
         → kv_cache_manager.free(C) → C 的 4 块释放回 free queue
         → C 进 waiting，num_computed_tokens=0（下次重排，CPU 有副本可 load 回）
  状态：
    GPU free: 回收 C 的 4 块 + 原 B7 = 够给 D 扩容
    ⚠️ 腾 GPU 空间靠 preempt，不是靠驱逐④，也不是靠 store③
    ⚠️ store 不释放 GPU 块，驱逐④不腾空间——只有 preempt 腾空间

【步骤6：垃圾累积——多个 session 来了又走】
  每个 session 的 L1_unique 都被 store 到 CPU/SSD，session 结束后：
    GPU：L1_unique 块迟早被驱逐④（hash 摘了，但数据可能还在显存没覆盖）
    CPU：LRU 慢慢淘汰（不通知 SSD）
    SSD：⚠️ 无淘汰！靠 os.path.exists 去重，假设磁盘无限
  → 死 session 的 L1_unique 在 SSD 越积越多，永远不被查（session 死了没人查）
  → GPU index 里也有一堆死 hash（父链断了的子块，查不到但占 dict）

═══════════════════════════════════════════════════════════════════════
这个例子暴露的根问题（题眼，第 9 页展开）：
═══════════════════════════════════════════════════════════════════════
  每个决策点的判据都是"时间/hash/是不是活 request"，没有一个看"复用价值"：
  - 查找：hash 链遇 miss 即停 → L1_unique 发散点后全断
  - 注册：schedule 时 forward **前**写 GPU dict → L0 可预知却要等 allocate
  - store：活 request prompt 段就备份 → 不分死活，死 session 垃圾也备份
  - 驱逐④：free queue LRU 顺序 → L0 高价值照样被摘
  - preempt④'：低优先级 running request → 不看价值
  - 三层副本：各自独立 LRU → 同一块三层命运不一致
  - 生命周期⑤：无，靠 LRU 间接 → 死 session 垃圾滞留 SSD（无淘汰）
```

【写什么】

- 这页用一个具体例子把五个环节跑一遍：冷启动→A 结束留缓存→B 复用 L0（**B 未结束**）→B 结束→C 触发驱逐→D 触发 preempt→垃圾累积
- **重点让听众看到四件事**：
  1. **session 结束 → free queue 回满**（步骤2、3' 都是 8 块 free）；持久的是 **hash/CPU/SSD 副本**，不是物理块被占死
  2. **步骤3 free 只有 3**：因为 B **还在 running** 占 5 块 ref_cnt>0，不是因为 A 没释放
  3. **步骤4 的驱逐④**：free 仍充裕时也会发生——pop 到带 hash 的旧 cache 块就摘索引；**不等于 GPU 快满**
  4. **步骤5 的 preempt④'**：多个 **running** 并发把 ref_cnt 占满，free 才真正不够——腾空间靠 preempt，驱逐④只摘 hash，store 不 free GPU
- 这页是第二部分（五个环节分讲）的综合应用，也是第三部分（题眼）的具体铺垫：例子末尾的"根问题"表直接引出第 9 页
- 数字是教学用的小数字（8 block），实际部署 num_gpu_blocks 由 `gpu_memory_utilization` 算（`scheduler.py:149` `cache_config.num_gpu_blocks`），block size 默认 16（`config/cache.py:46`）

【数字/证据】

- 冷启动 index 空：`block_pool.py:171`（`cached_block_hash_to_block = BlockHashToBlockMap()` 空初始化）
- 冷启动 free queue 满载：`block_pool.py:162-168`（所有 block 进 free_block_queue）
- 第一个请求全 miss：`get_cached_block`（`block_pool.py:184-209`）查空 dict 返回 None
- 查找→注册→forward 顺序：`scheduler.py:660` → `:819`（allocate+cache_full_blocks）→ `engine/core.py:454-455`（execute_model）
- store 在 schedule 末尾：`scheduler.py:1014` → `offloading/scheduler.py:729`
- 请求结束 free 不删 hash：`block_pool.py:419-441`（`_free_request`→`free_blocks`，ref_cnt-=1 进 free queue，无 pop hash）
- touch 命中块移出 free queue：`block_pool.py:402-417`（`ref_cnt==0` 时 `free_block_queue.remove`）
- allocate 从 free 队首 pop：`block_pool.py:333-347`（`get_new_blocks`→`popleft_n`）
- 驱逐④摘 hash：`block_pool.py:365-400`（分配新块时，弹出块带 hash 就 pop+reset_hash）
- preempt④'（running）：`scheduler.py:472-514,1033-1054`
- SSD 无淘汰：`tiering/fs/io.py:42-43`（`os.path.exists` 去重，无 LRU）
- block size=16：`config/cache.py:46`
- num_gpu_blocks 配置：`scheduler.py:149`（`cache_config.num_gpu_blocks`）

---



## 第三部分：题眼——判据缺失



### 第 9 页：所有问题归到一个根

【画什么】对照表（这是 PPT 的题眼页）：


| 决策点    | vLLM 现有判据                                       | 缺失的判据              | 后果                           |
| ------ | ----------------------------------------------- | ------------------ | ---------------------------- |
| 注册     | schedule 时 forward 前写 GPU dict                  | 内容可预知性             | L0/L1_shared 不该等第一次 prefill  |
| 查找     | hash 链（遇 miss 即停）                               | 语义层级               | 并发不可见、发散点全断                  |
| 跨层（备份） | "活 request + prompt 段"（门控）+ last-access（三层各自淘汰） | 复用价值 + 备份↔舍弃联动     | 备份不覆盖将被驱逐的高价值块；三级各自淘汰 load=0 |
| 驱逐（舍弃） | last-access（LRU 顺序）                             | 复用价值 + 备份状态        | L0 被无脑驱逐，且可能没备份就真丢           |
| 生命周期   | last-access（间接，等 LRU）                           | 复用价值（session 死→归零） | 垃圾滞留                         |


【写什么】

- 一句话总结：**vLLM 每个 cache 决策点的判据都是"时间"或"hash 链"或"是否活 request"，没有一个用"复用价值"**
- 这不是某个环节有 bug，是**所有环节共用一个 agent 盲的判据**
- GPU block 字段里压根没有 value 字段——源码层面就不具备价值感知能力
- 三层架构每一层都用各自的 LRU/时间判据，没有统一判据贯穿三级
- **备份和舍弃不联动**：store 只看"是不是活 request 的 prompt 段"，驱逐只看 LRU 顺序，两者互不知道——该备份的没备份（P2 真丢），该扔的反而备份了（垃圾滞留），备份的找不回（P6）

【数字/证据】

- GPU block 无 value 字段：`vllm/v1/core/kv_cache_utils.py:116-162`
- CPU BlockStatus 无 value 字段：`kv_offload/cpu/policies/base.py:10-33`
- SSD 无淘汰：`tiering/fs/io.py:42-43`
- store 和驱逐不联动：`offloading/scheduler.py:729-902`（src 是活 request）vs `block_pool.py:365-400`（驱逐不调 connector）

---



### 第 10 页（可选）：我们的方向

【写什么】

- 核心方向：引入**复用价值**作为统一判据，贯穿 cache 管理全链（注册/查找/跨层/驱逐/生命周期）
- 不是给 L0 贴"永不驱逐"标签——L0 是价值判据的**结果**，不是先验规则
- 不展开技术细节（回看/前看等未定）

【画什么】

- 复用第 9 页的表，把"缺失的判据"列改成"AgentKV 引入复用价值"，箭头指向每个决策点

---



## 附：写 PPT 时的几个纪律

1. **先画图后填字**——第 3 页时间轴是骨架，画清楚整个 PPT 就立住了
2. **每页配一个源码锚点**——不空讲机制，每页脚注带 file:line
3. **易错点（节选，源码核实）**：
  - **engine step** = schedule(T2/T4) → execute(T3/T5) → update(T6)（第 1 页）
  - CPU insert 在 T4、is_ready 在 T6——不是 T6 才 insert（第 1、4、6 页）
  - CPU/SSD 命中 → 该请求本 step 不 forward（WAITING_FOR_REMOTE_KVS 或 skipped）
  - P6 load=0 不是"不查 CPU"——lookup 确实查 CPU，是 store 侧/时序问题（第 6 页）
  - 驱逐删 hash ≠ free 删 hash——两种"不要了"不一样（第 7、8 页）
  - `cpu_offload_gb` ≠ KV cache tier——那是模型权重 offload（第 1 页）
  - **offload store 不是舍弃，是备份**——store 后 block 还在 GPU（第 6 页）
  - **跨层五条路径**：① store ② load ③ cascade ④ promotion；SSD 不直连 GPU（第 6 页）
  - **preempt 仅 running**；waiting allocate 失败只 break（第 7 页）
  - **驱逐不触发 store**——被驱逐块有没有 CPU 副本无保证（第 7 页三种结局）
4. **⑤ 生命周期诚实标"未实测"**——源码确认机制，但浪费量未量化
5. **别用 P1/P2 编号当主线**——用"注册/查找/跨层/驱逐/生命周期"语言，P 编号只括注



## 附：源码 file:line 速查

> 路径均相对 `Engine/vllm/vllm/`；offloading 调度 = `distributed/kv_transfer/kv_connector/v1/offloading/scheduler.py`


| 环节           | 关键位置                                                                                                                    |
| ------------ | ----------------------------------------------------------------------------------------------------------------------- |
| engine step  | `v1/engine/core.py:443-470`                                                                                             |
| 注册           | `block_pool.py:211-283`（cache_full_blocks），`single_type_kv_cache_manager.py:331`                                        |
| 查找           | `kv_cache_manager.py:202-242`，`single_type_kv_cache_manager.py:548-558`，`block_pool.py:402-417`（touch）                  |
| 跨层（备份 ①③） | `offloading/scheduler.py:729-902`（store），`cpu/manager.py:202-228`，`tiering/manager.py:517-534`（cascade） |
| 跨层（恢复 ②④） | `sched/scheduler.py:672-883`，`offloading/scheduler.py:581-648`，`gpu/kv_connector.py:70-75`（load），`tiering/manager.py:251-318`（promotion） |
| 跨层（查找） | `sched/scheduler.py:660-698`，`offloading/scheduler.py:395-531,579` |
| 驱逐           | `block_pool.py:365-400`（`_maybe_evict_cached_block`），`:443-460`（`evict_blocks` connector 路径）                            |
| preempt      | `sched/scheduler.py:472-514`（running）；`:833-840`（waiting break）                                                         |
| store↔驱逐不联动  | `offloading/scheduler.py:919-931`；`sched/scheduler.py:1659-1673`（event publish，offloading 不消费 GPU 驱逐）                   |
| 生命周期         | `sched/scheduler.py:1947-1969`，`block_pool.py:419-441`                                                                  |
| 数据结构         | `kv_cache_utils.py:116-162`，`kv_offload/cpu/policies/base.py:10-33`                                                     |


