# Prefix Family 跨 Session 复用与 TTFT 价值验证报告

> 日期：2026-07-17  
> 状态：阶段性实验报告  
> 对应主计划：`docs/33_explicit_session_prefix_family_plan.md`  
> 研究阶段：F0.1 Cross-session Exact-prefix Mass 与 TTFT 转换验证

---

## 一、执行摘要

本轮实验回答两个连续问题：

1. Agent 工作负载中是否存在可跨显式 Session 复用的 exact token prefix？
2. 这些 prefix 命中能否真实转化为 TTFT 与 SLO 收益？

当前证据给出的答案均为肯定：

- 767 个显式 Session 的首请求共包含 8.24M prompt tokens；
- 排除同一任务的重复运行后，57.12% 的完整 block token mass 可在不同任务间找到 exact prefix；
- 进一步要求来自不同项目时，该比例仍为 56.10%；
- 不同项目 cross-prefix 的中位数为 7,808 tokens；
- 在 Qwen3-8B + SGLang 上，7.8K prefix hit 将无并发 TTFT 中位数从 239.9 ms 降至 40.9 ms，节省 203.8 ms；
- 使用真实 Astropy/Django 请求时，精确共享的 7,823 tokens 带来 204.7–213.3 ms 的 TTFT 中位数收益；
- 与 8 个独立 4K prefill 并发时，7.8K hit 仍将 probe TTFT 中位数从 244.3 ms 降至 93.1 ms；
- 在该并发场景中，以 100 ms 为阈值，cold probe 的样本违约率为 100%，hit probe 为 0%。

因此，F0.1 的“机会是否存在”已经通过；“cache hit token 是否能转化为 TTFT 收益”也在机制级微基准上得到确认。

但这还不能证明必须引入 Prefix Family 策略。SGLang 原生 Radix Cache 在 prefix 仍驻留时已经能够完成内容寻址复用。下一阶段需要验证的是：

> 在容量压力和自然请求交错下，Oracle Prefix Family retention 相比默认 Radix、LRU、priority 和 session-aware 基线，能否显著提高 prefix 驻留概率并保住上述 TTFT/SLO 收益。

---

## 二、研究问题与结论边界

### 2.1 本报告已经验证

- 跨显式 Session 的 exact-prefix 机会在当前 trace 中广泛存在；
- 该机会在排除同任务重复后仍然存在；
- 不同项目之间存在稳定的约 7.8K 公共 prefix；
- prefix hit 可以减少真实 prefill work；
- 省下的 prefill work能够转化为约 150–215 ms 的 TTFT 收益；
- 在受控并发 prefill 压力下，该收益仍然存在。

### 2.2 本报告尚未验证

- Prefix Family 在线识别或预测是否准确；
- 默认缓存策略会以多高概率丢失这些 prefix；
- Family-aware retention 相比最强非 Family 基线是否有 residual utility；
- 在真实到达过程、长时间运行和多租户环境中的 P95/P99 收益；
- L2/L3 restore 是否快于重算；
- Family 索引、更新和策略决策本身的系统开销；
- 跨模型、跨 tokenizer、跨 LoRA 或跨 KV layout 的复用安全性。

因此，本报告不能直接宣称“Prefix Family 策略已经有效”，只能得出：

> 当前工作负载中存在有价值的跨 Session prefix；如果系统能够在正确时间保住它，单次命中可以产生显著 TTFT 收益。

---

## 三、实验环境

| 项目 | 配置 |
|---|---|
| GPU | NVIDIA H800 81 GB，单卡 |
| 模型 | Qwen3-8B |
| Tokenizer | Qwen2Tokenizer |
| SGLang | `0.0.0.dev1+g880e6f66f` |
| KV cache | SGLang Radix Cache，page size = 1 |
| 调度 | LPM |
| `mem-fraction-static` | 0.3 |
| cache report | 开启 |
| TTFT 输出长度 | `max_tokens=1` |
| 运行模式 | 单机单实例 |

Tokenizer 的 chat template SHA256 为：

```text
a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8
```

所有 TTFT 实验均在同一 SGLang 实例中完成。每个 prefix 长度或并发级别先运行一轮不计入结果的预热。

---

## 四、实验一：Cross-session Exact-prefix Mass

### 4.1 数据

数据来自：

```text
experiments/vllm_kv_cache/lmcache_traces/
```

输入审计结果：

| 指标 | 数值 |
|---|---:|
| 扫描行数 | 24,880 |
| 首请求数 | 767 |
| 显式 Session 数 | 767 |
| 缺失 `session_id` 的行数 | 0 |
| 项目数 | 14 |
| 去重后任务数 | 565 |
| 重复任务组数 | 160 |
| 原始首请求 token | 8,243,606 |
| 完整 16-token block token | 8,237,824 |

本实验只分析每个显式 Session 的第一个请求，以隔离跨 Session cold-start prefix 机会。

### 4.2 Exact-prefix 定义

消息首先通过固定的 Qwen chat template 序列化，再使用 Qwen3-8B tokenizer 转为 token。随后以 16-token 完整 block 构建 `ExactBlockTrie`。

一个请求的 cross-prefix 长度定义为：

> 从根开始，能够由另一个满足目标约束的 Session 持有的最长完整 token-block prefix。

该指标是 leave-one-session-out 静态机会，不代表 prefix 在真实全局时间线上一定驻留。

### 4.3 核心结果

| 范围 | 可复用 token mass | 比例 |
|---|---:|---:|
| 任意其他 Session | 5,251,936 | 63.75% |
| 数据集顺序中的先前 Session | 4,960,288 | 60.21% |
| 不同任务 | 4,705,280 | 57.12% |
| 同项目、不同任务 | 4,695,648 | 57.00% |
| 不同项目 | 4,621,600 | 56.10% |

不同项目 cross-prefix 分布：

| 分位数 | token 数 |
|---|---:|
| P25 | 2,624 |
| P50 | 7,808 |
| P75 | 7,808 |
| P90 | 7,808 |
| P95 | 7,808 |
| P99 | 7,808 |

72.36% 的首请求具有至少 4K 的跨项目 exact prefix。排除同任务重复后，不同任务或不同项目的 8K 以上比例为 0%；这说明更长 prefix 主要来自 benchmark 重复，而约 7.8K prefix 才是稳定的跨项目公共结构。

### 4.4 结论

对当前 OpenHands/SWE-bench trace 而言，F0.1 的 stop 条件没有触发。跨 Session exact-prefix 不是少量异常样本，而是由大规模稳定 prompt 模板形成的结构性机会。

同时，该结果具有明显的数据集依赖性：如果线上请求不共享 agent system prompt、工具定义或运行时环境描述，这一比例可能显著下降。

---

## 五、实验二：合成 Prefix 长度—TTFT 转换曲线

### 5.1 实验设计

对每个 prefix 长度执行如下 paired cold/hit 对照：

```text
cold:
  flush_cache
  probe(shared_prefix + probe_tail)

hit:
  flush_cache
  warm(shared_prefix + different_warm_tail)
  probe(shared_prefix + probe_tail)
```

关键控制：

- cold 和 hit 使用完全相同的 probe；
- warm 与 probe 是两个不同请求，且 user tail 不同；
- 两者只共享 system prefix；
- 每个长度重复 7 轮；
- 每个长度额外运行一轮丢弃的预热；
- probe tail 为 128 content tokens；
- `max_tokens=1`，尽量隔离 TTFT；
- cold 轮的 `cached_tokens` 必须为 0；
- hit 轮的 `cached_tokens` 必须与目标 prefix 一致。

### 5.2 结果

| Prefix | Cold TTFT P50 | Hit TTFT P50 | P50 节省 | P50 降幅 | Cold/Hit P95 |
|---:|---:|---:|---:|---:|---:|
| 1,024 | 35.7 ms | 16.8 ms | 18.9 ms | 53.2% | 38.6 / 17.2 ms |
| 4,096 | 125.3 ms | 24.1 ms | 99.1 ms | 80.7% | 128.1 / 29.1 ms |
| 7,808 | 239.9 ms | 40.9 ms | 203.8 ms | 83.8% | 256.7 / 44.4 ms |

缓存命中校验：

| Prefix content tokens | Hit cached tokens |
|---:|---:|
| 1,024 | 1,032 |
| 4,096 | 4,104 |
| 7,808 | 7,816 |

多出的 8 tokens 来自共享的 chat-template 边界。

### 5.3 解释

结果不是简单线性关系：

- 1K prefix 只能节省约 19 ms；
- 4K prefix 开始跨越 100 ms TTFT 阈值；
- 7.8K prefix 可节省约 204 ms。

这说明 Family value 不应只使用“是否共享”这一布尔信号，而应至少考虑：

- 可命中的 exact prefix 长度；
- probe 的剩余 uncached suffix；
- 当前并发与队列状态；
- cache tier 和 restore/recompute 成本。

---

## 六、实验三：真实跨项目请求验证

### 6.1 请求选择

从 trace 中选取两个不同项目、不同显式 Session 的真实首请求：

```text
swebench__astropy__astropy-12907__minimax
swebench__django__django-10097__minimax
```

Token 审计：

| 请求 | Prompt tokens |
|---|---:|
| Astropy | 8,468 |
| Django | 10,073 |
| 双方 exact LCP | 7,823 |

这两个请求来自不同项目，因此不存在“同一 benchmark task 重复运行”导致的虚假跨 Session 复用。

### 6.2 双向结果

| Warm → Probe | Cold P50 | Hit P50 | P50 节省 | P50 降幅 | Hit cached |
|---|---:|---:|---:|---:|---:|
| Astropy → Django | 317.3 ms | 103.9 ms | 213.3 ms | 67.2% | 7,823 |
| Django → Astropy | 253.8 ms | 48.7 ms | 204.7 ms | 81.0% | 7,823 |

P95：

| Warm → Probe | Cold P95 | Hit P95 | P95 最大 paired 节省 |
|---|---:|---:|---:|
| Astropy → Django | 337.7 ms | 110.6 ms | 235.4 ms |
| Django → Astropy | 262.8 ms | 57.5 ms | 212.4 ms |

### 6.3 为什么两个方向的 Hit TTFT 不同

两侧共享的 prefix 都是 7,823 tokens，但剩余 suffix 不同：

- Django probe：10,073 - 7,823 = 2,250 uncached tokens；
- Astropy probe：8,468 - 7,823 = 645 uncached tokens。

因此，双方都省下约 7.8K prefill work，但 Django 仍需计算更长的 suffix，其 hit TTFT 高于 Astropy。这进一步说明：

> Family value 应根据“预计 avoided prefill work + 剩余工作量”建模，不能仅根据 Family ID 或共享 prefix 长度排序。

### 6.4 SLO 样本结果

| Probe | 阈值 | Cold 违约率 | Hit 违约率 |
|---|---:|---:|---:|
| Django | 200 ms | 100% | 0% |
| Astropy | 100 ms | 100% | 0% |
| Astropy | 200 ms | 100% | 0% |

每个方向只有 7 个测量样本，因此这些违约率仅用于说明机制影响，不能视为生产 P99 估计。

---

## 七、实验四：并发 Prefill 压力

### 7.1 实验设计

在 7,808-token 合成 probe 旁同时发送多个独立噪声请求：

- 每个噪声请求约 4,096 prompt content tokens；
- 噪声请求与 probe 不共享 prefix；
- 测试 4 和 8 个并发噪声请求；
- 每个并发级别重复 5 轮；
- cold/hit 仍使用相同 probe；
- hit batch 开始前先完成 warm request。

该实验产生并发 prefill、batch 和 scheduler 压力，但不模拟完整生产 arrival process。

### 7.2 结果

| 并发噪声请求 | Cold Probe P50 | Hit Probe P50 | P50 节省 | P50 降幅 | Hit P95 |
|---:|---:|---:|---:|---:|---:|
| 4 × 4K | 238.1 ms | 54.6 ms | 184.5 ms | 77.3% | 56.3 ms |
| 8 × 4K | 244.3 ms | 93.1 ms | 152.0 ms | 61.6% | 96.3 ms |

SLO 样本结果：

| 并发噪声请求 | 阈值 | Cold 违约率 | Hit 违约率 |
|---:|---:|---:|---:|
| 4 | 100 ms | 100% | 0% |
| 4 | 200 ms | 100% | 0% |
| 8 | 100 ms | 100% | 0% |
| 8 | 200 ms | 100% | 0% |

所有 hit probe 都精确报告 7,816 cached tokens。

### 7.3 解释

并发从 4 增至 8 时：

- hit TTFT 从 54.6 ms 上升至 93.1 ms；
- paired saving 从 184.5 ms 下降至 152.0 ms；
- prefix hit 的收益缩小，但没有消失。

该结果包含 cache hit 和 LPM scheduler 的联合影响。cached probe 可能因更长 prefix match 获得更有利的调度顺序，因此不能把全部收益都归因于纯 prefill 计算减少。

但对系统设计而言，这正是有意义的联合效果：Family signal 最终也需要反馈给 retention 与 scheduling，而不是只做静态存储优化。

---

## 八、与既有驱逐实验的联合证据

既有 SGLang S4 实验已经观察到：

```text
baseline cached_tokens = 10,072
容量压力后的 cached_tokens = 3
压力后的 TTFT = 301.5 ms
```

在约 99K KV work 压入约 59,902-token cache 后，公共 L0 prefix 几乎完全被驱逐。

该实验与本轮 TTFT 结果共同形成如下证据链：

```text
跨 Session exact prefix 广泛存在
        ↓
7.8K prefix hit 可节省约 200 ms TTFT
        ↓
默认 Radix 在容量压力下可能丢失公共 prefix
        ↓
需要测试 Family-aware retention 是否能保住这部分收益
```

不过，S4 使用的是既有 Django L0，并非本轮 7,823-token Astropy/Django Family，也没有比较 Oracle Family 策略。因此它只能证明问题可能发生，不能替代下一阶段的策略对照。

---

## 九、研究判断

### 9.1 已通过的 Gate

**Gate A：跨 Session exact-prefix 机会存在**

通过。排除同任务重复后仍有 57.12% 的不同任务 token mass 和 56.10% 的不同项目 token mass。

**Gate B：机会可转化为 TTFT**

通过。真实 7,823-token prefix 双向都带来约 205–213 ms 的 TTFT 中位数收益。

**Gate C：受控并发下收益仍存在**

通过。8 个 4K 并发 prefill 下仍节省约 152 ms P50，并将 probe 保持在 100 ms 内。

### 9.2 尚未通过的核心 Gate

**Gate D：Prefix Family 相比现有机制具有 residual utility**

尚未验证。

当前实验人为保证 hit 条件中的 prefix 已驻留。它证明的是“保住 prefix 有价值”，没有证明“Family 是保住 prefix 的必要或最佳信息”。

真正的主比较仍应为：

```text
Oracle Prefix Family
    -
strongest(
    LRU,
    recency/frequency,
    prefix depth/shared count,
    default Radix,
    SessionRadix + close,
    session/ref-aware eviction,
    priority retention
)
```

---

## 十、下一阶段：Oracle Prefix Family Retention

### 10.1 实验目标

不训练 Family predictor，不先实现复杂在线索引，直接使用 trace ground truth 构造 Oracle Family，验证 Family 信息的增量价值上限。

### 10.2 最小对照组

至少比较：

```text
B0  默认 SGLang Radix eviction
B1  recency/frequency
B2  prefix depth + shared Session count
B3  session-aware/ref-aware retention
B4  priority + retention duration
B5  Oracle Prefix Family value
```

### 10.3 工作负载

需要同时包含：

- 真实首请求的 7.8K 跨项目 Family；
- 同 Session 后续 turn；
- 不同 Family 的容量竞争；
- Session close 后仍可能被其他 Session 复用的 prefix；
- 无共享价值的长 noise prefix；
- 可控到达间隔和 burst concurrency。

### 10.4 主要指标

策略层：

- Family prefix residency probability；
- useful hit tokens；
- avoided prefill tokens；
- 错误保护导致的有价值 cache eviction；
- 每 byte retained 的未来 avoided work。

服务层：

- TTFT P50/P95/P99；
- 100/200/500 ms SLO attainment；
- queueing latency；
- prefill latency；
- throughput/goodput；
- fairness 与 starvation。

### 10.5 Go/Stop 判断

如果 Oracle Family 相比最强非 Family 基线仍能稳定保住更多 7.8K prefix，并把本报告中约 150–215 ms 的单次 TTFT 潜在收益转化为 workload-level P95/P99 或 goodput 收益，则进入 PrefixFamilyIndex 与在线 value model。

如果最强的 prefix-depth/shared-count、priority 或 session-aware 策略已经达到 Oracle Family 的效果，则应停止复杂 Family 主线，将研究收敛为更简单的显式 Session + prefix metadata 管理。

---

## 十一、局限与风险

1. **样本量有限**：TTFT 每个配置只有 5–7 个有效样本，不能估算生产 P99。
2. **单模型单硬件**：结果只覆盖 Qwen3-8B 和 H800。
3. **SGLang 版本较旧**：当前版本为开发提交，后续正式版本的 scheduler、Radix Cache 和 kernel 可能不同。
4. **显式 flush 构造 cold/hit**：这有利于因果控制，但不是自然驱逐过程。
5. **合成并发不是线上 arrival**：没有真实 burst、优先级、decode 干扰和多租户混合。
6. **Runtime 未使用 `session_id` 决策**：两个请求在语义上属于不同 trace Session，但运行时复用由 token 内容寻址触发。
7. **模板主导风险**：7.8K 公共 prefix 可能高度依赖 OpenHands system prompt 与工具定义。
8. **未计保留成本**：保护 7.8K prefix 可能挤出其他高价值 KV。
9. **未测试 restore**：本报告只测 GPU-resident hit，未测试 L2/L3 恢复。
10. **调度耦合**：并发收益包含 LPM 调度效应，不能解释为纯 kernel 计算差。

---

## 十二、复现方式

### 12.1 静态 exact-prefix 审计

```bash
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python \
  scripts/analyze_f01_cross_session_prefix.py
```

### 12.2 合成 prefix TTFT 曲线

```bash
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python \
  scripts/benchmark_cross_session_ttft.py
```

### 12.3 真实跨项目双向测试

```bash
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python \
  scripts/benchmark_real_cross_project_ttft.py
```

### 12.4 并发 prefill 压力

```bash
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python \
  scripts/benchmark_cross_session_ttft_under_load.py
```

运行 TTFT 脚本前需要按 `docs/24_sglang_experiment_report.md` 启动端口 8001 的 SGLang 服务，并启用：

```text
--enable-cache-report
--enable-metrics
--schedule-policy lpm
```

---

## 十三、文件索引

### 分析与实验脚本

- `scripts/analyze_f01_cross_session_prefix.py`
- `scripts/benchmark_cross_session_ttft.py`
- `scripts/benchmark_real_cross_project_ttft.py`
- `scripts/benchmark_cross_session_ttft_under_load.py`

### 原始结果

- `experiments/vllm_kv_cache/investigation/data/f01_cross_session_exact_prefix.json`
- `experiments/sglang_kv_cache/exp_f01_cross_session_ttft/run_1.json`
- `experiments/sglang_kv_cache/exp_f01_real_cross_project_ttft/run_1.json`
- `experiments/sglang_kv_cache/exp_f01_cross_session_ttft_under_load/run_1.json`
- `experiments/sglang_kv_cache/exp_s4_l0_eviction/run_1.json`

### 相关规划与既有报告

- `docs/33_explicit_session_prefix_family_plan.md`
- `docs/24_sglang_experiment_report.md`

---

## 十四、最终结论

当前阶段最重要的结论不是“Family 策略已经成功”，而是完成了价值链的前两步验证：

```text
机会存在：
跨项目 exact-prefix mass = 56.10%
不同项目 prefix P50 = 7,808 tokens

机会有性能价值：
真实 7,823-token hit 节省约 205–213 ms TTFT

并发下仍有价值：
8 × 4K prefill 时仍节省约 152 ms P50
```

这已经足以支持继续进行 Oracle Prefix Family retention，但还不足以支持实现复杂在线 Family predictor。

下一步应优先回答：

> 在真实容量竞争中，Family ground truth 相比现有 Radix、Session、priority 和 prefix-shared-count 信号，究竟还能额外保住多少有价值 KV，并最终改善多少 workload-level SLO？
