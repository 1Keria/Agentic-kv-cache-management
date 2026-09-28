# token_balanced_openhands_wildchat

用于固定分区机制快速验证的冻结混合流量，仅包含 OpenHands 和 WildChat，不包含 GLM。

## 选择原则

- token 依据：已有 DeepSeek V4 Flash 实际重放返回的 `prompt_tokens`；
- 普通请求：保留源 workload 中全部 548 个 WildChat Session；
- OpenHands：同一原始轨迹最多保留一个严格前缀段，通过确定性子集选择配平最终上下文；
- OpenHands 最终 prompt token：385,107；
- 普通请求最终 prompt token：385,107；
- 两类差值：0 token。

调用次数不做均衡，因为固定分区按 KV token 容量划分，而不是按请求次数划分。

## 规模

- OpenHands：7 个 Session，211 次调用；
- 普通请求：548 个 Session，1050 次调用；
- 总计：555 个 Session，1261 次调用；
- Session 启动时间冻结为 6 个混合波次，覆盖 30 分钟；
- Session 内等待最多 30 秒；每次生成最多 208 token；prompt 内容保持不变。

## 回放

```bash
bash experiments/固定分区试验对比/scripts/replay_workload.sh
```

离线选择固定分区比例和两次 GPU 实验都必须使用本目录同一份 `workload.jsonl`。
