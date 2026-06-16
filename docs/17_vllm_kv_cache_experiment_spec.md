# vLLM KV Cache 实验设计 v3

> 2026-06-17，基于统一配置（GPU KV 6 GiB + CPU offload 8 GiB），覆盖跨 session 复用

## 统一配置

所有实验在同一配置下运行：

| 参数 | 值 | 说明 |
|------|-----|------|
| 模型 | Qwen3-8B bf16 | 单卡 |
| gpu_memory_utilization | 0.3 | GPU KV ≈ 6 GiB (~44K tokens) |
| kv_offloading_size | 8 GiB | CPU KV ≈ 8 GiB (~59K tokens)，总量 ~103K |
| kv_offloading_backend | native | vLLM 内置 CPU offloading |
| block_size | 16 | 显式指定 |
| prefix_caching | ON (xxhash) | APC 开启 |
| kv_cache_metrics_sample | 1.0 | 100% 采样 |
| watermark | 0.02 | 2% 预留 |
| chunked_prefill | ON | 分块 prefill |
| max_model_len | 32768 | |

### 可观测性基础设施（所有实验自动启用）

每个实验自动运行 `KVTimelineCollector`，产出 block 生命周期时间线：

```
采集内容：
  - gpu_cache_usage_perc 随时间变化（分配→占用→释放→APC保留→驱逐→offload恢复）
  - offload_store_bytes / offload_load_bytes（GPU↔CPU 传输量）
  - prefix_cache_hits / prefix_cache_queries（命中率变化）
  - 请求事件对齐（req_start / req_end 标注在时间线上）

产出格式：
  timeline.json — [{t, event, label, gpu_usage, offload_store_bytes, ...}, ...]
```

用法（在实验脚本中）：
```python
timeline = KVTimelineCollector(interval=0.5)  # 每 0.5 秒采样一次
await timeline.start()
# ... 发请求，send_and_record 自动调用 timeline.record_event ...
timeline_data = await timeline.stop()
run_data["timeline"] = timeline_data  # 存入 run JSON
```

启动：`bash scripts/run_vllm_server.sh`（默认就是 8 GiB offloading）

---

## 实验 1：Prefix Cache 基本机制验证

**目的**：验证 APC block-level hash chain 在新配置下正常工作

**设计**：
```
请求 1: [prefix_2000_tokens] + [unique_A_500]    ← 冷启动
请求 2: [prefix_2000_tokens] + [unique_B_500]    ← 应命中 prefix_2000
```

**观测**：
- 请求 2 的 `cached_tokens` ≈ 2000（block_size=16 整除）
- TTFT 降低幅度
- Prometheus `prefix_cache_hits` 增长

**不变**：填充文本足够，关注机制而非语义

---

## 实验 2：Block 粒度浪费量化

**目的**：精确测量 block_size=16 在不同 prefix 长度下的尾部 token 浪费

**设计**：7 组不同 prefix 长度，每组发冷→热两个请求

| prefix_tokens | 预期命中 | 预期浪费 | block 对齐 |
|--------------|---------|---------|-----------|
| 2000 | 2000 | 0 | ✅ 整除 |
| 2001 | 2000 | 1 | ❌ 余 1 |
| 2008 | 2000 | 8 | ❌ 余 8 |
| 2015 | 2000 | 15 | ❌ 余 15 |
| 2016 | 2016 | 0 | ✅ 整除 |
| 100 | 96 | 4 | ❌ 余 4 |
| 99 | 96 | 3 | ❌ 余 3 |

**不变**：填充文本足够

---

## 实验 3：KV Offloading 效果对比

**目的**：对比有无 CPU offloading 时的驱逐恢复行为

**这是新配置下最重要的新实验！**

**设计**：同一请求序列，分别在两种配置下运行：

**配置 A**（有 offloading）：`bash scripts/run_vllm_server.sh`（默认 8 GiB）
**配置 B**（无 offloading）：`KV_OFFLOAD_GIB=0 bash scripts/run_vllm_server.sh`

**请求序列**：
```
Phase 1: 发送 req_A [prefix_A (8000) + unique (500)] → 加载到 GPU
Phase 2: 发送 5 个不同 prefix 的填充请求 (每个 ~8000 tokens)，触发驱逐
Phase 3: 发送 req_C [prefix_A + unique_C] → 观察 prefix_A 是否还能命中
```

**观测对比**：

| 维度 | 无 offloading | 有 offloading (8 GiB) |
|------|-------------|---------------------|
| req_C 的 cached_tokens | 可能=0（prefix_A 被驱逐且无法恢复） | 可能>0（从 CPU 恢复） |
| req_C 的 TTFT | 需完整重算 prefix_A | 只需从 CPU 搬回，更快 |
| GPU KV 使用率 Phase 3 | 被新请求占满 | 同样占满，但 CPU 有备份 |

**预期**：
- 无 offloading：req_C cached_tokens=0，需完整 prefill 8000 tokens
- 有 offloading：req_C cached_tokens≈8000（从 CPU 恢复），TTFT 显著降低

**关键洞察**：offloading 让被驱逐的 prefix block 有"第二次生命"，这正是 agent 场景需要的——L0/L1 prefix 不应被一次驱逐就彻底丢失。

---

## 实验 4：Agent 多 Session 复用模拟（核心实验）

**目的**：用真实 SWE-bench 工作负载模拟多个 agent 实例的 KV 复用

**这是最核心的实验，覆盖 6 种复用场景**：

### 4.1 同 Session 多轮复用

```
Session 1 (sqlfluff repo):
  T1: [L0 + L1_sqlfluff + problem_1]         ← 冷启动，cached=0
  T2: [L0 + L1_sqlfluff + problem_1 + history + new_msg]  ← T1 全部命中
```

**预期**：T2 的 cached_tokens ≈ T1 的全部 prompt_tokens

### 4.2 同项目跨 Session 复用

```
Session 2 (sqlfluff repo, 不同 problem):
  T1: [L0 + L1_sqlfluff + problem_2]         ← 应命中 L0 + L1_sqlfluff
```

**预期**：命中 L0+L1 ≈ (L0_tokens + L1_tokens) // 16 * 16，problem_2 不命中

### 4.3 跨项目跨 Session 复用

```
Session 3 (astroid repo):
  T1: [L0 + L1_astroid + problem_3]           ← 仅命中 L0
```

**预期**：仅命中 L0 ≈ L0_tokens // 16 * 16

### 4.4 多 Session 并行竞争

```
同时发送 3 个请求：
  S_A: [L0 + L1_sqlfluff + problem_A]
  S_B: [L0 + L1_sqlfluff + problem_B]
  S_C: [L0 + L1_astroid + problem_C]
```

**观测**：
- L0 是否被所有请求共享（S_A, S_B, S_C 的 L0 block 应指向同一个物理 block）
- 同项目的 S_A, S_B 是否共享 L1_sqlfluff
- 并发时的命中率和串行时的对比
- GPU KV 使用率变化

### 4.5 驱逐压力下的 L0/L1 保护

```
Phase 1: 发送 5 个 sqlfluff session 的 T1，填满 GPU KV cache
Phase 2: 发送 2 个 astroid session 的 T1，触发 L1_sqlfluff 驱逐
Phase 3: 再发 1 个 sqlfluff session 的 T1，观察 L0+L1_sqlfluff 是否还在
```

**关键观测**：
- 无 offloading 时：L1_sqlfluff 被驱逐后无法恢复，S3 只命中 L0
- 有 offloading 时：L1_sqlfluff 被驱逐到 CPU，S3 可以从 CPU 恢复，命中率更高
- **验证 LRU 是否错误驱逐高价值的共享 prefix**

### 4.6 Offloading 层级恢复速度

```
Phase 1: 发送 req_A (prefix ≈ 6000 tokens)，加载到 GPU
Phase 2: 发送大量不同请求，让 prefix_A 被驱逐到 CPU
Phase 3: 发送 req_C (同 prefix_A)，测量恢复延迟
```

**对比三种恢复路径**：

| 恢复路径 | 预期 TTFT |
|---------|----------|
| GPU 直接命中 | 最快（~50ms） |
| CPU offload 恢复 | 中等（CPU→GPU DMA 传输） |
| 完整重算 prefill | 最慢（需要计算所有 token 的 KV） |

**这是 AgentKV 论文的直接数据支撑**：如果 CPU offload 恢复显著快于完整重算，就证明了 offloading 在 agent 场景的价值。

---

## 实验 5：Agent 组感知驱逐模拟

**目的**：展示"agent-aware 驱逐"比普通 LRU 的优势

**设计**：

两个对比运行（每次重启 server）：

**运行 A**（普通 LRU，默认 vLLM 行为）：
```
Phase 1: 加载 3 个 sqlfluff session 的 T1 (每个 ~6500 tokens, 共 ~19.5K)
Phase 2: 加载 2 个 astroid session 的 T1 (每个 ~6300 tokens, 共 ~12.6K) → 超过 GPU KV 容量，触发驱逐
Phase 3: 发送 sqlfluff session T2 → 观察 L0+L1 命中率
```

**运行 B**（模拟 agent-aware，通过请求时序控制）：
```
Phase 1: 同上
Phase 2: 只加载 1 个 astroid session T1 → 保留更多 sqlfluff 的 L1 block
Phase 3: 发送 sqlfluff session T2 → L0+L1 命中率应该更高
```

**不是改 vLLM 源码**，而是通过控制请求时序来模拟"如果调度器优先保护同组 prefix"的效果。

**关键对比**：运行 A vs B 的 S_sqlfluff T2 的 cached_tokens 差异。

---

## 执行流程

| 顺序 | 实验 | 预计时间 | 说明 |
|------|------|---------|------|
| 1 | 实验 1 | 15 min | 快速验证，确认 APC 正常 |
| 2 | 实验 2 | 30 min | 7 组测量，每组需重启 |
| 3 | 实验 3 | 45 min | 需两次运行（有/无 offloading），各需重启 |
| 4 | 实验 4 | 60 min | 最核心，包含 6 个子场景 |
| 5 | 实验 5 | 30 min | 需两次运行，各需重启 |
| **总计** | | **~3h** | |

每个实验完成后检查：
- `cached_tokens` 是否在合理范围内
- offloading 场景下命中率是否高于无 offloading
- TTFT 在命中/offload恢复/重算三种路径的差异明显

---

## 数据产出

| 文件 | 说明 |
|------|------|
| `experiments/vllm_kv_cache/exp1_*/run_*.json` | 实验 1 数据 |
| `experiments/vllm_kv_cache/exp2_*/run_*.json` | 实验 2 数据 |
| `experiments/vllm_kv_cache/exp3_offload_compare/` | 实验 3 有/无对比 |
| `experiments/vllm_kv_cache/exp4_agent_session/` | 实验 4 6 子场景 |
| `experiments/vllm_kv_cache/exp5_aware_eviction/` | 实验 5 对比 |
| `docs/19_experiment_results.md` | 最终分析报告 |
