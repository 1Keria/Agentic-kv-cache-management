# mix_oh100_g100_r2000

约 2 小时的三类混合：**100 条独特 OpenHands（截到前 8 跳）+ 100 条 GLM（n≥6）+ 2000 条 Request**。旧份 `mix_oh20_g1200_r1000` / `mix_oh20_glm_r8400` 不覆盖。

相对 `mix_oh20_g1200_r1000` 的改动（为了两类 Agent 可比、整体不要太高）：

- 条数对齐 **100 vs 100**，不再是 20 路长 OH 对 1200 路短 GLM。
- OpenHands 只留前 **8** 跳（原来中位 38 跳、最长 218），和 GLM 深度接近（本份 GLM 715 跳 / OH 799 跳）。
- GLM 只要 `n≥6` 的真链（208 条候选里 seed=42 抽 100），不要单跳孤条。
- Request 空档 cap=30s、最多 16 跳。重放默认 `--arrival uniform`，三类铺在同一段约 66 min 的时间线上。

## 生成

```bash
bash scripts/shell/build_mix.sh
```

| 文件 | 是否进 git | 内容 |
|---|---|---|
| `spec.json` | 是 | 配方与 Session 列表 |
| `sessions.jsonl` | 是 | 每 Session 一行元数据 |
| `manifest.json` | 是 | sha256 |
| `workload.jsonl` | 否 | 冻结跳 |

## 重放

```bash
bash scripts/shell/v4flash.sh
bash scripts/shell/replay_mix_workload.sh
```

三类铺在同一段 horizon 上交错进场（`--arrival uniform`）。jsonl 不用重造。旧排法加 `--arrival staggered`。

## 本份冻结统计（seed=42）

| | OpenHands | GLM-Agent | Request |
|---|---:|---:|---:|
| Session | 100（截到 ≤8 跳） | 100（全部 n≥6，从 208 条抽） | 2000（1182 单轮 / 818 多轮） |
| 调用 | 799 | 715 | 4463 |
| 原始跨度中位 | 3.0 s | 38.8 s | 0 s |
| 重放最后进场（uniform） | ~66 min | ~66 min | ~66 min |

合计 **2200 Session / 5977 跳**。第 0 跳占比：OH 12.5% / GLM 14.0%。墙钟仍由约 6000 跳排队决定，大概 2 小时量级。OpenHands 仍共享脚手架，turn0 可能略高于 GLM；会话长度和条数已经对齐，避免再出现 0.85 vs 0.01。
