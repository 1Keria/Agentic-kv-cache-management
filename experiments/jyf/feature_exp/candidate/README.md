# Node-level ideal-session feature experiment

当前实验只模拟一个理想资源环境：

- 每个 session 拥有独立 radix tree；
- session 之间不共享 node、hit 或 gap history；
- node 永不 eviction；
- message 只是 radix tree 的边/segment，样本单位是持久化的 cumulative prefix node；
- 标签是同一个 node 在本 session 内下一次 demand 的 wall-clock gap；session 最后一次 demand 为 right-censored。

入口脚本：

`run_node_experiment.py`

示例：

```bash
python3 run_node_experiment.py \
  --data /share/dai-sys/zhoulongsheng/agentkv/third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl \
  --out /share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/feature_exp/candidate/runs/node_level_v1
```

输出：

- `node_samples.npz`: node-level 样本、absolute/relative label、censor event、session split
- `node_dataset_meta.json`: 数据口径、样本单位、特征清单和审计计数

原 16 维去除 event/LRU 后的 Old-10：

```text
node_tokens
path_tokens
age_seconds
idle_seconds
hits
gap_present
recent_gap_seconds
gap_ewma_seconds
gap_std_seconds
is_agent
```

当前 candidate 的 8 维作为 node-level context/history 特征挂到 node demand 上：

```text
creation_turn_fraction
endpoint_is_tool
tool_schema_count
last_message_is_tool
last_message_is_user
prefix_gap_ewma_rel
prefix_reuse_rate8
prefix_turn_gap_last
```

注意：当前输入数据没有显式 workload 字段，因此 `is_agent` 暂时为常数 0，只为保持 Old-10 的列兼容；不能把它解释为真实的 agent 标志。后续如果原始 trace 提供 workload metadata，再替换该列。

之前的 message/session-level 脚本和报告保存在 `archive_session_level/`，不应作为本实验的结果入口。

