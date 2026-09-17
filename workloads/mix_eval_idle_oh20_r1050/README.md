# mix_eval_idle_oh20_r1050

按「上界要够高」从 `mix_eval_longgap` **合成**的评测夹具，不是新采的轨迹。

- 只留 **一种 Agent**：OpenHands。GLM 丢掉。
- tool 环（`pre_gap < 10s`）压成一轮，只保留每轮最后一跳（此时前缀最长）。
- 只留至少有一次 **≥60s 轮间空档** 的 session（20 条）。
- Request 1050 仍当 KV 压力，不进故事。

造数：

```bash
bash scripts/shell/build_mix_idle_prefix.sh
```

`workload.jsonl` sha256 前缀 `bfb0298464ef6f3b`。

## 组成

| | OpenHands | Request |
|---|---:|---:|
| Session | 20 | 1050 |
| 调用 | 129 | 1922 |
| 轮间空档 | 109（**64 个 ≥60s**，29 个 ≥180s） | cap 30s |

相对 longgap：OH 从 1987 跳收到 129 跳；≥60s 空档从 61/1928（3%）变成 **64/109（59%）**。短环 token 不再稀释 TW。

这是夹具：中间 tool 调用被丢掉，serving 里一次 round 会把整段新后缀一起 prefill。内容仍是真实 OH 前缀链。

## 离线上界（合成时钟）

`oracle_bound.py --synthetic`，dummy e2e=10s。保活 ≈ Belady。

| C（消息块） | LRU | Belady−LRU |
|---:|---:|---:|
| 182958 | 0.695 | +0.007 |
| 91479 | 0.613 | **+0.048** |
| 56098（校准 LRU≈0.40） | 0.399 | **+0.078** |
| 45739 | 0.317 | **+0.082** |
| 无限 | 0.702 | — |

longgap 真实 replay 上界只有 +0.005。这份在 LRU 被压到 0.3–0.6 时，策略空间到了 **0.05–0.08**。若 serving 太松（LRU 仍 ≥0.69），上界会缩回去——那时是压力不够，不是空档不够。

合成时钟仍不能当 serving 预测。上 serving 后用真实 `s_time` 再校准一次。

## 重放

先 LRU，再 MLP。主表报全局 TW hit，附录拆 OH / Request。

```bash
bash scripts/shell/v4flash.sh
MIX_REPLAY_RUN_ID=<id> bash scripts/shell/replay_mix_workload.sh \
  --workload-dir workloads/mix_eval_idle_oh20_r1050 \
  --arrival-horizon-s 10800 \
  --arrival-waves 9
```

OH 只有 129 跳，墙钟应明显短于 longgap（仍有 1050 条 Request 和最长 ~1h 空档）。

本目录已冻结；不要覆盖 longgap / 3h mix。
