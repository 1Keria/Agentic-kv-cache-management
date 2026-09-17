# V4-Flash：11 组按比例日更模型训练 workload

这些 workload 用于模拟“前一日流量”，分别训练与测试比例对应的 11 个 MLP。它们不是最终测试数据。

## 固定协议

- 每组恰好 2100 次调用，高于最终测试的 2000 次调用；
- Agent 调用占比为 `0.0, 0.1, ..., 1.0`；
- `agent_010` 对应训练 `ratio=0.1` 的模型，依此类推；
- Agent 来自全部 59 条 V4-Flash 开发轨迹（旧划分中的 47 条 train 和 12 条 validation）；
- OpenHands 在上下文重置处切段，仅使用至少 12 次调用且段内 prompt 严格前缀增长的部分；
- Request 来自旧开发池，并用额外 WildChat 补足容量；
- Request 已按 `conversation_hash` 去重，额外数据也排除了全部最终测试 hash；
- 不包含 GLM 或任何最终测试 session；
- 9 个波次已写入 `session_start_s`，重放必须使用 `--arrival frozen`。

旧 validation 仅用于前期确定统一的模型结构和超参数；最终 11 个模型不再按比例调参，因此在设计冻结后并入最终训练。49 条从未参与开发的 V4-Flash 轨迹仍只用于最终测试。

精确计数见 [`index.json`](index.json)。

## 重新生成

```bash
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python \
  scripts/python/build_ratio_training_workloads.py
```

## 训练前重放

训练标签需要对应 workload 的实际 `s_time/e_time`。先启动 LRU server，再逐个重放。例如比例 0.5：

```bash
bash scripts/shell/replay_ratio_training.sh agent_050
```

输出统一放在：

```text
experiments/sglang_kv_cache/ratio_daily_models/agent_050/replay/run_mix_train_lru/
```

确认单个比例正常后，可以依次重放全部比例：

```bash
bash scripts/shell/replay_ratio_training.sh all
```

重放完成后，使用对应目录的 `replay.jsonl` 为 `agent_050` 单独生成训练样本，并训练 `MLP_050`。后续样本和模型也统一放在 `ratio_daily_models/agent_050/` 下。不能使用最终测试 workload 或已经完成的最终 LRU 结果造训练标签。
