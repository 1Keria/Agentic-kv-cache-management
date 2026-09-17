# mix_a8_r32

冻结的混合 serving 负载：**8 条 Agent Session + 32 条 Request Session**。

- Agent：SkillsBench Flash with-skills `runner03` 的 OpenHands `llm_trajectory.jsonl`
- Request：WildChat-1M 对话（丢掉空 user）
- Session 内正文和间隙为原始轨迹；Session **进场时刻是实验旋钮**（默认 staggered：Agent Δ=15s，Request Δ=5s；也可 poisson）。
- `traffic_class` 只用于评测分组；LRU 重放不送给 cache 策略

## 生成

```bash
bash scripts/shell/build_mix.sh
```

| 文件 | 是否进 git | 内容 |
|---|---|---|
| `spec.json` | 是 | 配方、有序 Session 列表、到达/间隙规则 |
| `sessions.jsonl` | 是 | 每 Session 一行元数据（无 messages） |
| `manifest.json` | 是 | workload / 源文件 sha256 |
| `workload.jsonl` | 否 | 每一跳的 messages / max_tokens / pre_gap / session_start |

当前默认构造脚本写出的是 `workloads/mix_oh54_g54_r432`。本目录是更早的小份冻结，不要覆盖。重放小份时把 `--workload-dir` 指回来即可。

## 重放

产出：目录内 `replay.jsonl` / `summary.json` / `meta.json` / `report.md`。

```bash
bash scripts/shell/v4flash.sh
bash scripts/shell/replay_mix_workload.sh
# 改到达：改脚本里的 --arrival / --delta-*，或接到后面：
bash scripts/shell/replay_mix_workload.sh --arrival staggered --delta-agent-s 5 --delta-request-s 2
bash scripts/shell/replay_mix_workload.sh --arrival poisson --mean-gap-agent-s 15 --mean-gap-request-s 5 --arrival-seed 42
# dry-run：bash scripts/shell/replay_mix_workload.sh --dry-run
```

目录：`experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_<ts>/`

Session 内闭环：上一跳返回后再 `sleep(pre_gap)`。jsonl 每请求一行，字段与 GLM 重放相同，并多 `traffic_class` / `session_id` / `turn_index` / `pre_gap_s`。

## 本份冻结统计（seed=42）

| | Agent | Request |
|---|---:|---:|
| Session | 8 | 32（26 单轮 / 6 多轮） |
| 调用 | 224 | 61 |
| 间隙中位 | 0.59 s | 85 s |
| `max_tokens` 中位 | 305 | 227 |

`workload.jsonl` 约 24 MB。调用占比约 79% Agent / 21% Request。
