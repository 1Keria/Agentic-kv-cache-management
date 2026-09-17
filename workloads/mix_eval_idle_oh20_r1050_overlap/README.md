# mix_eval_idle_oh20_r1050_overlap

相对 `mix_eval_idle_oh20_r1050` 加大策略空间的夹具：同样 20 条 OH + 1050 Request，不要 GLM。

改了两处到达 / 空档，不覆盖 v1：

- 轮间空档 **floor 180s**（真实空档不到 180 的抬到 180；109/109 都 ≥180s）。
- 20 条 OH **叠在开头 60s** 并发抢 KV；Request 仍 9 波铺满 3h。

造数：

```bash
bash scripts/shell/build_mix_idle_overlap.sh
```

`workload.jsonl` sha256 前缀 `ccfed3c5c2075038`。内容仍来自 `mix_eval_longgap`：tool 环压成 round，只留每轮最后一跳。不要复制同一条 OH 来凑并发（radix 会跨 session 共享，LRU 也受益）。

## 组成

| | OpenHands | Request |
|---|---:|---:|
| Session | 20（start ∈ [0, 60]s） | 1050（9 波，0–10800s） |
| 调用 | 129 | 1922 |
| 轮间空档 | 109，**全部 ≥180s** | cap 30s |

## 离线上界（合成时钟，`--file-starts`）

`oracle_bound.py --synthetic --file-starts`，dummy e2e=10s。保活 ≈ Belady。

| C（消息块） | LRU | Belady−LRU |
|---:|---:|---:|
| 365916 | 0.542 | **+0.139** |
| 318240（校准 LRU≈0.40） | 0.400 | **+0.256** |
| 182958 | 0.274 | **+0.212** |
| 无限 | 0.702 | — |

v1 同校准点只有 +0.078。这里 OH 同时活着，180s 空档里 Request 把 LRU 的前缀挤掉，Belady 能留住。

合成时钟仍不能当 serving 预测。上 serving 后用真实 `s_time` 再校准一次。

## 重放

`session_start_s` 已经写进 jsonl。**必须 `--arrival frozen`**，不要 `waves`：waves 会重算 OH 到达，把重叠冲掉。

```bash
bash scripts/shell/v4flash.sh
MIX_REPLAY_RUN_ID=<id> bash scripts/shell/replay_mix_workload.sh \
  --workload-dir workloads/mix_eval_idle_oh20_r1050_overlap \
  --arrival frozen
```

离线复现：

```bash
python models/MLP/src/oracle_bound.py \
  --synthetic --file-starts --target-lru 0.40 \
  --workload workloads/mix_eval_idle_oh20_r1050_overlap/workload.jsonl
```

本目录不要覆盖 longgap / 3h mix / `mix_eval_idle_oh20_r1050`。
