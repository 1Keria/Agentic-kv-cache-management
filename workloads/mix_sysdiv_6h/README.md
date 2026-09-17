# mix_sysdiv_6h

冻结的三类混合 serving 负载，目标是 **Agent 之间尽量不共享 system 前缀**，重放墙钟大约 **6 小时**。不覆盖 `mix_a140_r560` / `mix_oh54_g54_r432`。

- **OpenHands**：三个 Flash 包内容去重后共 108 条独特轨迹，但它们共用同一套 `You are OpenHands agent…` 脚手架，所以 **只留 1 条**（本份是 runner05 的 `shock-analysis-demand`，218 跳）。
- **GLM-Agent**：线上 jsonl 按首条 user hash + messages exact prefix 推断 session（不是官方键）。在 n≥2 的 3253 条链上做贪心：若与已留 session 的 system **LCP ≥ 64 字符**则丢弃。本份留下 102 条；两两 system LCP 最大 **63 字符**（远小于旧份 OpenHands 的 ~1.4 万字符 / 2816 token）。
- **Request**：WildChat，按 Agent session 数 1:4 → 412 条。
- Session 内正文和间隙仍用原始/推断轨迹。spec 里进场是 Δ=180s/45s；**重放默认 Agent 200s / Request 50s**（最后进场约 5.7h，加上尾部大约 6h）。不要为了改 Δ 重造 jsonl。

成功信号：OpenHands 第 0 跳不再稳定打到 2816；各类 Agent turn0 互不命中对方脚手架；会话内后续跳该高还高。报告按 `openhands` / `glm` / `request` 拆 turn0 与 within-session。

## 生成

```bash
bash scripts/shell/build_mix.sh
```

| 文件 | 是否进 git | 内容 |
|---|---|---|
| `spec.json` | 是 | 配方、推断方法、system LCP 约束、有序 Session 列表 |
| `sessions.jsonl` | 是 | 每 Session 一行元数据（无 messages） |
| `manifest.json` | 是 | workload / 源文件 sha256 |
| `workload.jsonl` | 否 | 每一跳的 messages / max_tokens / pre_gap（约 80 MB） |

## 重放

```bash
bash scripts/shell/v4flash.sh
bash scripts/shell/replay_mix_workload.sh
```

目录：`experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_<ts>/`。

## 本份冻结统计

| | OpenHands | GLM-Agent | Request |
|---|---:|---:|---:|
| Session | 1 | 102（推断，n≥2；其中 41 条 n≥4） | 412（252 单轮 / 160 多轮） |
| 调用 | 218 | 405 | 963 |
| 原始跨度中位 | 1929 s | 25 s | 0 s |
| spec 最后进场（180/45） | 0 | 5.05 h | 5.14 h |
| 重放最后进场（200/50） | 0 | 5.61 h | 5.71 h |

调用占比约 14% OpenHands / 26% GLM / 61% Request。Agent 跳数比旧农场少，6h 主要来自进场窗口，不是把同一套 OpenHands 堆满 GPU。
