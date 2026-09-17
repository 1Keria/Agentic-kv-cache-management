# 按日重训的比例模型实验

本目录统一保存11个Agent调用比例对应的训练重放、MLP样本、checkpoint和最终评测产物。

```text
ratio_daily_models/
├── agent_000/
│   ├── replay/run_mix_train_lru/
│   ├── samples/
│   ├── checkpoint/
│   └── eval/
├── agent_010/
│   └── ...
└── agent_100/
    └── ...
```

训练 workload 位于：

```text
workloads/ratio_train_v4flash/agent_000 ... agent_100
```

最终测试 workload 位于：

```text
workloads/ratio_sweep_v4flash_unseen/agent_000 ... agent_100
```

每个比例的训练 workload 为 2100 次调用，最终测试 workload 为 2000 次调用。训练使用全部 59 条 V4-Flash 开发轨迹及与测试集去重的 WildChat；最终测试继续使用 49 条未见 V4-Flash 轨迹及独立 WildChat。

## 训练重放

先启动LRU server：

```bash
bash scripts/shell/v4flash.sh
```

重放单个比例：

```bash
bash scripts/shell/replay_ratio_training.sh agent_000
```

确认无误后重放全部比例：

```bash
bash scripts/shell/replay_ratio_training.sh all
```

包装脚本会强制使用训练workload的冻结到达时间，并将输出写入对应比例的 `replay/` 子目录。若目标run目录已经存在，脚本会停止而不是覆盖。

## 生成样本并训练

训练重放完成后，例如训练 `agent_050`：

```bash
bash scripts/shell/train_ratio_model.sh agent_050
```

脚本会离线重建 Radix 树，将请求级重放转换为节点级 `(x, T_s)` 样本，再用全部样本执行最终拟合。统一产出位置：

```text
agent_050/
├── samples/
│   ├── samples_train.jsonl.gz
│   ├── samples_meta.json
│   └── build_samples.log
└── checkpoint/
    ├── leaf_mlp.pt
    ├── horizons.json
    ├── metrics_mlp.json
    └── train.log
```
