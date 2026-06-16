# vLLM KV Cache 实验规划

> 日期：2026-06-16
> 目标：通过实际部署 vLLM，模拟多用户/多 session 请求场景，观察和量化 KV cache 管理行为
> 前置文档：`notes/vllm_kv_cache.md`（源码分析）、`docs/14_kv_cache_source_analysis.md`（四框架对比）

---

## 1. 环境现状

| 项目 | 值 |
|------|-----|
| GPU | 8× H800 (80GB each) |
| NVIDIA Driver | 550.90.07 → 最高支持 **CUDA 12.4** |
| conda env | `agentkv_zls` (Python 3.11) |
| PyTorch | 2.11.0+cu130 (编译 CUDA 13.0) |
| vLLM | **未安装** |
| 模型 | Qwen3-8B（本地已有） |
| **问题** | **PyTorch CUDA 13.0 > Driver CUDA 12.4，GPU 不可用** |

---

## 2. 安装方案

### 方案 A：在现有 env 中降级 PyTorch + 安装 vLLM

```bash
# 降级 PyTorch 到 CUDA 12.4 兼容版本
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
# 安装 vLLM（pip install，非源码编译）
pip install vllm
```

- 优点：快，直接用
- 缺点：pip 安装的 vLLM 不是我们分析的那个源码版本；降级 PyTorch 可能影响 SGLang（如果已装）

### 方案 B：新建 conda env 专门跑 vLLM 实验（推荐）

```bash
conda create -n vllm_exp python=3.11 -y
conda activate vllm_exp
pip install vllm  # 自动安装兼容的 PyTorch
```

- 优点：不影响现有环境，干净隔离
- 缺点：多一个环境

### 方案 C：从源码编译 vLLM（用我们分析的那个版本）

```bash
# 新建 env，安装 CUDA 12.4 兼容的 PyTorch
conda create -n vllm_src python=3.11 -y
conda activate vllm_src
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
# 从源码编译 vLLM
cd Engine/vllm && pip install -e .
```

- 优点：用的是我们分析过的源码，可以加日志/打 patch
- 缺点：编译慢，可能遇到依赖问题

### 推荐策略

**先方案 B 跑通实验**，拿到数据、验证实验设计。后续如果需要打 patch 观察更细粒度的 block 行为，再切到方案 C 源码编译。

---

## 3. 实验设计

### 实验 1：Prefix Cache 命中观察

**目的**：验证 APC 的 block-level hash chain 命中行为

**请求设计**：
```
请求 A: [system_prompt (2000 tokens)] + [task_A (500 tokens)]
请求 B: [system_prompt (2000 tokens)] + [task_B (500 tokens)]
```

**步骤**：
1. 启动 vLLM，开启 prefix caching：`--enable-prefix-caching`
2. 先发请求 A，等完成
3. 再发请求 B
4. 观察 B 的 `num_computed_tokens`、TTFT、block 命中数

**预期**：
- 请求 B 的前 `floor(2000/16) * 16 = 2000` tokens 命中（125 个 block）
- 最后 0 个 token 浪费（2000 恰好是 16 的倍数）
- TTFT 应显著降低

**变体**：system_prompt 长度 = 2001 tokens（不对齐 block_size）
- 预期：前 `floor(2001/16) * 16 = 2000` tokens 命中（125 个 block）
- 最后 1 个 token 无法命中，需要重新计算
- 浪费：1/16 block

**观测指标**：
- `vllm_num_cache_hits`（Prometheus metric）
- TTFT（Time To First Token）
- `num_computed_tokens`（日志）
- GPU cache usage

---

### 实验 2：Block-level 粒度浪费量化

**目的**：量化 block_size=16 在 agent 场景下的浪费

**请求设计**：构造不同长度的 system_prompt，观察尾部 block 的浪费

| system_prompt 长度 | 完整 block 数 | 尾部有效 token | 浪费 token | 浪费率 |
|-------------------|-------------|--------------|-----------|--------|
| 2000 | 125 | 0 | 0 | 0% |
| 2001 | 125 | 1 | 15 | 0.75% |
| 2008 | 125 | 8 | 8 | 0.4% |
| 2015 | 125 | 15 | 1 | 0.05% |
| 2016 | 126 | 0 | 0 | 0% |

**步骤**：
1. 对每个长度，发送两个共享 prefix 的请求
2. 记录第二个请求的 cache hit tokens
3. 计算 `waste = (prefix_len % block_size)` 如果不为 0

**预期**：vLLM 只能命中完整 block，尾部不足一个 block 的 token 需要重算。

**与 SGLang 对比**：SGLang 的 token-level 匹配可以命中到任意位置，无此浪费。

---

### 实验 3：LRU 驱逐行为

**目的**：观察内存压力下，共享 prefix block 是否被 LRU 驱逐

**请求设计**：
```
请求 A: [prefix_1 (1000 tokens)] + [task_A (500 tokens)]
请求 B: [prefix_2 (1000 tokens)] + [task_B (500 tokens)]  # 不同 prefix
请求 C: [prefix_1 (1000 tokens)] + [task_C (500 tokens)]  # 与 A 共享 prefix
```

**步骤**：
1. 发送 A，完成后 prefix_1 的 block 在 free queue 尾部
2. 发送大量不同 prefix 的请求，制造内存压力
3. 发送 C，观察 prefix_1 是否还在 cache 中

**预期**：
- 如果内存压力不大：prefix_1 的 block 仍在 free queue，C 可以命中
- 如果内存压力大：prefix_1 的 block 被 LRU 驱逐，C 无法命中
- **关键观察**：共享 prefix（被多个请求 touch 过的 block）是否比独占 prefix 更晚被驱逐？

**变体**：限制 GPU cache 大小（`--gpu-memory-utilization 0.3`），加速驱逐

---

### 实验 4：多 Session 模拟（Agent 场景）

**目的**：模拟 agent 多轮对话 + 跨 session 共享，观察 KV cache 复用

**请求设计**：
```
Session 1 (agent A, project sympy):
  Turn 1: [system + tools + CLAUDE.md + problem_sympy_1]     ≈ 20,000 tokens
  Turn 2: [system + tools + CLAUDE.md + problem_sympy_1 + history_1 + new_msg_1]  ≈ 21,000 tokens
  Turn 3: [system + tools + CLAUDE.md + problem_sympy_1 + history_1+2 + new_msg_2] ≈ 22,000 tokens

Session 2 (agent B, same project sympy):
  Turn 1: [system + tools + CLAUDE.md + problem_sympy_2]     ≈ 20,000 tokens
  # 共享 system + tools + CLAUDE.md ≈ 18,990 tokens (L0+L1)

Session 3 (agent C, different project django):
  Turn 1: [system + tools + CLAUDE.md_django + problem_django_1]  ≈ 20,000 tokens
  # 仅共享 system + tools ≈ 17,000 tokens (L0)
```

**步骤**：
1. 按顺序发送 Session 1 的 Turn 1, 2, 3
2. 发送 Session 2 的 Turn 1
3. 发送 Session 3 的 Turn 1
4. 记录每个请求的 cache hit tokens 和 TTFT

**预期**：
- Session 1 Turn 2 → 完全命中 Turn 1（prefix = Turn 1 全部内容）
- Session 1 Turn 3 → 完全命中 Turn 1+2
- Session 2 Turn 1 → 命中 L0+L1（约 18,990 tokens），但受 block_size 对齐影响
- Session 3 Turn 1 → 命中 L0（约 17,000 tokens），但受 block_size 对齐影响

**关键观察**：
- 跨 session 的 prefix 命中率（与源码分析中的 LCP 数据对比）
- Block-level 粒度导致的尾部浪费
- Session 间隔期间 prefix 是否被驱逐

---

### 实验 5：并发请求下的调度行为

**目的**：观察多个 agent session 并发时，调度器如何处理

**请求设计**：
```
同时发送 5 个请求：
  请求 1-3: 共享 prefix_A (同项目 agent)
  请求 4-5: 共享 prefix_B (另一项目 agent)
```

**步骤**：
1. 同时发送 5 个请求
2. 观察调度顺序（FCFS vs cache-aware）
3. 观察是否出现 prefix 重复计算

**预期**：
- vLLM FCFS 调度：按到达顺序处理，不考虑 prefix 共享
- 同 prefix 的请求如果连续调度，可以共享 block（第二个请求命中第一个的 block）
- 如果交替调度（A, B, A, B, A），可能导致 prefix 重复计算

---

## 4. 观测手段

### 4.1 vLLM 自带 metrics（Prometheus 格式）

启动时加 `--log-level info`，访问 `http://localhost:8000/metrics`：

关键指标：
- `vllm:num_cache_hits` — prefix cache 命中 token 数
- `vllm:num_cache_misses` — prefix cache 未命中 token 数
- `vllm:gpu_cache_usage_perc` — GPU KV cache 使用率
- `vllm:avg_generation_throughput` — 平均生成吞吐
- `vllm:num_requests_running` — 运行中请求数
- `vllm:num_requests_waiting` — 等待中请求数

### 4.2 API response 信息

vLLM OpenAI-compatible API 返回：
- `usage.prompt_tokens` — 输入 token 数
- `usage.completion_tokens` — 输出 token 数
- `usage.prompt_tokens_details.cached_tokens` — **缓存命中的 token 数**（关键！）
- TTFT 可通过 streaming response 的首个 chunk 时间计算

### 4.3 日志

`--log-level debug` 可以看到更详细的 block 分配/释放信息。

### 4.4 打 patch 加日志（方案 C 专属）

在以下文件中加 print/log：
- `vllm/v1/core/block_pool.py` — block 分配/释放/驱逐
- `vllm/v1/core/single_type_kv_cache_manager.py` — `find_longest_cache_hit()` 命中详情
- `vllm/v1/core/kv_cache_manager.py` — `get_computed_blocks()` 结果
- `vllm/v1/core/sched/scheduler.py` — 调度决策

---

## 5. 实验脚本设计

### 5.1 启动 vLLM server

```bash
python -m vllm.entrypoints.openai.api_server \
  --model /share/dai-sys/.cache/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218/ \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.9 \
  --max-model-len 32768 \
  --port 8000 \
  --log-level info
```

### 5.2 客户端请求脚本

使用 OpenAI Python SDK：

```python
from openai import OpenAI
import time

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")

def send_request(messages, max_tokens=100):
    start = time.time()
    response = client.chat.completions.create(
        model="Qwen3-8B",
        messages=messages,
        max_tokens=max_tokens,
        temperature=0,
    )
    ttft = time.time() - start  # 近似 TTFT（含网络延迟）

    cached = response.usage.prompt_tokens_details.cached_tokens
    total = response.usage.prompt_tokens
    hit_rate = cached / total if total > 0 else 0

    return {
        "ttft": ttft,
        "prompt_tokens": total,
        "cached_tokens": cached,
        "hit_rate": hit_rate,
        "completion_tokens": response.usage.completion_tokens,
    }
```

### 5.3 构造不同 prefix 的请求

```python
# 构造固定长度的 system prompt
def make_system_prompt(num_tokens):
    # 用重复文本填充到目标 token 数
    # 需要用 tokenizer 精确控制
    ...

# 构造 agent session 的多轮对话
def make_agent_session(system_prompt, problem_statement, num_turns=3):
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": problem_statement})
    for i in range(num_turns - 1):
        messages.append({"role": "assistant", "content": f"Response {i+1}"})
        messages.append({"role": "user", "content": f"Follow-up {i+1}"})
    return messages
```

---

## 6. 预期产出

| 产出 | 说明 |
|------|------|
| **实验数据** | 每个实验的 TTFT、cache hit rate、block 分配详情 |
| **对比表** | vLLM APC vs 理论最优（token-level）的复用率差异 |
| **Block 浪费量化** | 不同 prefix 长度下的 block 尾部浪费 |
| **驱逐行为记录** | 内存压力下 prefix block 的驱逐顺序 |
| **Agent 场景复用率** | 模拟 SWE-bench 场景的跨 session KV cache 复用率 |
| **实验报告** | `docs/15_vllm_kv_cache_experiment.md` |

---

## 7. 时间规划

| 阶段 | 内容 | 预计时间 |
|------|------|---------|
| 环境搭建 | 新建 conda env + 安装 vLLM + 验证 GPU 可用 | 1-2h |
| 实验 1-2 | Prefix cache 命中 + Block 粒度浪费 | 2-3h |
| 实验 3 | LRU 驱逐行为 | 1-2h |
| 实验 4-5 | Agent 场景模拟 + 并发调度 | 2-3h |
| 数据分析 + 报告 | 整理数据、撰写报告 | 2h |
| **总计** | | **8-12h** |
