# GLM 线上流量 Vanilla 基线诊断与研究问题收敛

> 日期：2026-08-01  
> 状态：**D1 基线已完成一轮有效开环；进入 D2 诊断收敛**  
> 主结果：`experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/run_glm_openloop_20260801_053834_*`  
> 服务：GLM-5.1-FP8，双节点 TP=16，SGLang radix LRU，`--enable-cache-report`

---

## 1. 一句话结论

同一批真实 GLM 线上请求在生产环境中有很高的前缀复用（token-weighted hit ≈ **83%**），但在当前有限 KV 的 vanilla SGLang 开环重放中只剩约 **35%**；miss 与 TTFT 强相关。  
主因是**本地 KV 容量不足以保住长前缀**，不是重放时间不够，也不宜据此直接得出「必须先区分 Agent/Request」的系统设计。

---

## 2. 实验设置

| 项 | 值 |
|---|---|
| 数据 | `third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl` |
| 重放方式 | 开环，按原始 `start_time` 调度；**不改数据层、不限 `max-inflight`** |
| 模型 / 服务 | `glm-5.1-fp8`，`http://127.0.0.1:30000` |
| scale_factor | `0.02`（放慢，使本地集群可承载文件头突发） |
| 有效长跑 | 1800s（479 req）与 3600s（620 req） |
| 前置操作 | 长跑前 `abort_all` + `flush_cache`，从空 KV 起步 |

说明：

- 对比对象是**线上原始 `usage.cached_tokens`**，不是 DeepSeek-V4 等其它模型的历史重放。
- `scale=1` 会在文件头把本地服务打爆（queue 上百、TTFT 数百秒），该轮指标作废；有效结论以不过载的 `0.02` 长跑为准。

---

## 3. 主结果（3600s / n=620）

来源：`run_glm_openloop_20260801_053834_report.md` / `latest_report.md`

### 3.1 完整性与调度

| 指标 | 值 |
|---|---|
| issued / ok / err | 620 / 620 / 0 |
| s_time_drift p50/p90 | 1.1 / 4.9 ms |
| TTFT p50/p90/p99 | 2.70 / 7.43 / 18.5 s |
| TPOT p50 | 25.7 ms |

调度漂移很小 → 长尾主要来自服务端，不是客户端跟不上。

### 3.2 与线上同窗口对照

| 指标 | Vanilla 重放 | 线上原始（同前 620 条） |
|---|---:|---:|
| token-weighted hit | **0.347** | **0.833** |
| per-req hit p50 | 0.268 | 0.941 |
| per-req hit p90 | 0.797 | 0.992 |
| cold miss rate | 0.245 | ~0.006 |
| cached / prompt | 4.86M / 14.02M | （同窗更高） |

1800s（479 req）与 3600s（620 req）命中几乎相同（TW ≈ 0.351 vs 0.347），说明**加长时间几乎不抬升命中**。

### 3.3 miss 的代价（TTFT）

逐请求上，TTFT 与「未命中 token 数」的相关性强于与总 prompt 长度的相关性（约 0.46 vs 0.27）。

按命中率粗分（同跑）：

| 命中率区间 | TTFT p50（量级） |
|---|---|
| ~0 | ~3.4 s |
| 25%–50% | ~2.7 s |
| 50%–75% | ~1.9 s |
| 75%–100% | ~0.8 s |

结论：对这种长上下文、短输出流量，**提高有效 KV 保留率有明确 TTFT 收益**。

---

## 4. 图示

目录：`experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/`

| 图 | 文件 | 说明 |
|---|---|---|
| 命中随时间 | […_hit_vs_time.png](../experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/run_glm_openloop_20260801_053834_hit_vs_time.png) | 滚动 TW 钉在 ~0.35，远低于线上 0.83 |
| 与线上柱对比 | […_vs_online_bars.png](../experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/run_glm_openloop_20260801_053834_vs_online_bars.png) | TW / p50 hit / cold 三项差距 |
| 命中 CDF | […_hit_cdf.png](../experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/run_glm_openloop_20260801_053834_hit_cdf.png) | 重放大量低命中；线上集中高命中 |
| cached vs prompt | […_cached_vs_prompt.png](../experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/run_glm_openloop_20260801_053834_cached_vs_prompt.png) | 大量 cold；部分命中停在共享前缀量级 |
| 累计命中 | […_cumulative_hit.png](../experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/run_glm_openloop_20260801_053834_cumulative_hit.png) | 重放与线上很快各自稳态，之后平行 |
| TTFT vs hit | […_ttft_vs_hit.png](../experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/run_glm_openloop_20260801_053834_ttft_vs_hit.png) | 高命中对应更低、更稳的 TTFT |

---

## 5. 原因分析

### 5.1 主因：本地 KV 有限（容量驱逐）

- 本地 KV 池约 **21 万 token** 量级；单条 prompt 中位约 **2.3 万**。
- 同会话连续轮中，上一轮 prompt 中位 ~23k，但下一轮 `cached_tokens` 中位常只有 **~7k**（更像 system/tools 共享前缀，而非整段历史）。
- 连续轮样本里，多数未能保住上一轮 ≥80% 前缀；短空档档位同样偏低 → **不是「等太久才丢」，而是池子里存不下**。
- 1800s → 3600s 命中几乎不变，进一步排除「重放时间不够」作为主解释。

### 5.2 次要因素（存在，但不是钉住 0.35 的主因）

| 因素 | 说明 |
|---|---|
| 冷启动 / 窗前历史 | 线上日志截自已运行系统；部分请求在线上已有窗前 KV，重放从空 cache 开始 |
| 半截会话采样 | 数据集按请求采样，`trace_id` 非 session；窗口内未必包含前序轮 |
| scale=0.02 | 放慢到达以适配容量；会加重驱逐机会，但短空档样本已显示容量瓶颈 |
| 分词/模板偏差 | prompt 均长略低于线上（~22.8k vs ~23.4k），不足以解释 83%→35% |
| 线上架构未知 | 生产可能有更大容量、亲和路由、分层 cache 等，命中上界未必能在单实例追平 |

### 5.3 当前还不能直接断言的事

- LRU「策略错误」已充分证明（缺驱逐→再访问的直接日志）；
- Agent KV 被普通 Request 挤掉（本数据主体即为 tool/agent 流量，不是双边混跑）；
- 某 priority 公式一定能恢复线上 83% 命中；
- 必须依赖客户端 `traffic_class` 字段才能做系统。

---

## 6. 对系统设计与论文 claim 的收敛

### 6.1 不宜继续作为主路径的设计

「提取信息区分 Agent / Request → 差异化保护 Agent」在无标签真实流量上存在三选二矛盾：

1. 策略区分 Agent / Request  
2. 不要求客户端提供类别  
3. 只在无标签真实流量上评测  

三者不能同时严格成立。仅靠 tool_call、频率、输出长度做启发式分类，容易变成循环论证，审稿说服力不足。

### 6.2 更干净的研究问题

> **在有限 KV 容量下，vanilla cache 为什么没有保住那些稍后会再次使用、且重计算代价很高的前缀？**  
> 系统贡献应是：无需客户端标签，基于**在线复用证据与重计算成本**做资源感知的 KV 保留/驱逐。

Agent 是该工作负载的重要来源与动机叙述，但**不是**系统必须识别的类别。普通请求若也有高价值前缀，同样应受益。

### 6.3 建议的证据结构

| 实验 | 数据 | 作用 |
|---|---|---|
| 机制/归因 | 来源明确的真实 Agent + Request 轨迹受控混跑 | 说明为什么有效、对哪类流量有效 |
| 真实流量 | 未修改的 GLM 线上 trace（本基线） | 证明不依赖标签、在自然分布中仍有效 |
| 压力 | 调时间缩放 / KV 容量 | 找策略生效边界 |
| 消融 | 去掉成本、频率、衰减或水位感知 | 证各组件作用 |

可写的 claim 方向（草案）：

> Agent 工作负载具有显著的跨请求前缀复用，但统一 LRU 难以表达其未来价值。我们提出一种无需客户端标签、基于在线复用证据与重计算成本的资源感知 KV 策略；在真实 Agent/Request 受控混跑中改善连续性，并在未标注生产流量上提升整体性能。

---

## 7. 下一步（D2 → D3）

优先级从高到低：

1. **补证据链**：记录/推断「某前缀被驱逐 → 较短 reuse distance 内再次访问」，把「命中差」落到「可优化的错误驱逐」。  
2. **容量扫描**：在相同开环流量下改变有效 KV（或 `mem-fraction-static` / 并发负载），画 hit–capacity 曲线，量化容量弹性。  
3. **策略原型**：在 SGLang 现有 priority / eviction 接口上做 cost-aware / reuse-aware，与 LRU 对照（先不要上复杂分类器）。  
4. **双边机制实验**：用 Codex / Claude Code / SWE-agent 等来源明确轨迹 + 真实 Request trace 做受控混跑，支撑论文动机中的混跑叙事。  
5. **服务侧指标**：长跑时导出 `token_usage`、`kv_evictable_tokens`、hit rate 时间序列，与请求级 jsonl 对齐。

---

## 8. 相关路径速查

| 类型 | 路径 |
|---|---|
| 最新报告 | `experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/latest_report.md` |
| 主跑 summary | `.../run_glm_openloop_20260801_053834.summary.json` |
| 逐请求 | `.../run_glm_openloop_20260801_053834.jsonl` |
| 图 | `.../hit_vs_time.png` 等（见 §4） |
| 重放脚本 | `scripts/shell/replay_glm_online.sh` |
| 清任务 / 清 KV | `scripts/shell/cleartask.sh`、`scripts/shell/clearkv.sh` |
| 数据说明 | `third_party/glm-5dot1_onlinedata/data_report.md` |
| 原规划（部分表述待按本文收敛修订） | `docs/混合流量KV策略规划.md` |
