# mix_eval_longgap_oh59_g150_r1050

给「跨请求 radix 前缀还在不在」用的评测夹具。Session 组成与 `mix_eval_3h_oh59_g150_r1050` 相同（OH 59 + GLM 150 + Request 1050），**不截 OpenHands 前 12 跳**，把真实分钟级空档留在链上。旧 3h mix 不覆盖。

造数：

```bash
bash scripts/shell/build_mix_longgap.sh
```

`workload.jsonl` sha256 前缀 `fd9293f559058a49`。

## 和旧 mix 的差别

| | 旧 `mix_eval_3h` | 本份 `mix_eval_longgap` |
|---|---:|---:|
| Session | 1259 | 1259（同池、同 seed） |
| 调用 | 3720 | **4999** |
| OpenHands 调用 | 708（截 12 跳） | **1987**（完整严格前缀） |
| OH 每 Session 跳数 | 全是 12 | min 12 / p50 25 / p90 69 / max 113 |
| OH orig_span p50 | 8.9s | **258s** |
| OH 空档 >60s / >180s / >600s | 12 / 6 / 3 | **61 / 29 / 7** |
| 含 >60s 空档的 OH session | 10 / 59 | **20 / 59** |
| GLM / Request | 1090 / 1922 | 相同（短间隔；Request cap 30s、64.5% 单跳） |

分钟级空档几乎全在 OpenHands 后段。GLM 推断链即使用更大 `glm_break_gap` 也凑不出分钟级间隔，所以本份只放宽 OH，GLM / Request 继续当坑位压力。

冻结后：OH 相邻跳仍是严格前缀增长（与造数时 `min-openhands-prefix-turns 12` 同一套检查）。

## 离线上界

口径与 `models/MLP/src/oracle_bound.py` 相同：消息块 radix（`char/4`），不是 tokenizer；贪心 Belady 不是严格 knapsack。

**不要**用合成时钟的 Δ 去对比旧 mix 的 serving 上界。dummy e2e=10s 的并发/占用和真实 TTFT 差很远：同样这份旧 mix，真实 replay 上 Belady−LRU 只有 **+0.011**，合成时钟会虚高到 **+0.27**。

合成时钟（9 波 + `pre_gap` + dummy e2e=10s）同 C 对照：

| C | 旧 mix LRU | 旧 mix Belady−LRU | 本份 LRU | 本份 Belady−LRU |
|---:|---:|---:|---:|---:|
| 83339 | 0.062 | +0.073 | 0.233 | +0.073 |
| 127728（旧 serving 校准点） | 0.156 | +0.167 | 0.402 | +0.102 |
| 162950 | 0.233 | +0.270 | 0.508 | +0.135 |

本份 LRU 自己更高：多出来的 OH 跳大部分仍是亚秒空档，LRU 也能打中，token-weighted 会稀释分钟级空档。保活与 Belady 仍然几乎重合。真正天花板够不够，要等本份 **LRU serving replay** 用真实 `s_time/e_time` 再校准 C。

若 serving 后 Belady−LRU 仍只有一个点，下一步是只留 20 条带 >60s 空档的 OH，或把无长空档的 OH 截回 12 跳。

```bash
python models/MLP/src/oracle_bound.py --synthetic --skip-sweep \
  --workload workloads/mix_eval_longgap_oh59_g150_r1050/workload.jsonl \
  --target-lru 0.233
```

## 九个混合波次

重放仍用 `scripts/shell/replay_mix_workload.sh`，只改目录和到达窗：

```bash
bash scripts/shell/replay_mix_workload.sh \
  --workload-dir workloads/mix_eval_longgap_oh59_g150_r1050 \
  --arrival-horizon-s 10800 \
  --arrival-waves 9
```

波次起点约为 0、22.5、45、67.5、90、112.5、135、157.5、179.8 分钟。每个波次在 10 秒内混合投放：

- 前 5 波：7 OpenHands + 17 GLM + 117 Request
- 第 6 波：6 OpenHands + 17 GLM + 117 Request
- 后 3 波：6 OpenHands + 16 GLM + 116 Request

Session 内按真实闭环执行，上一跳完成后再等待原始 `pre_gap`。最长 OH orig_span ≈ 79 min，且不截断。合成时钟（dummy e2e=10s）最晚约 **3.5h**；真实 serving 预计 **4–5h**（OH 生成更长）。

## 使用

先 LRU 打基线，再 MLP。主表报全局 token-weighted hit（含冷启动）。**不要**和旧 mix 的 3720 次数字直接比。

```bash
# LRU
MEM_FRACTION_STATIC=0.45 bash scripts/shell/v4flash.sh
MIX_REPLAY_RUN_ID=<lru_id> bash scripts/shell/replay_mix_workload.sh \
  --workload-dir workloads/mix_eval_longgap_oh59_g150_r1050 \
  --arrival-horizon-s 10800 \
  --arrival-waves 9

# MLP（另起目录，勿覆盖旧 mix 跑次）
# bash scripts/shell/v4flash_mlp.sh
# MIX_REPLAY_RUN_ID=<mlp_id> bash scripts/shell/replay_mix_workload.sh ...同上
```

本目录已冻结；调整波次或 KV 容量不需要重造 jsonl。
