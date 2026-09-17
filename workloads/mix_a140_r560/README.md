# mix_a140_r560

冻结的混合 serving 负载：**140 条 Agent Session + 560 条 Request Session**。jsonl 已冻结；重放默认 Δ=10s/3s，大约 2 小时、高并发。

- Agent：SkillsBench Flash with-skills `runner03` 全部 140 条 `llm_trajectory.jsonl`
- Request：WildChat-1M 对话（丢掉空 user）
- Session 内正文和间隙为原始轨迹。spec 里进场是 Δ=120s/30s；**重放默认压成 10s/3s**（约 2h、高并发），不重造 jsonl。
- 同一 `task_id` 在不同 run 目录下常是**字节相同**的轨迹：140 条里只有 **67 份独特内容**（73 条重复）。重复会在重叠窗口里把前缀命中抬高，不是 140 个不同任务。

## 生成

本目录已冻结，不要覆盖。当前 `build_mix.sh` 默认写出 `workloads/mix_sysdiv_6h`。不要为了改 Δ 重跑构造。重放本份：`bash scripts/shell/replay_mix_workload.sh --workload-dir workloads/mix_a140_r560 --delta-agent-s 10 --delta-request-s 3`。

| 文件 | 是否进 git | 内容 |
|---|---|---|
| `spec.json` | 是 | 配方、有序 Session 列表、到达/间隙规则 |
| `sessions.jsonl` | 是 | 每 Session 一行元数据（无 messages） |
| `manifest.json` | 是 | workload / 源文件 sha256 |
| `workload.jsonl` | 否 | 每一跳的 messages / max_tokens / pre_gap / session_start（约 759 MB） |

## 重放

```bash
bash scripts/shell/v4flash.sh
bash scripts/shell/replay_mix_workload.sh
# dry-run：bash scripts/shell/replay_mix_workload.sh --dry-run
```

目录：`experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_<ts>/`，里面是 `replay.jsonl` / `summary.json` / `meta.json` / `report.md`。

## 本份冻结统计（seed=42）

| | Agent | Request |
|---|---:|---:|
| Session | 140（67 独特轨迹） | 560（337 单轮 / 223 多轮） |
| 调用 | 5508 | 1260 |
| 最后进场（spec） | 4.63 h | 4.66 h |
| 间隙中位（turn≥1） | 0.57 s | 127 s |
| `max_tokens` 中位 | 282 | 318 |

调用占比约 81% Agent / 19% Request。预估墙钟约 5.7h（受几条长 Agent 和 WildChat 空档拖尾）；稳态大约同时 5–10 路 Agent。
