# V4-Flash + GLM 线上数据：原版基线

> 2026-07-31 · 本轮只做一件事：vanilla 跑 GLM 原数据，看问题在哪。

## 目标

1. 起 **V4-Flash vanilla**（LRU，关 PF）
2. 重放 **GLM 线上原数据**（不合成、不用 lmcache）
3. 从结果写清痛点

## 怎么跑

| 项 | 值 |
|---|---|
| 起服 | `bash scripts/shell/v4flash_vanilla.sh`（`:30000`，tp8） |
| 数据 | `third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl` |
| 客户端 | `bash scripts/shell/replay_glm_online.sh` → `scripts/python/replay_glm_online_openloop.py` |
| 产出 | `experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/` |

例：

```bash
bash scripts/shell/replay_glm_online.sh
# 参数仅 scale-factor / time-in-secs（与 trace-replayer 一致）；从文件头开环按时间发
```

## 数据与重放（学 trace-replayer）

- 从文件头按 `start_time` 开环发，**不等响应、不限 inflight**
- `--scale-factor` + `--time-in-secs` 控负载与时长
- `max_tokens` = 原 `completion_tokens`（无 slack）
- 缩放只当负载旋钮；评 Serving/KV，不评答案

## 产出文件

目录：`experiments/sglang_kv_cache/glm_online_replay/v4flash_vanilla/`

| 文件 | 内容 |
|---|---|
| `run_<ts>.jsonl` | **每请求一行**明细（主落盘） |
| `run_<ts>.summary.json` | 汇总指标（p50/p90/p99 等） |
| `run_<ts>_report.md` | 给人看的短报告 |
| `run_<ts>.meta.json` | 复现参数：model / scale / time / 起点 / 数据路径 |

### 每请求字段（jsonl）

调度：`trace_id`, `start_time_orig`, `t_sched_ms`, `s_time_ms`, `s_time_drift_ms`, `e_time_ms`  
延迟：`ttft_ms`, `tpot_ms`, `e2e_ms`（需 **stream**）  
用量：`prompt_tokens`, `cached_tokens`, `completion_tokens`, `max_tokens`  
结果：`status` / `error`  
派生：`cache_hit_ratio = cached/prompt`（有则写）

### summary 必报

| 类 | 指标 |
|---|---|
| 完整性 | n_issued / n_ok / n_err（timeout/4xx/…）/ wall_clock_s |
| 延迟 | TTFT、TPOT、e2e 的 p50/p90/p99 |
| KV | cached/prompt 总量与 hit 率 p50/p90；冷 miss 粗算（hit≈0） |
| 调度 | `s_time_drift` p50/p90（客户端是否跟得上开环） |
| 吞吐 | req/s、output tok/s（ok 集合） |

诊断用这三句：伤在哪 → 什么水位（scale/并发）→ 假说。

## 不做

合成混合负载 · 部署 GLM-5.1 · 改底部 cache · session 闭环重放
