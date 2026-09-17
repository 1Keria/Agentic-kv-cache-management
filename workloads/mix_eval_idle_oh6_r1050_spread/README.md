# mix_eval_idle_oh6_r1050_spread

overlap serving（`run_mix_20260831_overlap_lru`）把 LRU 打到 0.177：20 条 OH 叠在 60s 里，这块 GPU 的有效 C≈4.4 万消息块，连 Belady 也只能相对 LRU **+16%**（坑的 95% 是容量）。

这份把峰值占用降下来，**不改** `mem-fraction-static 0.45`：

- 6 条 OH（同一批长空档里的前 6 条），铺在 **900s**
- Request 整体 **+180s**，打在第一轮空档上，不跟 OH 首填撞车
- 轮间空档仍 **floor 180s**
- Request 仍 1050、9 波

造数：

```bash
bash scripts/shell/build_mix_idle_oh6_spread.sh
```

`workload.jsonl` sha256 前缀 `bef88b391c4e29a3`。

## 离线上界（合成时钟，C=44373 = overlap serving 反推）

| | LRU | Belady | 相对 LRU | 占无限容量余量 |
|---|---:|---:|---:|---:|
| 全局 | 0.245 | 0.371 | **+51%** | 33% |
| OpenHands | 0.192 | 0.315 | **+64%** | — |

重放必须 `--arrival frozen`。

```bash
bash scripts/shell/v4flash.sh
MIX_REPLAY_RUN_ID=<id> bash scripts/shell/replay_mix_workload.sh \
  --workload-dir workloads/mix_eval_idle_oh6_r1050_spread \
  --arrival frozen
```

不要覆盖 overlap / idle v1 / longgap。
