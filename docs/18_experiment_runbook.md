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

具体步骤同之前 runbook（Step 1.1~1.12, 2.1~2.4），此处不重复。

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

## 3. 数据验证检查点

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
| Exp1~5 (Phase 1) | 150 min | 195 min |
| Exp3/4.5/4.6 (Phase 2) | 50 min | 245 min |
| 可视化 + 报告 | 20 min | 265 min |
| **总计** | | **~4.5h** |
