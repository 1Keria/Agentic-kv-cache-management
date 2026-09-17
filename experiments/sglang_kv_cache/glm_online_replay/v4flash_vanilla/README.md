# GLM online open-loop / vanilla 基线

本目录存放 SGLang + GLM-5.1-FP8 对线上 `lt32k` 流量的开环重放结果与图。

## 诊断结论（主文档）

请阅读：

[`docs/GLM_vanilla基线与研究问题收敛.md`](../../../../docs/GLM_vanilla基线与研究问题收敛.md)

## 普通开环重放（vanilla）

每轮输出位于 `openloop_runs/run_glm_openloop_<timestamp>/`（由 `scripts/shell/replay_glm_online.sh` 创建），目录内含 jsonl / meta / summary / report；可用 `OPENLOOP_REPLAY_RUN_ID` 指定时间戳。

历史基线（改目录结构前，仍留在本目录根下）：

- `run_glm_openloop_20260801_053834_*`：`scale=0.02`，`t=3600s`，620/620 ok
- 图：同前缀的 `*_hit_vs_time.png`、`*_vs_online_bars.png`、`*_hit_cdf.png`、`*_cached_vs_prompt.png`、`*_cumulative_hit.png`、`*_ttft_vs_hit.png`

## KV 诊断实验

每轮诊断重放位于 `kv_diag_runs/run_glm_kv_diag_<timestamp>/`，目录内包含：

- `kv_trace.jsonl`：该轮 KV 生命周期原始事件
- `run_glm_kv_diag_<timestamp>.jsonl`：逐请求重放结果
- `*.meta.json` / `*.summary.json`：客户端元数据和汇总
- `*.regret.requests.jsonl` / `*.regret.summary.json`：驱逐归因明细和综合汇总
- `*_report.md`：唯一的综合实验报告
- `*.png`：miss 时间线、重用距离和 TTFT 关系图

运行 `glm51_node0_kv_diag.sh` 后，trace 会先写入 `kv_diag_runs/.staging/`；运行 `replay_glm_online_kv_diag.sh` 时会自动归档到本轮子目录。每轮正式实验前需要重启诊断服务，以保证 KV 状态和 trace 相互隔离。

`run_glm_kv_diag_20260801_081143` 使用旧版 v1 trace，存在 TP 多进程混写，只作为 legacy 原始记录；`run_glm_kv_diag_20260801_091603` 是当前可信的一小时 v2 结果。
