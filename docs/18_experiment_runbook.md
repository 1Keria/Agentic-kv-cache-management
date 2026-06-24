# vLLM KV Cache 实验运行控制文档

> 本文档定义了所有实验的完整执行流程。Claude 将严格按照此文档独立运行所有实验。

---

## 核心原则

### 1. 所有产出必须清晰标注数据来源

每一个数据点、曲线、结论，都必须标注来源：

| 标签 | 含义 | 示例 |
|------|------|------|
| `[MEASURED]` | vLLM 实际运行的测量数据 | TTFT、cached_tokens、GPU KV usage |
| `[SIMULATED]` | 基于 trace hash 的模拟计算结果 | kvcache-blog 的命中率曲线 |
| `[TRACE-ANALYSIS]` | 对已有 trace 数据的分析统计 | Claude Code 流量的 token 分布 |
| `[SYNTHETIC]` | 人为构造的 prompt（但基于真实组件） | 真实 L0 + 真实 L1 + 真实 L2 组合 |

**绝对禁止将模拟数据标注为真实数据。**

### 2. scripts/ 只是参考起点，不是最终版本

发现问题时立即改进脚本，不要凑数据。数据为准，脚本为仆。

### 3. 主动修复，永不停止，追求正确而非完成任务

任何脚本有 bug 或可改进 → 立即修复 → 重新运行。最终分析必须可用可信。

---

## 实验架构：模拟层 + 验证层

### 模拟层：kvcache-blog trace 数据分析

**数据来源**：`kvcache-blog/data/kv_cache_lab/precomputed.json`

基于真实 Agent trace 的 block hash 模拟，产出缓存命中率曲线。**只有 hash id，没有原始文本，不能发给 vLLM。**

| Trace | 场景 | 请求数 | 平均 input tokens | 无限命中率 | 标注 |
|-------|------|--------|-------------------|-----------|------|
| LMCache Agentic | SWE-bench agent | 1,200 | 23,475 | 99.7% | `[SIMULATED]` |
| Claude Code Weka | 编码 agent 生产 | 136,118 | 178,018 | 89.5% | `[SIMULATED]` |
| Claude Code + Subagent | 含子 agent | 77,858 | 122,583 | 97.2% | `[SIMULATED]` |
| kv-cache-tester | Claude Code replay | 59,937 | 138,737 | 97.5% | `[SIMULATED]` |
| Mooncake FAST25 | Tool&Agent | 23,608 | 8,590 | 59.1% | `[SIMULATED]` |
| Qwen Bailian | 生产 chat/search | 43,058 | 2,331 | 62.2% | `[SIMULATED]` |

**产出**：
- Agent 场景下 KV cache 命中率 vs 缓存容量曲线（FIFO/LRU/Optimal 三策略）
- 跨 session 复用率统计
- 不同 Agent 工作负载的对比
- **论文价值**：回答"Agent 场景 KV cache 复用理论收益有多大"

### 验证层：vLLM 实际运行测量

**数据来源**：真实 Agent prompt 文本，发给 vLLM，测量 KV cache 行为。

**关键设计决策**：

1. **不需要运行 Agent**——只发 prompt 做 prefill，不执行 tool call，不跑 agent loop
2. **不需要区分 user**——APC 基于 block content hash 匹配，不看请求者身份
3. **需要真实 L0/L1/L2 文本**——不能是填充文本，必须有 Agent prompt 的自然层次结构

**真实 prompt 数据来源**（优先级排序）：

| 优先级 | 来源 | L0 规模 | 说明 |
|--------|------|---------|------|
| 1 | LMCache agentic traces (HuggingFace) | ~23K avg | 真实 SWE-bench agent 会话完整文本，需 VPN 下载 |
| 2 | SWE-bench PS + 真实 L0/L1 构造 | 可控 | 用真实 PS + 从项目提取的真实 L0/L1 组合 |
| 3 | mini-swe-agent trajectory | ~1.7K | 太小，仅作补充 |

**如果 LMCache 数据集下载成功**：
- 直接用里面的完整 message 文本作为 prompt
- 每条记录是一个完整 session（多轮对话）
- 同 repo 的多条 session 天然共享 L0+L1

**如果下载失败**，用方案 2 构造真实 prompt：
- L0 = 从 mini-swe-agent system_template + instance_template 扩展（加 tool schema、skill listing）
- L1 = 从 SWE-bench 各 repo 的 CLAUDE.md / README 提取
- L2 = SWE-bench 的 problem_statement
- 标注为 `[SYNTHETIC]`（组件是真实的，但组合是人为的）

**产出**：
- Prefix cache 命中时的 TTFT 加速比 `[MEASURED]`
- Offloading 恢复 vs 完整重算的延迟对比 `[MEASURED]`
- Block-level 粒度浪费实测 `[MEASURED]`
- 驱逐策略对 prefix 的影响 `[MEASURED]`
- **论文价值**：回答"vLLM 实际实现能否达到理论收益"

---

## 0. 前置检查与自动修复

- [ ] GPU 空闲 → kill 占用进程或等待
- [ ] 端口 8000 未被占用 → `lsof -ti :8000 | xargs kill -9`
- [ ] Conda 环境可用
- [ ] 模型文件存在
- [ ] 脚本语法正确 → 否则直接修复
- [ ] exp_utils import 正常 → 否则直接修复
- [ ] VPN 可用（如需下载 HuggingFace 数据）→ `~/vpn/scripts/vpn-start && source ~/vpn/scripts/proxy-on.sh`

### VPN 使用

```bash
~/vpn/scripts/vpn-start          # 启动
source ~/vpn/scripts/proxy-on.sh # 设环境变量
curl -I https://huggingface.co   # 测试
source ~/vpn/scripts/proxy-off.sh # 关闭
```

---

## 1. 实验执行流程

### Step 0: 数据准备

1. **尝试下载 LMCache agentic traces**（VPN）：
   ```bash
   source ~/vpn/scripts/proxy-on.sh
   python -c "from datasets import load_dataset; ds = load_dataset('zeelHz/lmcache-agentic-traces', split='train'); ds.save_to_disk('experiments/vllm_kv_cache/lmcache_traces')"
   ```
   - 如果成功：提取真实 prompt 文本，更新 `exp_utils.py` 的 prompt 构建逻辑
   - 如果失败：用方案 2（SWE-bench PS + 构造 L0/L1），标注 `[SYNTHETIC]`

2. **分析 kvcache-blog precomputed 数据**：
   - 提取各 trace 的命中率曲线（FIFO/LRU/Optimal × 容量）
   - 产出模拟层图表，标注 `[SIMULATED]`

3. **验证 prompt 数据**：
   - 确认 L0 规模足够大（> 1000 tokens）
   - 确认同 repo 的 session 共享 L0+L1
   - 确认不同 repo 的 session 只共享 L0

### Step 1~12: vLLM 验证层实验

与之前计划相同（exp1~exp5），但 prompt 数据改为真实 Agent 文本。

**重要：每个实验完成后必须重启 vLLM server**，确保 KV cache 完全清空，避免前一个实验的残留缓存影响下一个实验的结果。这适用于：
- 同一个实验的不同 run 之间
- 不同实验之间
- 任何配置切换

| 阶段 | Server 配置 | 实验 | 预计时间 |
|------|------------|------|---------|
| Phase 1 | Offloading ON (8 GiB) | exp1, exp2, exp3-on, exp4(4.1~4.6 on), exp5(lru+aware) | ~3h |
| Phase 2 | Offloading OFF (0 GiB) | exp3-off, exp4(4.5 off, 4.6 off) | ~0.5h |
| Phase 3 | 三种 preemption 策略对比 | exp6 (swap-out/swap-in/recompute) | ~1h |

具体步骤同之前 runbook（Step 1.1~1.12, 2.1~2.4），此处不重复。

### Step 12.5: 实验 6 — 内存压力下调度行为对比（新增）

**目的**：在 GPU KV cache 内存压力下，对比 vLLM 三种 preemption 策略对 Agent session 的影响。

**三种策略解释**：

| 策略 | 行为 | 代价 | 适用场景 |
|------|------|------|---------|
| **swap-out** | GPU 满时，把 running 请求的 KV blocks 整体拷到 CPU，腾出 GPU 空间 | CPU 内存占用 + 拷贝延迟 | 有 CPU 内存余量，请求会回来继续跑 |
| **swap-in** | CPU 上等待的请求等到 GPU 有空间后，把 KV 从 CPU 拷回 GPU 继续跑 | 拷贝延迟 | swap-out 的逆操作，配合使用 |
| **recompute** | 直接丢掉被 preempt 请求的 KV cache，等有空间了从头重新 prefill | 重新计算的开销（最大），但不占 CPU 内存 | CPU 内存紧张，或请求 KV 价值低 |

**vLLM 中的对应配置**：

| 策略 | vLLM 参数 | 说明 |
|------|-----------|------|
| swap-out + swap-in | `--kv-offloading-size 8` | 启用 CPU offloading，被驱逐 block 存 CPU |
| recompute | `--kv-load-failure-policy recompute` | KV 加载失败时丢弃重算（而非报错） |
| 默认 preemption | 无额外参数 | scheduler 直接 preempt，请求进 waiting queue 重排 |

**实验设计**：同一请求序列，在三种配置下分别运行（每次重启 server）：

```
Phase 1: 发送 3 个同项目 Agent session T1 (每个 ~6500 tokens, 共 ~19.5K)
Phase 2: 发送 2 个不同项目 session T1 (每个 ~6300 tokens, 共 ~12.6K) → 触发内存压力
Phase 3: 发送 1 个同项目 session T2 → 观察 prefix 恢复行为
Phase 4: 发送 1 个被 preempt 的 session 继续推理 → 观察恢复延迟
```

**三种配置运行**：

| 运行 | 配置 | 观察重点 |
|------|------|---------|
| A (swap) | `--kv-offloading-size 8` | Phase 3/4 的 KV 从 CPU 恢复，TTFT 中等 |
| B (recompute) | `--kv-load-failure-policy recompute`，无 offloading | Phase 3/4 需完整重算，TTFT 最慢 |
| C (默认 preempt) | 无 offloading，无 recompute | Phase 3/4 被 preempt 后进 waiting，行为取决于 scheduler |

**关键观测**：

| 指标 | swap | recompute | 默认 preempt |
|------|------|-----------|-------------|
| Phase 3 cached_tokens | > 0（CPU 恢复） | = 0（需重算） | 取决于驱逐情况 |
| Phase 3 TTFT | 中等 | 最慢 | 不确定 |
| Phase 4 恢复延迟 | swap-in 延迟 | 完整 prefill 延迟 | 重新调度延迟 |
| CPU 内存占用 | 高（存了 KV） | 低（丢弃了） | 低 |
| `num_preemptions` Prometheus | 有 | 有 | 有 |

**产出标注**：`[MEASURED]`

**论文价值**：这是 AgentKV 论文的关键数据——证明在 Agent 场景下，swap-out/swap-in（即 offloading）对保护 L0/L1 prefix 至关重要，recompute 代价太大，默认 preempt 可能错误驱逐高价值 prefix。

### Step 13: 模拟层分析

从 `kvcache-blog/data/kv_cache_lab/precomputed.json` 提取：

1. **各 trace 的命中率 vs 容量曲线**（FIFO/LRU/Optimal）
2. **Agent trace vs 非 Agent trace 的对比**（LMCache Agentic 99.7% vs Qwen Bailian 62.2%）
3. **Claude Code trace 的 token 分布分析**（avgInputTokens、uniqueBlocks/totalBlocks 比值）
4. 所有产出标注 `[SIMULATED]`

### Step 14: 论文级结果产出

1. 生成所有图表（PDF + PNG 双格式）
2. 生成 LaTeX 表格
3. 撰写完整分析报告（每个实验：设计→结果→分析→结论→论文建议）
4. 提炼核心发现（5-8 条，可直接用于论文 Motivation）
5. 整理到 `experiments/vllm_kv_cache/results/`

---

## 2. Server 管理操作

同之前 runbook，此处不重复。

---

## 3. 四个观测渠道的分工

实验中必须同时使用四个观测渠道，各有不同的粒度和适用场景：

### ① cached_tokens（请求级，最直接）

**来源**：OpenAI API 响应的 `prompt_tokens_details.cached_tokens` 字段
**粒度**：单个请求
**适用**：看单次请求的 prefix reuse 情况，回答"这个请求命中了多少"

**当前覆盖**：✅ 已大量使用（所有 run_expN.py 都记录）

**必须采集的指标**：
- `prompt_tokens` — 请求总 input tokens
- `cached_tokens` — 命中缓存的 tokens
- `hit_rate = cached_tokens / prompt_tokens` — 命中率
- `ttft_ms` — 首 token 延迟

### ② /metrics 端点（全局聚合，看趋势）

**来源**：`http://localhost:8000/metrics`（Prometheus 格式）
**粒度**：全局累计 / gauge
**适用**：看 KV cache 整体趋势——利用率、命中率、队列长度、offload 传输量

**当前覆盖**：⚠️ 有采集（exp_utils.py 的 get_prometheus_metrics）但利用不足，只存了 before/after

**必须持续采集的关键指标**：

| 指标 | 类型 | 含义 |
|------|------|------|
| `kv_cache_usage_perc` | gauge | GPU KV cache 使用百分比 |
| `prefix_cache_hits` | counter | prefix cache 命中次数 |
| `prefix_cache_queries` | counter | prefix cache 查询次数 |
| `num_preemptions` | counter | 请求被 preempt 的次数 |
| `kv_offload_store_bytes` | counter | GPU→CPU offload 传输量 |
| `kv_offload_load_bytes` | counter | CPU→GPU 恢复传输量 |
| `kv_offload_stores_skipped` | counter | 跳过的 offload 次数 |
| `request_prefill_kv_computed_tokens` | counter | prefill 阶段需重新计算的 tokens |
| `prompt_tokens_cached` | counter | 总 cached tokens |

**改进**：`KVTimelineCollector` 已实现持续采样（interval=0.5s），但需要扩展，在每次采样时不仅采 `kv_cache_usage_perc`，还要采以上所有指标。这样能产出完整的 KV cache 生命周期时间线。

### ③ vLLM DEBUG 日志（调度决策级）

**来源**：vLLM server 的日志输出
**粒度**：调度事件
**适用**：看 swap-out/swap-in/preempt/recompute 等调度决策

**当前覆盖**：❌ 完全没有。server 用 `--log-level info`，看不到调度细节。

**改进**：在需要观察调度行为的实验（exp3, exp4.5, exp4.6, exp5, exp6）中，server 启动时使用：

```bash
--log-level DEBUG
```

关键日志关键词：
- `preempt` / `Preempting` — 请求被抢占
- `swap` / `swapping` — KV block swap 事件
- `evict` / `eviction` — block 被驱逐
- `offload` / `store` / `load` — CPU offloading 事件
- `recompute` — KV 重算事件

**日志采集方式**：server 的 stdout 重定向到文件，实验后用 grep 提取关键事件，与 timeline 对齐。

### ④ 源码阅读（机制理解，解释"为什么"）

**来源**：vLLM 源码
**粒度**：代码逻辑
**适用**：当观测到异常行为时，读源码理解"为什么 vLLM 这样做"

**当前覆盖**：❌ 脚本中未涉及，但分析报告需要

**关键源码文件**：

| 文件 | 内容 |
|------|------|
| `vllm/v1/core/sched/scheduler.py` | 调度器核心——preempt 决策、优先级、waiting/running 队列 |
| `vllm/v1/core/single_type_kv_cache_manager.py` | KV cache 管理——block 分配、释放、prefix 匹配 |
| `vllm/v1/simple_kv_offload/manager.py` | CPU offloading——swap-out/swap-in 逻辑 |
| `vllm/v1/core/block_pool.py` | Block 池管理——eviction 策略 |

**使用方式**：当实验数据出现意外结果（如 cached_tokens 与预期不符、preempt 行为异常），直接读源码定位原因，将解释写入分析报告。

### 四渠道协同工作流

```
实验设计 → ② 持续采样 /metrics（全局趋势）
  ↓
发请求 → ① 记录每个请求的 cached_tokens + TTFT
  ↓
分析数据 → 发现异常？
  ↓ 是
读 ③ DEBUG 日志 → 找到具体的 swap/preempt 事件
  ↓ 仍不理解
读 ④ 源码 → 理解调度器的决策逻辑
  ↓
写分析报告：行为 + 原因 + 影响
```

**必须改进的地方**：
1. `run_vllm_server.sh`：添加 `--log-level debug` 选项（默认 info，实验 3/4.5/4.6/5/6 开 debug）
2. `KVTimelineCollector`：扩展采样指标，不仅采 `kv_cache_usage_perc`，还采 prefix_cache_hits/queries、num_preemptions、offload bytes 等
3. `exp_utils.py`：添加日志解析函数，从 server 日志提取 swap/preempt 事件
4. 分析报告：每个实验必须解释"为什么"，不能只列数据

---

## 4. 数据验证检查点

每个实验完成后验证。**验证不通过 → 分析原因 → 修复 → 重跑。**

### 模拟层验证

- precomputed.json 数据完整性（每个 trace 有 requests、hitRate 等字段）
- 命中率曲线单调递增（容量越大命中率越高）
- Agent trace 命中率 > 非 Agent trace（LMCache 99.7% > Bailian 62.2%）

### 验证层验证

- exp1: warm 的 cached_tokens > 0, TTFT 降低
- exp2: block waste 与 mod 16 一致
- exp3: offload-on 的 req_C cached_tokens > offload-off
- exp4: 跨 session 复用率与 L0/L1/L2 层次一致
- exp5: aware 的 cached_tokens > lru
- exp6: swap 的恢复延迟 < recompute 的重算延迟

---

## 4. 异常处理

### 核心原则：主动修复，永不停止，追求正确而非完成任务

所有脚本都可能有问题。发现逻辑错误或更好的实现方式 → 立即改进 → 重新运行。

### 常见异常及自动修复

| 异常 | 自动修复 |
|------|---------|
| Server 启动失败 | 检查日志，kill 占用进程，重试最多 3 次 |
| 请求超时 | 重启 server，重试当前 run |
| 数据异常 | 记录，继续，如果所有 run 异常则标注"需重跑" |
| 脚本报错 | 直接修复脚本，重跑当前实验 |
| GPU 被占用 | kill 残留进程，等待 5 分钟 |
| 脚本卡住 | kill，重启 server，重试 |
| HuggingFace 下载失败 | 切换到方案 2（SWE-bench + 构造 L0/L1） |

---

## 5. 最终产出：论文级实验结果包

所有产出统一放在 `experiments/vllm_kv_cache/results/`：

```
results/
├── README.md                    # 总览索引
├── figures/                     # PDF + PNG 双格式图表
│   ├── simulated/               # 模拟层图表 [SIMULATED]
│   │   ├── hit_rate_vs_capacity.pdf
│   │   ├── agent_vs_nonagent_compare.pdf
│   │   └── token_distribution.pdf
│   ├── measured/                # 验证层图表 [MEASURED]
│   │   ├── exp1_prefix_hit_ttft.pdf
│   │   ├── exp3_offload_compare.pdf
│   │   ├── exp4_l0_l1_l2_reuse.pdf
│   │   ├── exp4_recovery_speed.pdf
│   │   └── exp5_aware_eviction.pdf
│   └── timeline/                # KV usage 时间线图
├── tables/                      # LaTeX 表格
├── analysis.md                  # 完整分析报告
└── key_findings.md              # 核心发现摘要（1 页）
```

### 分析报告每个实验必须覆盖

1. 实验设计回顾：验证了什么假设
2. 原始数据：关键指标数值，**标注来源**
3. 结果分析：数据说明了什么，是否与预期一致
4. 异常说明：哪些数据与预期不符，可能原因
5. 论文写作建议：支持论文哪个论点，建议怎么呈现
6. 后续建议：是否需要补充实验

---

## 6. 时间估算

| 步骤 | 预计时间 | 累计 |
|------|---------|------|
| 前置检查 + 数据准备 | 30 min | 30 min |
| 模拟层分析 | 15 min | 45 min |
| Exp1~5 (Phase 1) | 180 min | 225 min |
| Exp3/4.5/4.6 (Phase 2) | 50 min | 275 min |
| Exp6 preemption 对比 (Phase 3) | 60 min | 335 min |
| 可视化 + 报告 | 25 min | 360 min |
| **总计** | | **~6h** |
