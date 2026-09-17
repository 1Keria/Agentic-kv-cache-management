# OH6：MLP 与 LRU 实验数据

本文只归档 `mix_eval_idle_oh6_r1050_spread` 上的三次可比实验，避免与后续 `agent_050` 比例扫描混淆。

## 1. 实验身份与原始产物

共同 workload：

- [`workloads/mix_eval_idle_oh6_r1050_spread/spec.json`](../workloads/mix_eval_idle_oh6_r1050_spread/spec.json)
- [`workloads/mix_eval_idle_oh6_r1050_spread/README.md`](../workloads/mix_eval_idle_oh6_r1050_spread/README.md)
- `workload.jsonl` SHA256 前缀：`bef88b391c4e29a3`

三次主实验：

| 文中简称 | 策略 | 原始目录 |
|---|---|---|
| LRU 8/31 | LRU | [`run_mix_20260831_oh6_lru`](../experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_20260831_oh6_lru) |
| LRU prof | LRU + 驱逐计时 | [`run_mix_20260903_oh6_lru_prof`](../experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_20260903_oh6_lru_prof) |
| MLP+SWA prof | MLP 同时控制 Full 和 SWA + 驱逐计时 | [`run_mix_20260902_oh6_mlp_swa_prof`](../experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_20260902_oh6_mlp_swa_prof) |

另有一次未启用计时的重复实验：

- [`run_mix_20260902_oh6_mlp_swa`](../experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_20260902_oh6_mlp_swa)

每个目录均包含 `replay.jsonl`、`summary.json`、`meta.json` 和 `report.md`。

## 2. Workload 构成

固定协议：

- DeepSeek-V4-Flash，TP=8；
- `mem-fraction-static=0.45`；
- Session 内闭环；
- `arrival=frozen`，总时间窗 10800 秒，9 个波次；
- 每次重放前 flush cache；
- 1969 次调用、1056 个 Session，三次均 1969/1969 成功、0 错误；
- 6 条 OpenHands 轨迹经过 tool-loop burst 折叠，只保留 47 次调用；
- 1050 条 WildChat Session，共 1922 次调用；
- OpenHands 轮间空档下限为 180 秒，6 条轨迹铺在前 900 秒；
- Request 起点整体后移 180 秒。

### 2.1 “比例”必须区分口径

这份实验**不是按调用次数 5:5**：

| 口径 | OpenHands | Request |
|---|---:|---:|
| 调用次数 | 47（2.39%） | 1922（97.61%） |
| Session 数 | 6（0.57%） | 1050（99.43%） |
| Prompt tokens | 2,349,626（60.90%） | 1,508,567（39.10%） |

它接近的是 **6:4 的 Prompt Token 构成**，而不是 5:5 的调用构成。OpenHands 单次 Prompt 很大，因此虽然调用很少，却主导了 token-weighted hit。

## 3. 策略配置

LRU 两次实验使用相同的标准 Radix/SWA LRU。

`MLP+SWA prof` 使用当时的基础 checkpoint：

```text
models/MLP/checkpoints/leaf_mlp.pt
H = 29.93s / 198.03s / 2370.90s
α = (1, 1, 1)
λ = 0.05
```

因此该次实验中 `π` 基本退化为 `p(H3)`。

```text
SWA 排序：π → prefix_depth → NetValue → KVSize
```

## 4. 核心命中结果

| 指标 | LRU 8/31 | LRU prof | MLP |
|---|---:|---:|---:|
| 全局 token-weighted hit | 0.363743 | 0.358833 | **0.509718** |
| Cached / Prompt tokens | 1,403,392 / 3,858,193 | 1,384,448 / 3,858,193 | **1,966,592 / 3,858,193** |
| OpenHands token-weighted hit | 0.357368 | 0.357368 | **0.616241** |
| OpenHands cached tokens | 839,680 | 839,680 | **1,447,936** |
| OpenHands 会话内 hit | 0.379085 | 0.379085 | **0.661290** |
| OpenHands 每请求 hit p50 | 0.096021 | 0.096021 | **0.812968** |
| Request token-weighted hit | 0.373674 | 0.361116 | 0.343807 |
| Request cached tokens | 563,712 | 544,768 | 518,656 |
| Request 会话内 hit | 0.499274 | 0.482495 | 0.459368 |
| 全局 cold-miss rate | 0.798883 | 0.805993 | 0.819198 |

以同样带 profiling 的 `LRU prof` 为基准：

- 全局 hit：`+0.150885`，相对提升 **42.05%**；
- OpenHands hit：`+0.258873`，相对提升 **72.44%**；
- OpenHands 会话内 hit：`+0.282205`，相对提升 **74.44%**；
- Request hit：`-0.017309`，相对下降 **4.79%**；
- 全局多命中 582,144 tokens；
- OpenHands 多命中 608,256 tokens，Request 少命中 26,112 tokens。

全局 cold-miss rate 反而上升 1.32 个百分点。这不与 token hit 上升冲突：MLP+SWA 让更多小 Request 完全 miss，但保住了少量、体积很大的 OpenHands 前缀。

## 5. 延迟结果

### 5.1 全局

| 指标 | LRU 8/31 | LRU prof | MLP+SWA prof |
|---|---:|---:|---:|
| TTFT p50 (ms) | 323.150 | 322.910 | 329.929 |
| TTFT p90 (ms) | 1343.315 | 964.948 | 1189.136 |
| TTFT mean (ms) | 641.357 | 535.169 | 587.022 |
| TPOT p50 (ms) | 17.907 | 18.101 | 17.983 |
| e2e p50 (ms) | 7051.192 | 7112.345 | **7029.536** |
| e2e p90 (ms) | 15981.704 | 16044.901 | **15643.135** |
| e2e mean (ms) | 8013.749 | 8062.666 | **7847.961** |

相对 `LRU prof`：

- TTFT p50 `+2.17%`，基本持平；
- TTFT p90 `+23.23%`，该次更差，但两次 LRU 自身的 p90 波动也很大；
- e2e p50 `-1.16%`；
- e2e p90 `-2.50%`；
- e2e mean `-2.66%`。

全局指标被 1922 次 Request 主导，不能体现 47 次 OpenHands 的延迟变化。

### 5.2 OpenHands

| 指标 | LRU 8/31 | LRU prof | MLP+SWA prof |
|---|---:|---:|---:|
| TTFT p50 (ms) | 1589.046 | 1485.065 | **1155.500** |
| TTFT p90 (ms) | 4737.007 | 4315.166 | **3246.197** |
| TTFT mean (ms) | 2162.546 | 2076.614 | **1649.532** |
| e2e p50 (ms) | 6039.205 | 5483.146 | **4612.702** |
| e2e mean (ms) | 6382.626 | 5992.252 | **5431.549** |

相对 `LRU prof`，OpenHands TTFT p50 降低 329.565ms（**-22.19%**）。相对 8/31 LRU 则降低 433.546ms（**-27.28%**）。

## 6. Profiling 数据

当时从服务端 TP0 的累计驱逐日志提取：

| 指标 | LRU prof | MLP+SWA prof |
|---|---:|---:|
| `evict()` 次数 | 2820 | 2600 |
| 累计 `evict()` 时间 | 29.6s | 20.5s |
| 其中 MLP 特征、前向与聚合 | 0 | 6.3s |
| MLP / 驱逐时间 | 0 | 约 30% |
| 驱逐 / 11213s 墙钟 | 约 0.26% | 约 0.18% |
| MLP / 墙钟 | 0 | 约 0.056% |

MLP 单次打分通常约 5–7ms。尽管加入了打分，MLP 运行的总驱逐时间仍低于 LRU，因为命中提高后减少了分配和驱逐次数。

注意：这些 profiling 累计量来自实验结束时抓取的服务端日志，未写入 run 目录中的 `summary.json`；目录内持久化的是请求级重放指标。

## 7. 重复性

未启用 profiling 的 `run_mix_20260902_oh6_mlp_swa` 得到：

| 指标 | MLP+SWA | MLP+SWA prof |
|---|---:|---:|
| 全局 hit | 0.530885 | 0.509718 |
| OpenHands hit | 0.644787 | 0.616241 |
| OpenHands 会话内 hit | 0.691982 | 0.661290 |
| Request hit | 0.353480 | 0.343807 |
| OpenHands TTFT p50 (ms) | 1042.705 | 1155.500 |

两次方向一致：显著保留 OpenHands SWA、轻微牺牲 Request；约 2–3 个百分点的绝对差异应视为单次运行波动，不能归因于 profiling 本身，因为计时代码累计只占 6.3 秒。

## 8. 解释与使用边界

这份实验能够支持：

1. V4-Flash 中只控制 Full 不够，SWA 墓碑顺序会直接决定可报告的长前缀命中；
2. MLP+SWA 能用少量 Request 命中换取大体积 OpenHands 前缀，从而提高总体 token hit；
3. 收益确实落到了 OpenHands TTFT，而不仅是缓存计数；
4. MLP 计算不是端到端延迟瓶颈。

这份实验不能直接支持：

1. **不能称为 5:5 调用比例实验**；Agent 调用占比只有 2.39%；
2. 6 条 OpenHands 和 Request 都来自旧模型开发数据池，不是严格 held-out 泛化测试；
3. OpenHands 只有 47 个请求、6 条轨迹，样本量不足以单独形成论文主结果；
4. workload 人为折叠 tool-loop，并把长空档抬到至少 180 秒，属于机制压力夹具；
5. `α=(1,1,1)` 时只实际使用最长 horizon，不能据此证明三个 horizon 的时间形状都有贡献；
6. 不能用全局 hit 单独宣称“双边都改善”，因为 Request hit 明确下降。

因此，这份数据适合作为 **SWA 机制实验与开销实验**，不应替代当前零交集、按调用比例构造的最终比例扫描。
