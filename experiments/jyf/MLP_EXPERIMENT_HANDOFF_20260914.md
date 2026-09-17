# AgentKV MLP 实验与讨论交接总结

更新时间：2026-09-14

本文档用于在新会话中恢复上下文。当前实验已迁移到：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf`

脚本目录：

`/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/jyf`

## 1. 核心问题与目前结论

目标是预测一个可复用 prefix/node 下一次何时被请求，并把预测接入多用户、KV 容量紧张的 serving，用于 eviction。

当前最重要的结论如下。

1. **只看 prefix 自身历史，确实能预测下一次复用的大致时间尺度，但不能证明能精确预测到逐节点顺序。**
   - request-log 离线实验中，history/gap 特征明显优于仅总体分布或 radix 形状；加入 tool 信息还有提升。
   - 将预测分布压成条件中位数后，`within 2x` 约 78%，但 Spearman 约 0.407，说明精确排序能力有限。
   - 因此模型输出应保留为生存分布/窗口概率，而不是把一个点估计当作精确到达时间。

2. **推荐 K=10 的离散时间 hazard MLP。**
   - request-log 的秒级桶为：`[0,2), [2,5), [5,10), [10,20), [20,60), [60,180), [180,600), [600,1800), [1800,7200), [7200,+inf)`。
   - K=5 太粗；K=20 没有稳定收益，数据稀疏时还更难校准。

3. **时间流逝后优先用条件 Shift，不必默认重新推理。**
   - 初始模型给出生存曲线 `S(t)`；节点已经存活到 age 后，未来 horizon 内复用概率为 `1-S(age+h)/S(age)`。
   - age=20s、K=10 时，Shift 与 age-aware Re-predict 很接近，且都远好于完全不更新时间条件的 Static。
   - 现有证据支持“一次预测 + 随 age 条件化”；是否在线周期性重跑网络，应等 serving 证据证明收益。

4. **桶内插值推荐 log-survival，但它不是主要误差来源。**
   - log-survival 略优于 linear-survival，right-step 明显较差。
   - age=20s、horizon=20s 时实际 KM 风险约 8.05%，log 仅预测 2.75%；这里主要是模型/桶端点低估，不是插值形式造成的。

5. **cold node 必须处理，但不建议把 cold/warm 拆成两个 MLP。**
   - 真实 frozen frontier 中，cold 在实际 LRU victims 中按 node 约 77.5%、按 token 约 96.6%，不是小众情况。
   - cold-only 简单模型可得到强信号，但统一模型在完整分布任务上整体优于 shared trunk + cold/warm heads。
   - 推荐一个统一 MLP，显式输入 `is_cold`、history mask、gap-present 等；cold 时历史特征置零并由 mask 区分“缺失”和真实 0。

6. **真正面向 eviction 的特征，应同时使用 wall-clock seconds 和 traffic/event counts。**
   - frontier 实验中 `idle_seconds`、gap seconds 很强，event count 也有互补信息。
   - 推荐的候选约 16 维，包括 node/path tokens、age/idle 的 event 与 seconds 两套尺度、LRU position、hits、gap mask、最近 gap/EWMA/std、workload 类型。

7. **模型已经在 serving replay 中超过 LRU。**
   - On-demand MLP 相比 LRU，missed prompt tokens 降约 27.7%；precompute 降约 29.1%。
   - On-demand 吞吐和中位延迟更好；precompute eviction 延迟和 E2E 尾延迟较好，但预测量约放大 6.18 倍，仍有优化空间。

## 2. 四套数据口径——不要混用指标

| 数据口径 | 样本对象 | 时间标签 | 主要用途 |
|---|---|---|---|
| Request-log logical prefix | JSONL 每条 request 的消息边界 prefix | request start 到下一次相同 prefix 的 request start，秒 | 验证 prefix 自身历史是否有信号；研究分桶、删失、Shift、校准 |
| Frozen runtime frontier | server 每次 eviction 时 frontier 中的 node exposure | 距离未来 demand 的 cache-access event 数 | cold 比例、cold/warm 策略、frontier 特征消融 |
| Frontier wall-clock | 同一真实 frontier exposure | 当前 frontier wall time 到下一次 demand wall time，秒 | 训练真正面向 serving 的时间 hazard MLP |
| Online serving replay | DSV4 TP8 实际服务与压力流量 | KV hit/miss、TTFT、E2E、吞吐、eviction latency | 最终比较 LRU、On-demand、Precompute |

早期 request-log prefix 不是 server 的真实 radix-tree node；它适合证明“历史行为是否有预测信号”，不能直接代替 eviction frontier 结果。

## 3. 原始数据与 prefix 构造

### 3.1 原始 request 数据

`/share/dai-sys/zhoulongsheng/agentkv/third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl`

- 16,559 条有效 requests，1 条 malformed。
- 原始时间跨度约 122,444.72 秒，约 34 小时。
- 时间流量具有明显 burst/hourly replay 结构，不是连续平稳生产流量。

### 3.2 离线 logical prefix 的构造逻辑

代码：

`/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/jyf/mlp_reuse_offline.py`

输出：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/mlp_exp/data/prefix_reuse_samples.npz`

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/mlp_exp/data/prefix_reuse_samples.meta.json`

构造步骤：

1. 读取整个 JSONL；按 `model + tools` 构造 scope。
2. 对每条 message 做稳定 hash，并从第一条 user message 开始逐消息滚动 hash。
3. 每个 message boundary 形成一个 logical prefix；完全相同的内容链才视作同一 prefix。
4. 对同一个 prefix 的相邻出现，记录 `gap = current_request_start - previous_request_start`。
5. 前一次 pending 样本在再次出现时标为 observed event；最后一次出现如果到 trace 结束仍未再出现，则标为 right-censored。
6. 以首个 user 上下文对应的 anchor 做 train/val/test split，尽量避免同一轨迹泄漏。

样本统计：

- logical prefixes：210,719。
- 总 samples：373,228。
- `history >= 1` 的 warm eligible samples：162,509。
- 其中 observed：83,223。
- eligible train/val/test：114,580 / 24,143 / 23,786。
- test 中 observed 12,019，right-censored 11,767。

局限：

- 标签是 request-start → next request-start，不是严格的 `unlock → next_hit`。
- 不是 tokenizer/radix tree 的真实 node；token 数用字符数近似。
- 每个 request 会产生多个 message-boundary prefix，同一 request gap 会复制到多个 prefix。
- tenant ID 未进入 prefix hash，内容完全相同的跨租户请求可能碰在一起。
- trace 结束统一作为 censor endpoint，会产生较长的删失时间。
- NPZ 包含 `history=0` 的 cold 样本，但早期 standalone 训练和校准主动筛掉了它们。
- meta 文件中的旧 `output` 字段可能仍记录迁移前路径；以上新路径是当前 canonical location。

## 4. MLP 输入、输出与删失 loss

### 4.1 早期 standalone MLP

输入共 30 维，主要包括：

- 最近 8 次 reuse gaps 的 `log1p` 值和有效 mask。
- gap mean/std/min/max/EWMA。
- 历史 reuse count。
- trajectory request count、连续增长轮数。
- 最近 prefix growth、新增 tokens。
- 当前 path/prefix length。

网络：`30 -> 128 -> 128 -> 9 hazards`。9 个 hazard 边界加最后 tail，形成 K=10 个时间桶。

Initial 模型只看 unlock/request 时刻特征；Landmark 模型额外输入 `log(age)`，用多个 landmark 展开样本并预测剩余时间。

### 4.2 离散 hazard loss 与 right censoring

每个输出 `h_k` 表示“已经存活到桶 k 开头时，在桶 k 内发生 reuse 的条件概率”。生存概率为：

`S(t_k) = product_{j<k}(1-h_j)`。

- observed event：loss 包括此前各桶“未发生”的概率，以及事件桶“发生”的概率。
- right-censored：只要求在已观察到的 censor time 之前不发生；censor 后不施加“永不复用”标签。
- censor 落在桶内部时，需要根据桶内生存曲线计算 partial exposure；当前训练实现使用 log-survival 插值。

所以右删失样本会参与训练，但它只提供“至少活到这里”的信息。若错误地把它直接标成永不复用，会让模型过度保守；如果把所有删失样本删除，只保留较快返回的 observed 样本，则会造成 selection bias，通常高估近期复用、低估长尾等待时间对应的生存概率。正确做法是 censor-aware survival likelihood。

## 5. 已完成实验清单

### 实验 A：Standalone Prefix Reuse MLP、分桶与时间更新策略

目录：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/mlp_exp`

主报告：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/mlp_exp/final_report.md`

启动脚本：

`/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/jyf/run_standalone_mlp_exp.sh`

模型权重：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/mlp_exp/runs/20260910_standalone_prefix_v1/k10/seed_41/{initial.pt,landmark.pt}`

另外还有 seed 42、43 对应目录。

目的：

- 验证只依赖 prefix 自身历史能否预测 reuse interval。
- 比较 K=5/K=10/K=20。
- 比较 Static、Shift、Re-predict。

方法：

- Static：age 增加后仍直接使用最初的未来窗口概率，没有条件化。
- Shift：不重跑网络，根据初始 `S(t)` 计算 `P(T<=age+h | T>age)=1-S(age+h)/S(age)`。
- Re-predict：将 age 和状态送入 Landmark MLP，重新预测 residual distribution。

关键 K=10 结果：

| age | 方法 | token-Brier | token-NLL |
|---:|---|---:|---:|
| 5s | Static | 0.22160 | — |
| 5s | Shift | 0.21099 | — |
| 5s | Re-predict | 0.20271 | — |
| 20s | Static | 0.19162 | 0.82103 |
| 20s | Shift | 0.07462 | 0.47367 |
| 20s | Re-predict | 0.07170 | 0.42477 |

K=20、age=20s 时 Shift 0.07169，Re-predict 0.07267，说明更细桶和重推理没有稳定优势。

结论：采用 K=10；优先 Initial + Shift。Re-predict 在部分点略好，但不足以支持在线反复 inference 的复杂度。

### 实验 B：Hazard 曲线与 Shift 可视化

目录：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/mlp_exp/hazard_curve_exp`

报告：`conclusion_zh.md`；脚本：`run_hazard_curve_exp.py`。

目的：解释离散 hazards 如何组成 survival curve，以及 age 增加后条件分布如何右移。

结论：Shift 不是简单移动 bucket index，也不是保留过期桶概率；它是在“已经等到 age 仍未复用”的条件下重新归一化生存分布。K=10 在表达能力与样本量之间较合适。

### 实验 C：桶内插值与条件窗口概率校准

目录：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/mlp_exp/insection_calibration`

主要文件：

- `run_insection_calibration.py`
- `run_dense_window_calibration.py`
- `run_long_window_calibration.py`
- `make_age_horizon_tables.py`
- `age_horizon_calibration_tables_zh.md`

目的：MLP 只在 bucket edges 给出 survival，验证在桶内查询任意 `age`、`age+horizon` 时该如何插值，并检查窗口概率校准。

比较方法：

- Log：对 `log S(t)` 线性插值，等价于桶内 constant hazard rate。
- Linear：直接对 `S(t)` 线性插值。
- Step：在整个桶内维持左端 survival，到右边界跳变。

聚合结果：

| 指标 | Log | Linear | Step |
|---|---:|---:|---:|
| interior ECE | 0.03992 | 0.04069 | 0.06160 |
| conditional-window ECE | 0.01529 | 0.01537 | 0.01799 |

具体例子：age=20s、horizon=20s。

1. test 共有 23,786 个 warm samples。
2. 选择 `duration > 20s`，即到 20s 仍未复用、仍在 risk set 的 12,616 个样本。
3. 其中 754 个 observed event 在未来 20s 内发生；202 个在未来窗口结束前被 censor；可直接确定二元结果的样本为 12,414。
4. age=20 是 bucket edge，end=40 位于 `[20,60)` 的中点。
5. Log 用 `S(40)=S(20)*(1-h_[20,60])^(20/40)`；预测窗口概率为 `1-S(40)/S(20)`。
6. Linear 在该桶内按 1/2 线性消耗边界概率；Step 在到达 60s 前不给该桶事件概率。
7. 真实参照不是简单比例，而是对 residual durations 做 censor-aware Kaplan-Meier，再得到 `1-S_KM(20)`；token-weighted 值约 8.052%。

该点结果：Log 2.75%、Linear 2.68%、Step 0；对应 ECE 约 0.0536、0.0543、0.0809。Log/Linear 接近，二者都低估，说明主要问题是模型端点/数据分布，不是插值。

KM 的作用：KM 本来估计生存函数；实验先估计 residual survival `S_KM(h)`，再把未来 horizon 内累计复用风险定义为 `1-S_KM(h)`。censored 样本在 censor 时刻退出 risk set，不算 event。

注意：训练时 partial-censor loss 已使用 log-survival，因此比较并非完全中性，可能轻微偏向 Log。

### 实验 D：Gap 分布来源分析

目录同实验 C。

文件：

- `analyze_gap_origin.py`
- `gap_origin_analysis.json`
- `gap_distribution_analysis_zh.md`

目的：解释为何 age>=60s 的中短 horizon 几乎无正样本，以及这是 builder 造成还是原始数据造成。

结果：

- 原始全局相邻请求绝大多数小于 1s，但存在约一小时的 burst 间隔。
- 同 anchor、从原始 JSONL 重建的 exact prefix、最终 NPZ 中，都没有约 60–3551s 的 observed gap。
- NPZ warm observed：`[20,60)` 4168；`[60,1800)` 0；`[1800,3600)` 2196；`[3600,7200)` 1135；`>=7200` 824。
- test 中 `[20,60)` 785；`[60,1800)` 0；`[1800,3600)` 142；`>=7200` 153。

结论：中间时间段空洞来自原始 trace 的 burst replay 时间戳；prefix builder 会因多个 message boundaries 放大频数，但没有制造 gap 空洞，也没有做 gap scaling/rounding。这限制了长窗口校准结论的生产泛化能力。

### 实验 E：逐样本真实 next-request time 诊断

目录同实验 C；文件名包含 `next_request_time`。

目的：回答“模型预测比例相近，但具体对应节点是否正确”。将 K=10 分布压缩成一个点估计，与 observed true duration 对比。

方法：只使用 observed 且 `T<=7200s` 的 11,866 个样本；删失样本和 153 个 >7200s 的 observed 样本被排除。以“给定 7200s 内会返回”的条件中位数作为 `T_hat`，并比较 Log/Linear/Step。

Token 结果：

| 方法 | MAE | median abs error | log1p error | within 2x | within 4x |
|---|---:|---:|---:|---:|---:|
| Log median | 25.40s | 2.35s | 0.5037 | 78.21% | 97.55% |
| Linear median | 25.59s | 2.35s | — | 78.01% | — |
| Step median | 45.21s | 3.54s | — | 64.91% | — |

- exact bucket accuracy 约 40.46%，允许相邻桶约 86.78%。
- 时间排序相关性 Spearman 约 0.407；当前实现实际上是 unweighted rank correlation。
- 条件均值点估计很差：MAE 47.11s、median abs error 28.51s、within 2x 24.62%。

结论：条件中位数可粗略表示时间尺度，但逐节点精确排序仍弱。此实验排除了 censor，存在 selection bias，只是诊断；正式评价仍应使用 survival NLL/Brier/calibration 和最终 serving 指标。

目录中的 `node_level_*`、`node_selection_*`、`oracle_*` 是早期对“oracle”含义理解偏差后做的 victim/selection 诊断，不应作为主结论。用户所说 oracle 是数据里的真实下一次请求时间，即上述 observed duration。

### 实验 F：Cold frontier 比例与 cold predictor

目录：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/cold_predictor_exp`

报告：`final_report.md`。

数据：held-out `agent_050`，533 sessions / 2000 turns，约 50% OpenHands；DSV4 Flash TP8 的 frozen frontier trace。分析 5,102 次 eviction、6,945 个 victims（单个 TP rank）。

Cold 定义：node 自插入后没有发生过 genuine prefix match/hit。

Cold 比例：

| 位置 | node 比例 | token 比例 |
|---|---:|---:|
| Full frontier exposure | 98.67% | 98.08% |
| SWA frontier exposure | 42.32% | 88.75% |
| 实际 LRU victims | 77.54% | 96.62% |

这里的 full/SWA 是 server 内两类 eviction frontier/缓存区域的统计口径，不是说“模型的 full-attention node 天然永远不复用”。用户此前关心的关键数应看 actual victims，而不仅是所有 frontier exposure。

预测目标为未来 5/20/100 个 cache-access events 内是否 demand，不是 5/20/100 秒。

Cold-only logistic：

| horizon | AUC | token-Brier | Top-10% recall |
|---:|---:|---:|---:|
| 5 events | 0.9026 | 0.01436 | 0.8095 |
| 20 events | 0.8785 | 0.02471 | 0.7523 |
| 100 events | 0.9134 | 0.08788 | 0.4839 |

早期 unified MLP 在这个特定 binary/cold 对比上短 horizon 较差，但后续完整统一分布实验整体优于拆 heads。结论是 cold 有可预测信号且不能统一置零，不是必须维护两个网络。

### 实验 G：Unified MLP vs Shared trunk + Cold/Warm heads

目录：

- `/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/unified_mlp`
- `/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/shared_and_heads`

启动脚本：

- `/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/jyf/run_shared_vs_unified.sh`
- `/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/jyf/run_shared_vs_unified_k10.sh`

数据：完整 frozen frontier，2000 turns / 533 sessions；按 prefix digest 切分。

Fixed-horizon binary 结果：

| horizon | Unified AUC | Heads AUC | Unified Brier | Heads Brier |
|---:|---:|---:|---:|---:|
| 5 | 0.8812 | 0.8663 | 0.13373 | 0.14219 |
| 20 | 0.8823 | 0.8758 | — | — |
| 100 | 0.9030 | 0.8938 | — | — |

K10 event-distance distribution buckets：`(0,1], (1,2], (2,5], (5,10], (10,20], (20,50], (50,100], (100,200], (200,500], (500,+inf)`。

| 指标 | Unified | Heads |
|---|---:|---:|
| exact bucket accuracy | 0.3551 | 0.3177 |
| token Brier | 0.7958 | 0.8131 |
| exact NLL | 1.7891 | 1.8789 |
| censor NLL | 1.2803 | 1.3440 |

结论：推荐统一网络 + cold/history masks。拆 head 使每个 head 数据更少，warm 上尤其不稳定，没有得到一致收益。

### 实验 H：特征消融

目录：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/feature_exp`

#### H1. Request-log message-boundary 特征

报告：`conclusion_zh.md`。

主要结果：

- population-only NLL 1.5332。
- recent gaps NLL 1.4586，AUC@5 0.6912。
- history statistics NLL 1.4508，AUC@5 0.6989。
- radix shape AUC 约 0.501，几乎无信号。
- tools size/schema NLL 1.5092，AUC@5 0.6734。
- history + tool size NLL 1.4251，AUC@5 0.7470。
- history + tool names NLL 1.4284，AUC@5/20/60 = 0.7499/0.6853/0.6835。

结论：历史 gap/reuse 特征是基础，tool 信息有额外信号；静态 radix shape 在此构造中没有价值。建议 12 维核心历史特征，可选 tool hash/name embedding。

#### H2. 真实 frontier 的 event-distance 特征

报告：`frontier_ablation_conclusion_zh.md`。

数据：692 个 frontiers、29,885 exposures；去掉 3,100 个 left-truncated 后 26,785 个，1,652 digests。目标为未来 5/20/100 events。

推荐 new11：node/path tokens、age/idle events、LRU fraction、hits、gap-present、recent gap events、gap EWMA/std、is_openhands。

| 指标 | Original16 | New11 |
|---|---:|---:|
| NLL@5 | 0.43132 | 0.36511 |
| AUC@5 | 0.8708 | 0.9103 |
| NLL@20 | 0.43420 | 0.38934 |
| AUC@20 | 0.8803 | 0.9017 |
| NLL@100 | 0.40850 | 0.36430 |
| AUC@100 | 0.8882 | 0.9103 |

结论：保留 history、gap-present、size、LRU position、traffic；删除冗余 depth/is_request/is_cold 组合。parent/sibling 特征未稳定提升；owner_turn 只局部帮助 cold。

#### H3. 真实 frontier 的 wall-clock time hazard

报告：`time_hazard_conclusion_zh.md`。

推荐 `both_candidate16`：同时包含 age/idle/gap 的 seconds 与 event counts，加 node/path tokens、LRU、hits、gap mask、is_openhands。

| 特征 | censor NLL | AUC@5s | AUC@20s | AUC@60s |
|---|---:|---:|---:|---:|
| original16 | 1.25458 | 0.8677 | 0.8748 | 0.8667 |
| time_candidate11 | 0.99402 | 0.9369 | 0.9351 | 0.9209 |
| both_candidate16 | 0.92690 | 0.9528 | 0.9510 | 0.9305 |

结论：wall-clock seconds 是最重要改进，event count 提供流量强度归一化后的互补信息。下一版 serving predictor 应基于此数据，而不是继续只用 request-log logical prefixes。

### 实验 I：异步预测原型（已归档/不作为最终结论）

目录：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/nn_exp/useless/async_exp`

早期 CPU microbenchmark 显示 request-end 同步预测开销高，异步提交可显著降低 hook 延迟；但旧 online run 使用 event-distance 模型、每次最多 16 candidates 且 fallback 很多，模型实际使用率低于 8%，因此不能判断最终策略优劣。后续 full-frontier serving 实验已取代这组结果。

### 实验 J：真实 serving eviction 位置与推理时机

目录：

`/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/evict_position`

报告：`conclusion_zh.md`。

模型：`training/model.pt`，unified 16 features，固定 24 维输入，2×128 hidden，K10 hazards；训练目标为 frozen frontier 到下一次 demand 的 wall-clock 时间，包含 cold 与 censor。seed 42 val NLL 约 0.942261。

Serving 配置：DSV4 Flash TP8、FP8 KV、`--mem-fraction-static 0.45`、KV capacity 705,280 tokens、page 256、chunked prefill 8192、decode 32。每个策略 3 次顺序平衡重复；每次 1,970 requests / 572 sessions；总计 17,730 successful requests，0 API error。

| 指标（3 次均值） | LRU | On-demand MLP | Precompute MLP |
|---|---:|---:|---:|
| token hit rate | 91.817% | 94.084% | 94.202% |
| missed prompt tokens | 3,317,924 | 2,398,713 | 2,350,841 |
| TTFT p50 | 503 ms | 481 ms | 521 ms |
| TTFT p99 | 5969 ms | 3590 ms | 4018 ms |
| E2E p50 | 1305 ms | 1232 ms | 1300 ms |
| E2E p99 | 10499 ms | 9039 ms | 8092 ms |
| throughput | 4.752 req/s | 5.137 req/s | 5.016 req/s |
| eviction p50 | 4.155 ms | 9.616 ms | 5.757 ms |
| request-end p50 | 0.189 ms | 0.178 ms | 0.688 ms |

- On-demand missed tokens 相比 LRU 减少约 27.7%。
- Precompute 减少约 29.1%。
- Precompute 的 eviction p50 比 On-demand 低约 40.1%，E2E p99 最好；但吞吐比 On-demand 低约 2.4%。
- Precompute 提交的 node predictions 约为 On-demand 的 6.18 倍，只有约 17.3% 在 request-end；当前 broad refresh 仍浪费计算。

结论：两种 MLP serving 策略都超过 LRU。当前默认可选 On-demand；若关注 eviction stall/E2E tail，再优化 dirty-node selective precompute 后复测。

## 6. 指标解释

- **NLL**：预测分布对真实 observed/censored outcome 的负对数似然，越低越好。survival NLL 可正确利用右删失。
- **Brier**：预测窗口概率和真实二元结果的平方误差，越低越好。`token-Brier` 按 node token 数加权，更贴近 KV 容量成本。
- **ECE**：把预测概率分箱，比较每箱平均预测概率与实际 KM 风险，再按样本/token 权重平均绝对差。越低越校准，但在几乎没有正样本的区域，低 ECE 不等于模型有区分能力。
- **AUC**：排序一个 horizon 内会复用和不会复用样本的能力，不评价概率数值是否校准。
- **KM risk**：Kaplan-Meier 先估计 censor-aware survival，再用 `1-S_KM(h)` 得到 horizon 内累计事件概率；不是瞬时 hazard。
- **Spearman**：预测时间与真实时间的秩相关，1 表示排序完全一致，0 表示无单调关系。现有约 0.407 只是中等偏弱。
- **Evicted-then-soon-reused**：最终 serving 应补充的“后悔型驱逐”指标，例如 eviction 后 5/20/60s 内又被复用的 token 比例。

## 7. 已完成的路径迁移修改

以下脚本中的旧实验目录已更新到 `/experiments/jyf`：

- `run_standalone_mlp_exp.sh` → `experiments/jyf/nn_exp/mlp_exp`
- `run_cold_frontier_collection.sh` → `experiments/jyf/nn_exp/cold_predictor_exp`
- `run_frozen_cold_frontier.sh` → 同上
- `wait_and_run_cold_frontier.sh` → 同上
- `run_shared_vs_unified.sh` → cold/unified/shared 三个新目录
- `run_shared_vs_unified_k10.sh` → cold/unified/shared 三个新目录
- `info.md` → standalone data 新目录

新统一目录名使用 `unified_mlp`，替代迁移前脚本中的 `uniform_mlp_exp`。

所有 6 个修改过的 shell 脚本均通过 `bash -n`。脚本目录中已无以下旧引用：

- `experiments/mlp_exp`
- `experiments/nn_exp/cold_predictor_exp`
- `experiments/nn_exp/uniform_mlp_exp`
- `experiments/nn_exp/shared_and_heads`

`experiments/sglang_kv_cache/dsv4_vanilla_lru` 仍保留，因为它不是本次已确认迁移的 MLP 实验目录，旧目标也仍存在。

## 8. 当前系统设计建议

### 离线训练

1. 以真实 server frontier exposure 为训练样本，而不是只用 logical message prefix。
2. 标签为当前可驱逐时刻到下一次真实 demand 的 wall-clock time；trace 结束或 node 生命周期结束正确做 right censoring。
3. 同时保存 event-distance，作为 traffic-intensity 辅助尺度。
4. 统一 K10 hazard MLP；cold/warm 共享网络，输入 masks。
5. 特征使用 both_candidate16；进行按 session/tenant/time 的严格 split，避免 digest 重复泄漏。
6. 用 censor NLL 训练；报告 token-weighted Brier/NLL、age×horizon KM calibration、AUC 和 exact-time ranking 作为诊断。

### 在线 serving

1. node 创建或历史状态发生实质变化时推理，缓存 edge survival/hazards。
2. eviction 时用当前 age 对 survival 做 conditional Shift；桶内默认 log-survival 插值。
3. eviction score 同时考虑近期复用概率、node tokens、重算成本、SWA/full pool 限制和 fairness，而不是仅按预测时间点排序。
4. cold node 通过统一模型的 cold mask 进入排序，不能直接当“永不复用”。
5. 初版采用 On-demand；后续仅对 dirty/high-value frontier 节点做 selective precompute。

### 最终评价

必须在相同请求流量、KV 容量、随机种子和运行顺序下比较：LRU、Oracle next-demand、MLP On-demand、MLP Precompute。核心指标为 token hit rate、missed/recomputed prompt tokens、evicted-then-soon-reused tokens、TTFT/E2E、throughput 和 predictor/eviction overhead。

## 9. 尚未完全解决的问题

1. request-log 数据有 60–1800s 的天然空洞，需在更连续、更接近生产的多日 trace 上复验校准。
2. logical prefix 构造没有 tenant ID、真实 tokenizer node 和 unlock timestamp；下一轮应直接导出 server node lifecycle。
3. age=20s 的 `[20,40]` 风险明显低估，需要区分模型端点误差、训练分布偏移和特征不足。
4. cold 定义与 node merge/split/压缩生命周期需要在 server 实现中统一。
5. exact-time Spearman 当前未 token-weight，且排除 censor；可补 IPCW/concordance index，但不要让点预测替代 survival 指标。
6. 还缺严格的 Oracle next-demand serving replay，用于量化 eviction policy 的理论上界。
7. 还应补 evicted-then-soon-reused@5/20/60s/token 指标。
8. precompute 需要 dirty-node 选择、版本检查、队列过载 fallback 和批量 inference 优化。

## 10. 新会话可直接粘贴的短上下文

> 项目是 AgentKV 的 reuse-time MLP 与 KV eviction。实验根目录已迁移到 `/share/dai-sys/zhoulongsheng/agentkv/experiments/jyf`，脚本在 `/share/dai-sys/zhoulongsheng/agentkv/scripts/shell/jyf`。早期 request-log logical-prefix 实验表明历史 gap/reuse 和 tool 特征能预测粗粒度复用时间；推荐 K10 discrete-hazard MLP、censor-aware loss、一次 Initial 推理后按 `1-S(age+h)/S(age)` 做 conditional Shift。log-survival 桶内插值略优于 linear，step 较差，但 age20/h20 的主要问题是模型低估（KM 8.05%，log 2.75%）。真实 frozen frontier 中 cold 是 actual victim 的 77.54% nodes/96.62% tokens，不能忽略；完整实验支持统一 cold/warm MLP + masks，而不是拆 heads。真实 frontier 特征实验推荐 seconds + event counts 的 both_candidate16，censor NLL 0.9269、AUC@5/20/60s 0.9528/0.9510/0.9305。真实 serving 3×重复中，LRU/On-demand/Precompute token hit 为 91.817/94.084/94.202%，missed tokens 为 3.318M/2.399M/2.351M；On-demand 吞吐最好，Precompute eviction 和 E2E tail 较好但预测量 6.18×。下一步应以真实 frontier wall-clock labels 训练统一 K10 模型，补 Oracle next-demand replay、后悔型驱逐指标和 selective precompute。
