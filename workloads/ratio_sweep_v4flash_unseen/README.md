# V4-Flash 未见数据：Agent 调用比例扫描

这组 workload 用于比较固定模型下 LRU 与 MLP 随 Agent 调用占比变化的表现。

## 数据协议

- 每组恰好 2000 次调用；
- Agent 调用占比为 `0.0, 0.1, ..., 1.0`；
- Agent 只使用未进入旧 `oh59` 模型数据池的 49 条 V4-Flash OpenHands 轨迹；
- 轨迹遇到上下文重置时切段，只保留至少 12 次调用且段内 prompt 严格前缀增长的部分；
- 最终得到 64 个严格前缀段、2227 次可用 Agent 调用；
- Request 来自新的 WildChat conversation，排除旧模型 workload 使用过的 conversation hash；
- 不包含 GLM；
- 9 个混合波次已写入 `session_start_s`，重放必须使用 `--arrival frozen`。

精确比例和数据池统计见 [`index.json`](index.json)。每个子目录的 `spec.json` 记录目标比例、实际比例和来源。

## 重新生成

```bash
/share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python \
  scripts/python/build_ratio_sweep_workloads.py
```

## 重放单个比例

先启动 LRU 或 MLP server，然后选择对应目录。例如 Agent 调用占比 0.5：

```bash
MIX_REPLAY_RUN_ID=<run_id> bash scripts/shell/replay_mix_workload.sh \
  --workload-dir workloads/ratio_sweep_v4flash_unseen/agent_050 \
  --arrival frozen
```

目录对应关系：

```text
agent_000 → 0.0
agent_010 → 0.1
...
agent_100 → 1.0
```

同一比例下，LRU 与 MLP 必须使用完全相同的目录、server 配置、显存比例和到达方式。
