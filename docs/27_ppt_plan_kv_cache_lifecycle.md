# PPT 规划：KV Cache 的生命周期与管理

> 日期: 2026-06-30
> 目的: 写一份 PPT，理清并展示 KV cache 在 serving 系统中是怎么管理的
> 主线: "一个 KV block 的一生"——用生命周期时间轴作主线，不按 P1/P2/P6 痛点罗列
> 关联: `docs/26_cache_management_framework.md`（cache 管理全链框架）

---

## 0. PPT 的核心目标

让听众（也包含自己）顺着 cache 的生命周期看清楚一件事：

> 一个 block 从生到死经历了什么，现有系统在每个节点怎么决策，agent 场景下这个决策为什么有问题。

**不要**把所有细节堆上去，也**不要**按痛点编号罗列（那是论文 appendices 的写法）。PPT 要讲"故事流"——用生命周期作主线，痛点挂在时间轴的对应节点上。

---

## 1. 推荐结构

### 第一部分：建立"cache 管理是什么"的心智模型

不要一上来讲痛点。先用 1-2 页让听众知道 KV cache 在 serving 里是被谁、怎么管的。画一张架构图：

```
请求到达 → Scheduler → [Cache Index 查找] → 命中？
                                    ├─ 是 → 复用已有 KV，只 prefill 新增部分
                                    └─ 否 → 全量 prefill，写入 Cache Index

容量不足时 → [驱逐决策] → 腾出空间
跨层时    → [GPU ⇄ CPU ⇄ SSD 三级移动]
```

> ⚠️ **事实校正（2026-06-30 源码确认）**：KV cache 是**三级**架构，不是两级。vLLM 和 SGLang 都支持 SSD/disk 作为第三层：
> - **vLLM**：GPU → CPU(primary) → SSD(secondary)，`FileSystemTierManager`（`vllm/v1/kv_offload/tiering/fs/manager.py:62`），`O_DIRECT` 写磁盘 `.bin` 文件，`TieringOffloadingManager`（`manager.py:111`）编排。已实现 + 真实磁盘单测 + 官方文档（2026-01-08 博客），无 experimental 标注。
> - **SGLang**：L1(GPU) → L2(CPU) → L3(storage)，`HiCacheFile`（`hicache_storage.py:319`）+ `LRUFileEvictor`，生产可走 nixl(GDS)/3FS/mooncake。比 vLLM 更成熟。
>
> **一个易混点**：vLLM 的 `cpu_offload_gb` 是**模型权重** offload（UVA），与 KV cache 的 CPU/SSD tier 完全无关。我们 P6 测的"offload load=0"是 KV cache 的 CPU 层，不是 `cpu_offload_gb`。PPT 讲跨层时必须澄清，否则听众会混。

- 标清楚：index、查找、写入、驱逐、跨层 这几个组件的位置
- 这就是 `docs/26` 里那条链的图示化
- 这部分要回答：serving 系统"管理" cache 到底管什么——答案就是图上那几个决策点

### 第二部分：主线——一个 block 的生命周期（PPT 主体）

用横向时间轴讲一个 block 从产生到消失。每一步对应链上一个环节，每步讲三件事：

> 这一步做什么 / 现有系统怎么做 / agent 场景下的问题

**① 注册（出生）**
- 做什么：prefill 算出的 KV 写进 cache index
- 现状：被动注册，算完才写；按 block 对齐（vLLM 16 tok 一块，尾块浪费）
- agent 问题：L0/L1_shared 是可预知内容，为什么要等算完才注册？

**② 查找/命中（被使用）**
- 做什么：新请求来，在 index 里找已有 prefix
- 现状：block hash 链式匹配，遇发散点全 miss
- agent 问题：并发时同批请求看不到彼此正在算的 prefix（P1）；SGLang in-batch 阈值 32 tok 对 agent L1 失效

**③ 跨层移动（搬家）**
- 做什么：GPU 满了把 block 搬到 CPU，CPU 满了再搬到 SSD，需要时逐级搬回
- 现状：**三级**架构 GPU → CPU → SSD；机械 LRU 搬运，各级独立淘汰
- agent 问题：搬的不分死活、不分内容价值，offload 形同虚设，load=0（P6）
- ⚠️ **实测范围**：我们 P6 只测了 GPU↔CPU 这两级（load=0），**SSD 层未测**。CPU↔SSD 之间是否也有独立 LRU 不协调，尚未确认——这是 PPT 里要诚实标注的空白

**④ 驱逐（死亡，被动）**
- 做什么：容量不够时决定谁走
- 现状：LRU 按时间，或 SGLang 叶子优先按树结构
- agent 问题：判据里没有价值信息，L0 被无脑驱逐（P2）；SGLang 统一树压力下也保不住（S4）

**⑤ 生命周期（真正的死亡，缺失）**
- 做什么：block 什么时候该彻底失效
- 现状：没有显式生命周期，靠 LRU 间接淘汰
- agent 问题：session 结束 block 本该立刻失效，系统不知道，垃圾滞留

**视觉要求**：五步用一条横向时间轴串起来，每步下面挂"现状 + agent 问题"。听众一眼能看到：驱逐（④）只是其中一环，前面环节失管才把问题堆到驱逐爆发。这个视觉冲击比文字说"驱逐不是唯一问题"强得多。

### 第三部分：问题的根——判据缺失（题眼）

讲完五步，用一页总结把所有 agent 问题归到一个根上：

> 现有系统每个决策点的判据都是时间或拓扑（last-access、是不是叶子），没有复用价值。

对照表：

| 决策点 | 现有判据 | 缺失的判据 |
|--------|---------|-----------|
| 驱逐 | last-access 时间 | 复用价值 |
| 跨层 | last-access 时间 | 复用价值 |
| 生命周期 | last-access 时间（间接） | 复用价值（session 死了→价值归零）|
| 查找 | hash 链 | 语义层级 |

这一页是 PPT 的题眼——把零散的 P1/P2/P5/P6 统一成一个论点：**不是某个环节有 bug，是所有环节共用一个 agent 盲的判据**。直接引出研究方向（复用价值判据）。

### 第四部分：我们的方向（可选）

- 如果 PPT 也要带"接下来做什么"：用 1-2 页承接，核心是引入复用价值作为统一判据，贯穿全链
- **不要展开技术细节**（回看/前看那些还没定的），只点方向
- 如果 PPT 纯粹是"理清 cache 怎么管理"的记录性展示，这部分可不要

---

## 2. 写 PPT 的具体建议

### 2.1 先画图，再写字

PPT 讲 cache 生命周期，图比文字重要。最该花时间的是第二部分那张**横向时间轴**——五步排开，每步挂现状和问题。这张图画清楚了，整个 PPT 的骨架就立住了。

### 2.2 每个环节用"一句话现状 + 一个实测数字"撑住

不要空讲机制。举例：

- 讲驱逐 → 配 P2 的 "5,829 blocks 被驱逐"
- 讲跨层 → 配 P6 的 "load=0"

数字是听众信你的依据，也是自己确认"这事真发生过"的锚点。`docs/26` §2.1 那张表是现成的数字来源。

### 2.3 vLLM 和 SGLang 对照着讲

每个环节尽量给两个系统的做法，体现"两个最佳系统都有问题"。尤其是驱逐那步：

- vLLM：LRU 无差别
- SGLang：叶子优先但压力下也失效（S4 cached=3）

这个对照直接支撑"判据缺失是普遍问题"。

### 2.4 生命周期（⑤）单独标注"未测量"

这是我们推断但还没实测的环节。PPT 里诚实标出来，既严谨，也给自己留一个"接下来要补的实验"的钩子。

### 2.5 别把痛点编号（P1/P2…）当主线

听众不关心内部编号。用"注册/查找/跨层/驱逐/生命周期"这种生命周期语言，P 编号只在括号里作交叉引用。

---

## 3. 关于"理清生命周期"这个私人目标

这份 PPT 是逼自己理清 cache 生命周期的工具。**写之前，先自己用一张白纸把"一个 block 从产生到消失"画一遍，画不出来的地方就是还没理清的地方。**

最可能卡住的点（写 PPT 前必须先在源码层面确认清楚）：

1. **一个 block 在 GPU 被驱逐后，它的 hash 在 index 里还在不在？**
   - vLLM 和 SGLang 答案不同，需分别确认

2. **offload 到 CPU 后，查找时会不会去找 CPU 那份？**
   - 这是 P6 的核心，影响"跨层移动"环节怎么画

3. **session 结束后，它的 block 是立刻被标记失效，还是只是不再被访问、等 LRU 慢慢淘汰？**
   - 这决定"生命周期"环节⑤是画成"有"还是"缺失"

4. **SSD 层（第三级）的行为——CPU 满了 block 怎么到 SSD？查找时会不会回查 SSD？CPU↔SSD 之间是不是也独立 LRU？**
   - 我们只测过 GPU↔CPU，SSD 层完全空白，画 PPT 前必须在源码层面先确认
   - vLLM 关键代码：`vllm/v1/kv_offload/tiering/fs/manager.py`、`tiering/manager.py`（`TieringOffloadingManager` 的 cascade 和 promotion 逻辑）
   - SGLang 关键代码：`hicache_storage.py:319`（`HiCacheFile`）、`hiradix_cache.py`、`cache_controller.py`（`write_buffer`）

这几个点画清楚了，生命周期就真通了，PPT 自然就出来。

---

## 4. 横向时间轴草图（第二部分骨架）

```
一个 KV block 的生命周期
─────────────────────────────────────────────────────────────────────►
        │           │           │           │           │
       注册        查找        跨层        驱逐       生命周期
      (出生)      (被使用)    (搬家)     (被动死亡)  (真死亡·缺失)
        │           │           │           │           │
   prefill算完   新请求来     GPU满      容量不够    session结束
   才写index     查prefix    搬CPU      决定谁走    block该失效
        │           │           │           │           │
   现状:被动    现状:hash链  现状:机械   现状:LRU    现状:无显式
   agent:为啥   agent:并发   agent:不分  agent:判据  agent:垃圾滞留
   不预注册?    不可见(P1)   死活(P6)    无价值(P2)  (未测量)
```

每步下方挂"现状 + agent 问题"，P 编号作交叉引用。vLLM/SGLang 对照可在每步用两列展开。
