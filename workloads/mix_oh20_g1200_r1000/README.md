# mix_oh20_g1200_r1000

压紧进场的三类混合：**20 条独特 OpenHands + 1200 条 GLM 多跳 + 1000 条 Request**。目标是 **高并发大约 2 小时**，不要靠稀疏进场拖墙钟。

相对 `mix_oh20_glm_r8400` 的改动：

- GLM 只抽 `min_turns>=2` 的 1200 条（3253 条候选里 seed=42），不要 1 万条含单跳。
- Request 空档 **cap=30s**，丢掉 **>16 跳** 的超长 WildChat，避免再被一条 107 跳对话拖十几个小时。
- 跳数对齐 `mix_a140_r560`（6768 → 本份 **6999**）。那份 Δ=10/3 墙钟 2.02h；本份更挤（Agent Δ=1s / Request Δ=2s）。
- 20 条 OpenHands 与 `mix_oh20_glm_r8400` 相同（seed=42 先抽 OH），便于对照。

不要覆盖 `mix_a140_r560` / `mix_oh20_glm_r8400` / `mix_sysdiv_6h` 等旧份。不要为了改 Δ 重造 jsonl。

## 生成

```bash
bash scripts/shell/build_mix.sh
```

| 文件 | 是否进 git | 内容 |
|---|---|---|
| `spec.json` | 是 | 配方与 Session 列表 |
| `sessions.jsonl` | 是 | 每 Session 一行元数据 |
| `manifest.json` | 是 | sha256 |
| `workload.jsonl` | 否 | 约 489 MB |

## 重放

```bash
bash scripts/shell/v4flash.sh
bash scripts/shell/replay_mix_workload.sh
```

默认 Δ：**Agent 1s / Request 2s**。OpenHands 与 GLM 都走 `--delta-agent-s`。目录：`experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_<ts>/`。

## 本份冻结统计（seed=42）

| | OpenHands | GLM-Agent | Request |
|---|---:|---:|---:|
| Session | 20（20 独特；runner03 13 / runner05 7） | 1200（全部 n≥2，从 3253 条抽） | 1000（612 单轮 / 388 多轮，最多 15 跳） |
| 调用 | 1126 | 3580 | 2293 |
| 原始跨度中位 | 590 s | 17 s | 0 s |
| 重放最后进场（1s/2s） | 19 s | 20.0 min | 33.3 min |

合计 **2220 Session / 6999 跳**。Request 的 `pre_gap` 已 cap 到 30s（365 条碰到 cap）；按 cap 后的间隙，最晚一条 Session 大约 0.81h 就排完，墙钟主要由推理排队决定，而不是空档。粗算并发：GLM 寿命中位约十几秒、Δ=1s → 十几路 GLM 叠着；20 路 OpenHands 从 t=0 几乎一起进；Request Δ=2s 再叠一层。
