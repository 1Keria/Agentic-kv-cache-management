# mix_eval_3h_oh59_g150_r1050

给后续小模型实验用的 **约 3h 评测夹具**。过滤条件与 `mix_lru_pressure_oh59_g100_r700` 相同；12 跳严格前缀的 OpenHands 只有 59 条，所以 OpenHands 数量不动，GLM / Request 按 9/6 加密。不覆盖 2h 那份。

用原来的脚本生成：

```bash
bash scripts/shell/build_mix.sh \
  --name mix_eval_3h_oh59_g150_r1050 \
  --out-dir workloads/mix_eval_3h_oh59_g150_r1050 \
  --n-glm 150 \
  --n-request 1050
```

## 数据组成

| | OpenHands | GLM-Agent | Request |
|---|---:|---:|---:|
| Session | 59 | 150 | 1050 |
| 调用 | 708 | 1090 | 1922 |
| 每 Session 跳数 | 12 | 至少6 | 最多8 |

Agent 共 1798 次调用（48.3%），Request 共 1922 次调用（51.7%）。

- OpenHands 来自去重后的独特轨迹，只保留前 12 跳严格消息前缀链。冻结后验证：649 个相邻跳对全部严格增长，无上下文截断或重置。
- GLM 来自 `n>=6` 的推断连续链，不含单跳孤条（池子 208 条，本份抽 150）。
- Request 空档 cap=30s。

## 九个混合波次

重放仍用 `scripts/shell/replay_mix_workload.sh`，只改目录和到达窗：

```bash
bash scripts/shell/replay_mix_workload.sh \
  --workload-dir workloads/mix_eval_3h_oh59_g150_r1050 \
  --arrival-horizon-s 10800 \
  --arrival-waves 9
```

波次起点约为 0、22.5、45、67.5、90、112.5、135、157.5、179.8 分钟。每个波次在 10 秒内混合投放：

- 前 6 波：7 OpenHands + 17 GLM + 117 Request
- 后 3 波：6 OpenHands + 16 GLM + 116 Request

Session 内仍按真实闭环执行，上一跳完成后再等待原始间隙并发下一跳。按 2h 基线末波之后约 8–9 分钟收尾估算，墙钟大约 **3.1h**。

## 使用

```bash
MEM_FRACTION_STATIC=0.45 bash scripts/shell/v4flash.sh
bash scripts/shell/replay_mix_workload.sh \
  --workload-dir workloads/mix_eval_3h_oh59_g150_r1050 \
  --arrival-horizon-s 10800 \
  --arrival-waves 9
```

本目录已冻结；调整波次或 KV 容量不需要重造 jsonl。
