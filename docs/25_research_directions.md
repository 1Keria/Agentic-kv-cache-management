# AgentKV 后续研究方向

> 日期: 2026-06-26
> 目标: 在现有 vLLM/SGLang KV cache 测量基础上，确定能支撑顶级系统会议的研究方向
> 背景: 已完成 P1-P7 痛点的测量与归因（见 `docs/report.md`），但缺少"改进原型 + 量化收益"
> 约束: 倾向无损改进（不做有损的近似 KV 复用）；需要能在真实 serving 框架上跑的原型

---

## 0. 现状判断：我们还缺什么

**已经扎实**：
- Agent trace 画像（L0/L1/L2 分层、增长 3.64×、并发到达模式）
- P2/P6 是 [MEASURED] + 根因清晰（L0 被驱逐 5,829 blocks；offload store 14.96GiB/load 0）
- vLLM vs SGLang 对比（含 S4 证明 SGLang 统一树也保不住 L0）

**顶会系统论文的硬通货**：测量发现 gap → 提出机制 → 原型实现 → 量化收益
**我们卡在**：第二步往第三步走——没有一个跑起来的"改进原型"证明收益。

**关键认知更新**（2026-06-26 验证）：
- L1 不是同项目完全共享，而是 L1_shared(~1,664 tok, 21.8%) + L1_unique(78.2%)
- 真实跨 session 可复用 = L0(6,163) + L1_shared(1,664) ≈ 7,827 tokens
- vLLM 源码确认逐请求串行处理，B 能见 A 注册的 blocks → P1 的 L1 miss 主因是**内容发散**，不是注册时序 bug
- 这让 P1 的可优化空间从"整个 L1"缩到"L1_shared"，纯并发方向撑不起顶会

基于以上，下面三个方向是从"测量"走向"机制+原型"的具体路径。

---

## 方向一：AgentKV —— Agent-Aware 层级 KV 管理（主线推荐）

### 核心 idea

把 P2 + P6 打包成一个统一的机制：**价值感知的层级 KV 管理**。

现有两个系统都没解决"Agent 高价值 prefix 在压力下被驱逐"：
- **vLLM**：GPU 单层 LRU 无脑驱逐 L0（P2，5,829 blocks）；GPU/CPU 双层独立 LRU 互不协调，offload 形同虚设（P6，load=0）
- **SGLang**：HiRadixCache 虽然统一了树，但**叶子优先驱逐在极端压力下也保不住 L0**（S4 实测 cached=3）

→ gap 真实存在，且两个最佳系统都没解决。

### 技术机制

**机制 A：Value-Aware Eviction（解决 P2）**

给 prefix block 标记"复用价值"，驱逐时按价值而非纯 LRU：

```
当前 vLLM:
  free queue 头部 (最久未用) → 直接驱逐，不看价值

AgentKV:
  驱逐时跳过 protected 标记的 L0 / 项目级 L1_shared blocks
  protected 来源:
    - L0 (system prompt): 全 session 共享，价值最高 → 永不驱逐（或最后驱逐）
    - L1_shared (项目模板 ~1,664 tok): 同项目共享 → 高保护
    - L1_unique / L2: session 特有 → 正常 LRU
```

价值标记可以来自：
1. **显式标注**：Agent 框架在发请求时声明哪些 message 是 system/project 级（需 API 配合）
2. **隐式推断**：通过 hash 出现频率推断（L0 在所有请求都出现 → 自动 protected），无需 Agent 配合

**机制 B：Unified Prefix Tier（解决 P6）**

让 GPU 和 CPU 共享一个 prefix index，offload 数据能被 prefix lookup 找回：

```
当前 vLLM:
  GPU hash table (cached_block_hash_to_block)  ←─ find_longest_cache_hit 只查这里
  CPU offload _policy (独立 LRU)               ←─ 被驱逐的 hash 在这里也独立 LRU 掉了

AgentKV:
  统一 prefix index (一个 hash → block 元数据)
    ├─ GPU location (if resident)
    └─ CPU location (if offloaded)
  find_longest_cache_hit 查统一 index:
    GPU 命中 → 直接用
    GPU miss / CPU 命中 → 触发 load_back（异步）
  驱逐策略:
    GPU 驱逐时不删 index 条目，只清 GPU location，保留 CPU location
    CPU 驱逐时才真正删 index 条目
```

这本质是**把 SGLang HiRadixCache 的"统一树"思想移植到 vLLM 的 block-hash 架构上**，但加上机制 A 的价值感知——这是 SGLang 没做的。

### 为什么能发顶会

1. **动机扎实**：trace 显示 13.6% session 单独超容量，多 session 并发更严重；L0 占首轮 46.3% 却被无脑驱逐
2. **gap 有铁证**：P2 5,829 blocks、P6 load=0，都是 [MEASURED] 可复现
3. **对比干净**：vLLM（不统一）vs SGLang（统一但无价值感知）vs AgentKV（统一+价值感知）——三段对比
4. **关键差异化**：S4 证明 SGLang 的统一树**在极端压力下也保不住 L0**（cached=3），这是 AgentKV 价值感知要解决的、SGLang 没解决的问题

### 原型与收益量化

**原型**：在 `Engine/vllm`（editable install）上改：
- `block_pool.py`：`_maybe_evict_cached_block()` 加 value-aware 跳过逻辑
- 新建 unified prefix index，替换 GPU/CPU 双 hash table
- `find_longest_cache_hit()` 改为查统一 index

**收益目标**（可量化）：
| 场景 | 现状 (vLLM) | AgentKV 目标 |
|------|------------|-------------|
| 压力下 L0 命中 | 0 tokens | 接近 6,163 tokens（L0 全保） |
| offload load_back | 0 bytes | >0（offload 真正可用） |
| 压力场景 TTFT | 冷启动级（300ms+） | 显著降低（prefix 恢复） |

### 风险

1. **改 vLLM 内核有工程量**——但 editable install 现成，且改动集中在 block_pool 和 hash table 两处，可控
2. **SGLang 已经部分解决 P6**——必须靠 S4 的"统一树也保不住 L0"来论证差异化，否则被认为 incremental
3. **价值标记的隐式推断可能不准**——需验证 hash 频率能否可靠区分 L0/L1_shared/L1_unique

---

## 方向二：调度时机范式 —— 长 Prefix 同批并发复用（独立方向，源码确认 gap）

### 源码确认的关键事实（2026-06-26）

vLLM 和 SGLang 对"同批并发请求能否复用彼此正在计算的 prefix"采用了**两种相反的调度范式**，且各有硬伤：

| | vLLM | SGLang |
|---|---|---|
| 调度结构 | 单循环逐请求交错：A 查→A 注册→B 查→B 注册 | 三阶段分离：全查→全 prefill→（forward）→全注册 |
| 同批 B 能见 A 的 KV？ | **能**（FullAttention，`cached_block_hash_to_block` 是普通 dict，A 的 `cache_blocks()` 在 `allocate_slots()` 同步执行，B 在下一轮才查） | **不能**（所有 `match_prefix()` 在 Phase 1 完成，`insert()` 推到 Phase 3 forward 之后） |
| 同批保护机制 | 仅 Mamba 有 `cached_blocks_this_step` 守卫；FullAttention 无 | 结构性：insert 是独立阶段 |
| Agent 并发 L1 实测命中 | ≈0% | ~15%（in-batch 补救） |

**反直觉点**：vLLM 理论上能见，实测却 ≈0%；SGLang 理论上不能见，实测却有 ~15%。原因是两者各有不同的漏失机制。

### 两个范式的硬伤（gap 所在）

**vLLM 范式的漏失**（"能见但有条件"）：
1. **顺序依赖**：B 只有排在 A 之后才命中；队列顺序由 FCFS/priority 决定，不保证共享 prefix 的请求相邻
2. **block 对齐**：只缓存完整 block，部分尾 block 不注册；`find_longest_cache_hit` 首 miss 即停
3. **分步算不完**：chunked prefill 下 A 可能一步算不完整个 L1，B 这一步只能命中已注册部分，剩余要等下一步
4. **内容发散**：不同 session 的 L1_unique 不同，链式 hash 在发散点后全 miss（这是 P1 的主因，与时机无关）

**SGLang 范式的漏失**（"同批不可见，靠阈值过低的补救"）：
1. 同批所有兄弟请求的 `match_prefix` 在 Phase 1 全做完，此时谁都没 insert → 每个请求各算一遍 L1
2. in-batch 机制（`waiting_queue_radix_tree`，模拟树）只在**真实 cache 命中 ≤32 tokens** 时触发，目的是为"the"这种短公共词设计的
3. Agent L1 是 1,664-3,000 tokens，远超 32 → in-batch 路径被完全跳过 → 同批兄弟无法复用

→ **gap 真实存在**：长 prefix 的同批并发复用，两个范式都没做好。vLLM 因对齐+顺序+分步而漏，SGLang 因阈值过高而漏。

### 核心 idea：跨范式统一的长 Prefix 同批复用

不依赖 prefill 完成的**预测性注册**，让同批兄弟请求在调度阶段就能命中共享的 L0/L1_shared：

```
当前两个范式:
  vLLM:  A 查 → A prefill → A 注册 → B 查(能见,但有对齐/顺序/分步限制)
  SGLang: 全查(都miss) → 全prefill → forward → 全注册(同批永远见不到)

AgentKV:
  请求到达 → 立即预注册已知共享的 L0/L1_shared 的 block hash
           → 调度时所有兄弟请求的 lookup 直接命中预注册 hash
           → 第一个请求 prefill 时填充已注册 block,后续兄弟复用(不重复 prefill)
```

关键点：L0 和 L1_shared 的内容是**可预知的**（system prompt 和项目模板在 session 开始前就确定），所以可以 eager 注册而不依赖 prefill 完成。这同时绕过了 vLLM 的对齐/顺序/分步限制，和 SGLang 的同批不可见限制。

### 技术机制

**机制 A：Eager Prefix Registration**
- 请求到达时，把已知共享 prefix（L0 + 项目级 L1_shared）的 block hash 预注册到 index
- 后续兄弟请求的 lookup 直接命中，无需等第一个请求 prefill
- 正确性保障：预注册 hash 必须与实际 prefill 产出的 block 严格一致（内容确定 → 可保证）

**机制 B：Batch-Aware Scheduling（解决 vLLM 的顺序依赖）**
- 把共享 prefix 的请求**聚合同批**，并保证共享 prefix 先被预注册
- 类似 SGLang 的 LPM/DFS-weight，但适配 Agent 长 L1（不受 32 token 阈值限制）

### 为什么能发顶会（潜力中高，比之前评估更高）

1. **gap 是架构层面的设计取舍**，不是单点 bug——vLLM 和 SGLang 是两种主流范式，我们揭示两者在长 prefix 同批复用上**都没做好**，这个 framing 比"修 vLLM 的并发"高一个层次
2. **有源码铁证**：vLLM 同批可见（FullAttention）vs SGLang 同批不可见，是可复现的源码级事实
3. **收益可量化**：附录 C，Turn 0 同项目并发 +1,488 tok/req，TTFT ~5×
4. **对比干净**：vLLM（交错但有条件）vs SGLang（分离+低阈值）vs AgentKV（预测性注册）

### 风险

1. **收益天花板**：可优化空间是 L1_shared(~1,664 tok)，Turn 加深后 L1_unique/L2 占比上升，并发可复用空间收窄
2. **正确性**：预注册 hash 必须和实际 prefill 产出严格一致，否则"假命中"
3. **场景局限**：只在"同项目多 session Turn 0 并发冷启动"收益最大；长 session 收益收窄

### 与之前评估的修正

之前把这个方向评为"中低潜力、不建议独立"，是基于**错误的认知**（以为 vLLM 也同批不可见，和 SGLang 一样）。源码确认 vLLM 实际同批可见后，这个方向的 framing 升级为"**两种调度范式在长 prefix 同批复用上各有硬伤**"，差异化更强，**可以独立成方向**，也可以和方向一组合（eager 注册到方向一的 unified index）。

---

## 方向三：Prefix 增长感知的动态内存管理（针对 P4，长 session 场景）

### 核心 idea

Agent session 的 KV 占用随 turn 增长 3.64×（Turn 0 中位数 8,810 → Turn 30 增长到 28,884），13.6% session 单独超 44K 容量。现有系统的内存管理是**被动的**——等容量不足才驱逐/抢占，没有预测性。

**观察**：Agent 的 prefix 增长是**可预测的**——同一 session 的历史 turn 长度能预测后续 turn 的增长趋势；同项目的 session 增长模式相似。

### 技术机制

**机制 A：Growth-Aware Memory Reservation**

```
当前:
  容量不足 → 被动驱逐 L0 / 排队等待

AgentKV:
  预测当前 session 的 KV 增长轨迹（基于历史 turn 长度）
  预留空间给"即将增长的高价值 session"
  提前把低价值 prefix (L1_unique/L2) offload 到 CPU
  保留 GPU 空间给 L0 和正在增长的 session
```

**机制 B：Session-Level Memory Planning**

把单个 block 的管理提升到 session 级别：
- 跟踪每个活跃 session 的当前 KV 占用 + 预测增长
- 当多 session 并发时，按"预测总占用 vs 容量"提前做 offload 决策
- 避免等到 `allocate_slots()` 失败才被动响应

### 为什么能发顶会（潜力中等偏上）

- 场景真实：13.6% session 超容量，多 session 并发更严重
- "预测性 vs 被动响应"是一个清晰的系统设计维度
- 和 P3（preemption 丢 decode）联动：如果能预测增长，可以提前 offload decode 而不是等 preempt

### 风险

1. **预测准确性**：Agent turn 长度方差大（增长比 mean 9.12× vs median 3.64×），预测可能不准
2. **和方向一重叠**：本质也是"价值感知的内存管理"，只是多了预测维度——可能被合并进方向一
3. **P3 难触发**：preemption 在当前实验条件极难复现，机制 B 的收益难直接量化

### 定位建议

**适合作为方向一的扩展维度**，而不是独立工作。方向一做"当前价值感知"，方向三加"未来增长预测"，组合成一个完整的"时空感知 KV 管理"。

---

## 方向对比与推荐

| 维度 | 方向一：层级管理 | 方向二：调度时机范式 | 方向三：增长预测 |
|------|----------------|-------------------|----------------|
| 解决痛点 | P2 + P6（核心） | P1 + 调度架构（并发） | P4 + P3（长 session） |
| 可优化空间 | 大（6,163 tok L0 + offload） | 小-中（L1_shared ~1,664 tok，但场景价值高） | 中（13.6% 超容量 session） |
| 证据强度 | [MEASURED] 铁证 | 源码级确认 + [MEASURED] | [TRACE] + 部分 [MEASURED] |
| 差异化 | S4 证明比 SGLang 强 | **两范式各有硬伤，架构级 framing** | 预测性是新维度 |
| 工程量 | 中（改 block_pool + hash table） | 中（改调度循环 / 预注册） | 中（需预测模型） |
| **顶会潜力** | **高** | **中高**（升级后） | 中 |

### 两条主线候选

现在有两个可独立成主线的高潜力方向：

**主线候选 A = 方向一**（Agent-Aware 层级 KV 管理）
- 证据最硬（P2/P6 [MEASURED]）
- gap 真实且两个系统都没解决（S4 是关键差异化）
- 可优化空间最大（整个 L0 + offload 有效性）
- 原型改动集中可控

**主线候选 B = 方向二**（调度时机范式）
- 架构级 framing（两种主流范式各有硬伤），层次更高
- 源码级铁证（vLLM 同批可见 vs SGLang 同批不可见）
- 但可优化空间是 L1_shared，收益天花板低于方向一
- 场景聚焦（同项目多 session Turn 0 并发冷启动）

### 推荐组合

两种可行路径：

**路径 1（方向一为主，方向二/三为辅）**：
- 方向一做 value-aware unified hierarchy
- 方向二的 eager registration 作为并发场景子模块（预注册到统一 index）
- 方向三的增长预测作为长 session 扩展维度
- 论文：Agent trace 揭示 gap → value-aware unified KV hierarchy → vLLM 原型 → 量化收益

**路径 2（方向二为主，方向一为辅）**：
- 方向二做调度时机的长 prefix 同批复用
- 方向一的 unified index 作为 eager registration 的承载底座
- 论文：两范式调度时机分析 → 预测性 prefix 注册 → 原型 → 量化收益
- 风险：收益天花板受 L1_shared 限制，需论证场景普适性

---

## 待确认的关键问题

1. **改 vLLM 源码的接受度**：之前实验坚持不改源码，但系统论文几乎必然需要修改过的原型。方向一必须改 `block_pool.py` 和 hash table。
2. **时间/会议约束**：奔着具体 deadline（OSDI/SOSP/ASPLOS/EuroSys）还是长周期？决定原型深度。
3. **S4 的差异化是否够强**：方向一的核心论点是"比 SGLang 强"，全靠 S4（统一树也保不住 L0）。这个发现需要更扎实的复现和理论解释——为什么统一树在压力下也失效？
4. **价值标记用显式还是隐式**：显式（Agent API 配合）更准但需改 Agent 框架；隐式（hash 频率推断）更通用但可能不准。这影响原型的部署难度和论文的 generality 卖点。
