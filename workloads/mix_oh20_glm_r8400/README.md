# mix_oh20_glm_r8400

压紧进场的三类混合：**20 条独特 OpenHands + 10073 条 GLM 推断 Session + 8400 条 Request**。用来撑 **高并发大约 6–8 小时**（不是把进场拉开拖时间）。

- **OpenHands**：三个 Flash 包去重后的 108 条里 seed=42 抽 **20**（runner03 13 / runner05 7）。同构脚手架，只适当加一点长 Session 顶 KV。
- **GLM-Agent**：线上 jsonl **全部**推断链（`min_turns=1`，10073 条；其中 3253 条 n≥2，6820 条单跳）。推断方法仍是首条 user hash + messages exact prefix，不是官方 session 键。
- **Request**：WildChat 8400 条（5123 单轮 / 3277 多轮）。
- 重放默认 **Agent Δ=2s / Request Δ=3s**：GLM 最后进场约 5.6h，Request 约 7.0h，加上尾部大约 7–8h。不要为了改 Δ 重造 jsonl。

并发粗算：GLM 多跳寿命中位约 25s、Δ=2s → 大约十来路 GLM 叠着；20 路 OpenHands 从 t=0 几乎一起进，活几分钟到几十分钟。后面几小时主要靠 GLM + Request 持续进场。

## 生成

```bash
bash scripts/shell/build_mix.sh
```

| 文件 | 是否进 git | 内容 |
|---|---|---|
| `spec.json` | 是 | 配方与 Session 列表（较大，含 1 万条 GLM 元数据） |
| `sessions.jsonl` | 是 | 每 Session 一行元数据 |
| `manifest.json` | 是 | sha256 |
| `workload.jsonl` | 否 | 约 1.88 GB |

## 重放

```bash
bash scripts/shell/v4flash.sh
bash scripts/shell/replay_mix_workload.sh
```

## 本份冻结统计（seed=42）

| | OpenHands | GLM-Agent | Request |
|---|---:|---:|---:|
| Session | 20（20 独特） | 10073（3253 多跳 / 6820 单跳） | 8400 |
| 调用 | 1126 | 16559 | 19585 |
| 原始跨度中位 | 590 s | 0 s（大量单跳） | 0 s |
| 重放最后进场（2s/3s） | 38 s | 5.60 h | 7.00 h |

合计 18493 Session / 37270 跳。旧份 `mix_sysdiv_6h` / `mix_oh54_g54_r432` / `mix_a140_r560` 未覆盖。
