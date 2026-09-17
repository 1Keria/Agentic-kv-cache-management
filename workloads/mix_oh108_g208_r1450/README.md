# mix_oh108_g208_r1450

约 2 小时的高并发三类混合，主点按调用数控制为 **Agent / Request ≈ 50 / 50**：

- OpenHands：108 条去重后的独特轨迹全部使用，每条保留前 12 跳。
- GLM-Agent：全部 208 条 `n>=6` 的推断连续链。
- Request：1450 条 WildChat，空档 cap=30s，最多 8 跳。

## 冻结统计

| | OpenHands | GLM-Agent | Request |
|---|---:|---:|---:|
| Session | 108 | 208 | 1450 |
| 调用 | 1281 | 1506 | 2801 |
| 原始跨度中位 | 7.9s | 38.3s | 0s |

合计 **1766 Session / 5588 次调用**：

- Agent：2787 次（49.9%）
- Request：2801 次（50.1%）
- OpenHands / GLM 调用量接近，分别占 Agent 调用的 46.0% / 54.0%。
- GLM 不含单跳孤条；两类 Agent 都是真正可观察会话内复用的多跳链。

## 时间线

重放使用：

```bash
--arrival uniform --arrival-horizon-s 7200
```

1766 个 Session 按类别比例编入同一条 2 小时时间线，平均每约 4.1s 启动一个新 Session。Session 内仍是闭环：上一跳完成后，按真实间隙发下一跳。因此三类会贯穿整个时间线，同时保留 Agent 的多跳突发。

## 使用

```bash
bash scripts/shell/v4flash.sh
bash scripts/shell/replay_mix_workload.sh
```

旧 workload 均未覆盖。不要为了修改进场时间重造 jsonl。
