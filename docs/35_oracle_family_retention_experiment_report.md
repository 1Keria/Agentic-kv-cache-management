# Oracle Prefix Family 保留实验报告

> 日期：2026-07-17  
> 对应阶段：F0.2 Residual Utility  
> 前序报告：`docs/34_prefix_family_ttft_value_validation_report.md`

## 一、结论摘要

本轮同时完成了 SGLang 引擎闭环和离线策略 replay。

最重要的两组结论是：

1. **已知某个 7.8K Family 未来会被复用时，priority eviction 可以在容量压力下完整保住它。**
   - LRU 与 Priority 全零都在第 6 个独立 10K pressure request 后把 Family 淘汰到只剩 3 tokens；
   - Oracle priority 保留了完整 7,816/7,823-token prefix；
   - 合成 probe TTFT P50 从 236.5 ms 降到 28.4 ms；
   - 真实 Django probe TTFT P50 从 307.3 ms 降到 94.2 ms。

2. **但全局 replay 中，未来信息相对简单 LFU 的 residual utility 很小。**
   - 32K capacity：Oracle 比最强非 Oracle 高 0.235 个百分点；
   - 44K capacity：高 0.373 个百分点；
   - 60K capacity：高 0.544 个百分点。

因此应区分两个判断：

- “保护一个已知高价值 Family 是否有用”：明确有用；
- “复杂 Family value model 是否显著优于简单频率/共享度信号”：目前证据偏弱。

当前判断是 **Pivot/Inconclusive，而不是直接 Go**：继续做轻量 prefix value metadata 和更真实的多轮 replay，但暂不投入复杂 Family predictor。

---

## 二、SGLang 引擎实验

### 2.1 固定配置

| 项目 | 配置 |
|---|---|
| 模型 | Qwen3-8B |
| GPU | 单 NVIDIA H800 |
| KV 配额 | `mem-fraction-static=0.3`，约 59,902 tokens |
| 调度 | FCFS，所有请求严格串行 |
| Priority scheduling | 开启，默认值 0 |
| Pressure | N 个独立约 10K prompt，`max_tokens=1` |
| 重复 | 正式 arm 每场景 5 轮，另丢弃 1 轮预热 |

严格串行请求用于排除 queue scheduling 的影响，使 priority 只通过 Radix eviction 产生作用。

### 2.2 三个 Arm

```text
A0 LRU
   radix_eviction_policy=lru
   family_priority=0
   noise_priority=0

A1 Priority-Zero
   radix_eviction_policy=priority
   family_priority=0
   noise_priority=0

A2 Priority-Oracle
   radix_eviction_policy=priority
   warm Family priority=100
   baseline probe/noise priority=0
```

A1 在所有节点 priority 相同时退化为 LRU tie-break，用来判断收益究竟来自 eviction policy，还是来自 Oracle Family 标签。

### 2.3 Post-pressure 协议

```text
flush
  → warm Family
  → baseline probe，确认 shared prefix
  → N 个固定、互不共享的 10K pressure requests
  → post-pressure probe
```

关键修正：只有 warm Family 获得 100 priority。baseline probe 使用 0，避免把 probe 的独有 suffix 也错误保护。

---

## 三、驱逐临界点

在 LRU 下扫描 4–7 个 pressure requests：

| Pressure 数量 | Post-pressure cached tokens | Family 驻留 |
|---:|---:|---:|
| 4 | 7,948 | 完整 |
| 5 | 7,948 | 完整 |
| 6 | 3 | 基本完全淘汰 |
| 7 | 3 | 基本完全淘汰 |

第 6 个 10K pressure request 是稳定的离散驱逐临界点，因此正式三臂对照固定为 N=6。

该边界与约 60K KV 容量一致：

```text
Family 路径约 8K
6 × 10K noise
总量约 68K > 59.9K
```

---

## 四、合成 7,808-token Family

目标共享 prefix 在 SGLang chat template 后为 7,816 cached tokens。

| Arm | Cached P50 | Family 完整驻留率 | TTFT P50 | 100ms SLO 违约率 |
|---|---:|---:|---:|---:|
| LRU | 3 | 0% | 236.5 ms | 100% |
| Priority-Zero | 3 | 0% | 241.3 ms | 100% |
| Priority-Oracle | 7,816 | 100% | 28.4 ms | 0% |

Oracle 相对 LRU：

```text
TTFT P50 saving = 236.516 - 28.434 = 208.082 ms
```

Priority-Zero 与 LRU 的驻留结果完全一致，说明 Oracle arm 的收益来自 Family priority 标签，而不是单纯切换 eviction implementation。

---

## 五、真实 Astropy → Django Family

真实请求：

```text
warm:  swebench__astropy__astropy-12907__minimax
probe: swebench__django__django-10097__minimax
exact shared prefix: 7,823 tokens
```

| Arm | Cached P50 | Family 完整驻留率 | TTFT P50 | 100ms / 200ms 违约率 |
|---|---:|---:|---:|---:|
| LRU | 3 | 0% | 307.3 ms | 100% / 100% |
| Priority-Zero | 3 | 0% | 321.4 ms | 100% / 100% |
| Priority-Oracle | 7,823 | 100% | 94.2 ms | 0% / 0% |

Oracle 相对 LRU：

```text
TTFT P50 saving = 307.265 - 94.244 = 213.021 ms
```

该数值与前一阶段无压力真实 hit/miss 实验的约 213 ms 一致，说明 retention 确实恢复了可预测的 prefill 收益。

### 5.1 过度保护成本

当前 API 只能给整条 request path 赋 priority，不能只提高共享 prefix 节点：

- Astropy warm prompt：8,468 tokens；
- exact Family prefix：7,823 tokens；
- 至少 645 个 Astropy 独有 suffix tokens 被一并提高 priority。

不过 baseline Django probe 使用 priority 0，因此 post-pressure 命中严格等于 7,823，而不是整个 10,073-token Django prompt。当前 TTFT 收益没有被 Django suffix 保护所夸大，但 capacity cost 仍被低估了 645 tokens。

---

## 六、离线 Residual-utility Replay

### 6.1 输入和模型

- 767 个显式 Session 的首请求；
- Qwen chat template；
- 16-token 完整 block；
- 204,846 个 radix nodes；
- dataset order + 3 个固定 shuffle seed；
- capacities：32K、44K、60K tokens；
- 只允许从 resident radix leaf 逐 block 淘汰。

比较策略：

```text
LRU
LFU
SLRU
Observed shared-count + depth
Oracle next-use
```

`Observed shared-count + depth` 只使用已到达请求形成的 holder count，不读取未来；`Oracle next-use` 使用未来请求位置，是理论上界而非可部署策略。

### 6.2 平均 avoided-prefill ratio

| Capacity | LRU | LFU | SLRU | Shared+Depth | Oracle | Oracle - strongest non-oracle |
|---:|---:|---:|---:|---:|---:|---:|
| 32K | 56.348% | 56.506% | 56.460% | 56.481% | 56.740% | +0.235 pp |
| 44K | 56.364% | 56.569% | 56.499% | 56.537% | 56.942% | +0.373 pp |
| 60K | 56.472% | 56.688% | 56.624% | 56.642% | 57.232% | +0.544 pp |

最强非 Oracle 在三个容量下都是 LFU。

### 6.3 如何解释 56% 的高命中

这不是所有策略都很聪明，而是该 trace 存在覆盖大量请求的约 7.8K 公共根路径。一旦公共路径进入 radix tree，即使容量只有 32K，大部分策略也能长期保留它。

因此：

- Family 的主要价值来自“识别并保护少数大公共 prefix”；
- 对这个 clean-prefix workload，频率已经是很强的代理信号；
- Oracle 额外改善的是更细的分支与未来复用顺序，而这部分 token mass 较小。

### 6.4 超长请求审计

部分首请求大于模拟容量：

| Capacity | 超长请求数 |
|---:|---:|
| 32K | 47 |
| 44K | 14 |
| 60K | 1 |

这些请求可以消费当前 resident prefix，但在第一次 miss 后不被 simulator admission。该规则避免构造不可能保持 ancestor closure 的 radix 状态，但与 SGLang chunked prefill 的真实行为并不完全一致。

因此 32K/44K 的策略差异只能作为 sensitivity evidence，不能直接映射为引擎收益。

---

## 七、联合分析

### 7.1 明确通过的部分

**机制正确性**

- request priority 能传播到 Radix node；
- priority eviction 能在容量压力下保留高 priority Family；
- Priority-Zero 与 LRU 的相同结果验证了对照结构。

**服务价值**

- 合成 Family 恢复 208.1 ms TTFT；
- 真实 Family 恢复 213.0 ms TTFT；
- 真实 probe 从 200ms SLO 全部违约变为全部达标。

### 7.2 未通过复杂 Family Go Gate 的原因

离线 replay 中，Oracle next-use 相对 LFU 只增加 0.235–0.544 个百分点 avoided-prefill ratio。当前没有预注册一个低于该范围的 SESOI，因此不能把这一差值解释为足够大的论文级 residual utility。

此外，当前 Oracle arm 本质上是：

```text
trace ground truth
  → request priority=100
  → existing priority eviction
```

它不是完整 PrefixFamilyIndex，也没有：

- Family 动态 value；
- priority 衰减；
- retention TTL；
- prefix-node 级精确标记；
- Session close 后 holder 更新；
- 多 Family 冲突预算。

### 7.3 当前研究判断

| 问题 | 判断 |
|---|---|
| 跨 Session prefix 是否有价值 | Go |
| bounded soft priority 是否能保护它 | Go |
| Family 是否优于 LRU | 对选定 Family 明确 Go |
| Family 是否优于 LFU/shared-count | Inconclusive，增量偏小 |
| 是否立即训练复杂 Family predictor | Stop/Pivot |
| 是否继续轻量 prefix metadata | Go |

---

## 八、建议的下一步

### 8.1 优先做轻量方案

将系统目标收敛为：

```text
explicit session_id
  + exact prefix identity
  + observed holder/frequency
  + bounded priority bucket
  + decay/budget
```

先验证简单信号能否达到 Oracle 收益的大部分，而不是直接预测抽象 Family label。

### 8.2 必须补的实验

1. 全部多轮 request replay，而不只是每个 Session 的首请求；
2. Session close 后共享 prefix 的 residual value；
3. 非 clean-prefix workload，避免 7.8K 公共根主导全部结果；
4. priority budget：只允许保护 5%、10%、20% KV；
5. priority decay/TTL，避免 `max()` 永久污染；
6. LFU/SLRU 与 priority 在同一 SGLang engine 上闭环；
7. simulator 与 SGLang 对同一 action tape 做 cached-token conformance。

### 8.3 下一 Gate

下一阶段的核心比较应改为：

```text
Oracle Family priority
  -
Observed frequency/shared-count bounded priority
```

而不再主要比较 Oracle 与 LRU。

如果简单 observed signal 能恢复 Oracle 收益的 90% 以上，则停止复杂 Family predictor，保留 PrefixFamilyTable 作为 holder/accounting metadata。

---

## 九、产物索引

### 脚本

- `scripts/benchmark_oracle_family_retention.py`
- `scripts/simulate_f02_family_retention.py`
- `scripts/benchmark_cross_session_ttft.py`

### 引擎结果

- `experiments/sglang_kv_cache/exp_f02_oracle_family_retention/lru_calibration_n4.json`
- `experiments/sglang_kv_cache/exp_f02_oracle_family_retention/lru_calibration_n5.json`
- `experiments/sglang_kv_cache/exp_f02_oracle_family_retention/lru_calibration_n6.json`
- `experiments/sglang_kv_cache/exp_f02_oracle_family_retention/lru_calibration_n7.json`
- `experiments/sglang_kv_cache/exp_f02_oracle_family_retention/lru_n6.json`
- `experiments/sglang_kv_cache/exp_f02_oracle_family_retention/priority_zero_n6.json`
- `experiments/sglang_kv_cache/exp_f02_oracle_family_retention/priority_oracle_n6.json`

### 模拟结果

- `experiments/vllm_kv_cache/investigation/data/f02_family_retention_simulation.json`

---

## 十、最终结论

Oracle Prefix Family retention 的**单点机制价值已经成立**：

```text
LRU:              7.8K Family → 3 cached tokens
Priority Oracle:  7.8K Family → 完整驻留
真实 TTFT:        307.3 ms → 94.2 ms
```

但**复杂 Family 建模的增量价值尚未成立**：

```text
Oracle next-use - LFU
= 0.235 至 0.544 percentage points
```

因此最合理的路线不是立刻实现复杂预测器，而是先把 Family 研究收敛为可解释、低成本、可衰减的 prefix value metadata，并在多轮、Session close 和非 clean-prefix workload 上重新验证 residual utility。
