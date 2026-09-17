# mix_lru_pressure_oh59_g100_r700

用于放大“可复用前缀被 LRU 驱逐后再次访问”的受控压力负载。它与均匀稳态负载 `mix_oh108_g208_r1450` 分开保存。

## 数据组成

| | OpenHands | GLM-Agent | Request |
|---|---:|---:|---:|
| Session | 59 | 100 | 700 |
| 调用 | 708 | 736 | 1347 |
| 每 Session 跳数 | 12 | 至少6 | 最多8 |

Agent 共1444次调用（51.7%），Request 共1347次调用（48.3%）。

- OpenHands 来自去重后的独特轨迹，只保留前12跳严格消息前缀链。冻结后验证：649个相邻跳对全部严格增长，无上下文截断或重置。
- GLM 来自 `n>=6` 的推断连续链，不含单跳孤条。
- Request 空档 cap=30s。

## 六个混合波次

重放脚本使用：

```bash
--arrival waves
--arrival-horizon-s 7200
--arrival-waves 6
--arrival-wave-width-s 10
```

波次起点约为 0、24、48、72、96、119.8 分钟。每个波次在10秒内混合投放：

- 前4波：10 OpenHands + 17 GLM + 117 Request
- 第5波：10 OpenHands + 16 GLM + 116 Request
- 第6波：9 OpenHands + 16 GLM + 116 Request

Session 内仍按真实闭环执行，上一跳完成后再等待原始间隙并发下一跳。

## 使用

先以受限 KV 启动服务，例如：

```bash
MEM_FRACTION_STATIC=0.45 bash scripts/shell/v4flash.sh
```

再重放：

```bash
bash scripts/shell/replay_mix_workload.sh
```

本目录已冻结；调整波次或 KV 容量不需要重造 jsonl。
