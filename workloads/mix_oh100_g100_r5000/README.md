# mix_oh100_g100_r5000

约 **2 小时高并发** 三类混合：**100 条独特 OpenHands（截到前 8 跳）+ 100 条 GLM（n≥6）+ 5000 条 Request（最多 2 跳）**。

不覆盖 `mix_oh100_g100_r2000`。那份只有 2200 Session，均匀铺开后进场间隔太大，并发上不去。本份加到 **5200 Session / 7475 跳**，重放铺在 **7200s** 时间线上，全局约 **1.4s** 进一条，三类按 100:100:5000 的比例交错。

## 生成

```bash
bash scripts/shell/build_mix.sh
```

## 重放

```bash
bash scripts/shell/v4flash.sh
bash scripts/shell/replay_mix_workload.sh
```

`--arrival uniform --arrival-horizon-s 7200`。jsonl 不用为改进场重造。

## 本份冻结统计（seed=42）

| | OpenHands | GLM-Agent | Request |
|---|---:|---:|---:|
| Session | 100（≤8 跳） | 100（n≥6） | 5000（4039 单轮 / 961 两轮） |
| 调用 | 799 | 715 | 5961 |
| 原始跨度中位 | 3.0 s | 38.8 s | 0 s |

合计 **5200 Session / 7475 跳**。跳数对齐先前约 2h 的 6700–7500；进场铺满 2h，而不是 66 分钟就把人排完。
