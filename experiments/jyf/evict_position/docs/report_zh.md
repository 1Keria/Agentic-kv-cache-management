# 完整 frontier：秒级 MLP 的推理时机对比

每组 3 次实际 TP=8 serving 运行。候选无 LRU 截断；请求集合、有效配置、MLP 策略的全部 TP rank victim 选择及三组的释放量均已通过检查。原生 LRU 未记录逐 victim 身份。

| 指标（各次运行均值） | LRU | On-demand | 预计算并等待 |
|---|---:|---:|---:|
| 成功请求 | 1,970.000 | 1,970.000 | 1,970.000 |
| Token 命中率 % | 91.817 | 94.084 | 94.202 |
| 未命中 prompt tokens | 3,317,924.000 | 2,398,713.333 | 2,350,841.333 |
| TTFT p50 ms | 503.106 | 480.771 | 521.364 |
| TTFT p90 ms | 2,145.582 | 1,639.986 | 1,756.572 |
| TTFT p99 ms | 5,968.545 | 3,589.709 | 4,018.012 |
| E2E p50 ms | 1,305.006 | 1,232.488 | 1,300.487 |
| E2E p90 ms | 4,845.800 | 2,999.739 | 2,852.398 |
| E2E p99 ms | 10,499.453 | 9,039.112 | 8,091.651 |
| 请求/秒 | 4.752 | 5.137 | 5.016 |
| 回放秒数 | 414.571 | 383.478 | 392.718 |
| Eviction p50 µs | 4,154.814 | 9,616.331 | 5,756.707 |
| Eviction p99 µs | 205,888.263 | 197,103.574 | 186,895.694 |
| Request-end p50 µs | 189.040 | 177.716 | 688.291 |
| Request-end p99 µs | 3,634.017 | 4,047.769 | 15,488.840 |
| 最大合法 frontier（各次最大值的均值；LRU 未采集） | — | 160.000 | 146.333 |
| Eviction 内预测节点数 | 0.000 | 49,135.333 | 0.000 |
| 提前提交预测数 | 0.000 | 0.000 | 303,474.667 |
| 遇到未完成任务次数 | 0.000 | 0.000 | 195.000 |
| 读取/等待预测合计秒数 | 0.000 | 0.000 | 0.210 |
| MLP 推理合计秒数 | 0.000 | 0.381 | 11.346 |

## 逐次结果

### 20260913_100114_formal_rep1

| 策略 | Token 命中率 % | TTFT p50 ms | E2E p50 ms | 完成请求/秒 |
|---|---:|---:|---:|---:|
| lru | 91.514 | 498.306 | 1355.704 | 4.707 |
| on_demand | 94.177 | 489.034 | 1258.179 | 5.135 |
| precompute | 94.146 | 544.344 | 1328.233 | 5.010 |

预计算提交来源：

```json
{
  "cache_unfinished_req": {
    "calls": 1576,
    "predictions": 52598,
    "submit_us": 2895238.167606294
  },
  "match_prefix": {
    "calls": 1089,
    "predictions": 48602,
    "submit_us": 2662426.2053519487
  },
  "inc_lock_ref": {
    "calls": 2170,
    "predictions": 96158,
    "submit_us": 4937666.050158441
  },
  "dec_lock_ref": {
    "calls": 1088,
    "predictions": 48284,
    "submit_us": 2469725.844450295
  },
  "cache_finished_req": {
    "calls": 1500,
    "predictions": 51414,
    "submit_us": 2751853.338442743
  }
}
```

### 20260913_103350_formal_rep2

| 策略 | Token 命中率 % | TTFT p50 ms | E2E p50 ms | 完成请求/秒 |
|---|---:|---:|---:|---:|
| lru | 91.999 | 516.962 | 1264.558 | 4.769 |
| on_demand | 94.041 | 458.671 | 1217.526 | 5.140 |
| precompute | 94.148 | 517.310 | 1299.216 | 5.005 |

预计算提交来源：

```json
{
  "cache_unfinished_req": {
    "calls": 1573,
    "predictions": 53846,
    "submit_us": 2933080.72257787
  },
  "match_prefix": {
    "calls": 1097,
    "predictions": 49800,
    "submit_us": 2710134.376771748
  },
  "inc_lock_ref": {
    "calls": 2188,
    "predictions": 98662,
    "submit_us": 5053552.724421024
  },
  "dec_lock_ref": {
    "calls": 1096,
    "predictions": 49466,
    "submit_us": 2530786.7815718055
  },
  "cache_finished_req": {
    "calls": 1500,
    "predictions": 52766,
    "submit_us": 2806731.8871617317
  }
}
```

### 20260913_110634_formal_rep3

| 策略 | Token 命中率 % | TTFT p50 ms | E2E p50 ms | 完成请求/秒 |
|---|---:|---:|---:|---:|
| lru | 91.940 | 494.049 | 1294.758 | 4.781 |
| on_demand | 94.035 | 494.606 | 1221.758 | 5.137 |
| precompute | 94.313 | 502.437 | 1274.011 | 5.034 |

预计算提交来源：

```json
{
  "cache_unfinished_req": {
    "calls": 1566,
    "predictions": 54616,
    "submit_us": 3032048.985362053
  },
  "match_prefix": {
    "calls": 1106,
    "predictions": 50426,
    "submit_us": 2853774.460963905
  },
  "inc_lock_ref": {
    "calls": 2208,
    "predictions": 100130,
    "submit_us": 5155833.640135825
  },
  "dec_lock_ref": {
    "calls": 1105,
    "predictions": 50096,
    "submit_us": 2549002.096056938
  },
  "cache_finished_req": {
    "calls": 1500,
    "predictions": 53560,
    "submit_us": 2904765.681363642
  }
}
```

## 实现与解释边界

- 同一验证集选出的单模型 checkpoint；完整合法 frontier 每轮比较，新暴露父节点继续参与。
- On-demand 在每次 eviction 为当前候选预测；同一次 eviction 内缓存结果，新暴露候选再批量补算。
- 预计算在请求结束等 mutation boundary 提交相关节点和祖先。eviction 只等待已存在任务，缺失 ticket 直接失败，零 LRU fallback。
- SWA 内部节点可在请求结束前成为候选；match/split、unfinished cache 和提前解锁边界也可提交，实际比例见上表。
- 时间条件化仍在比较时执行，没有改写全部缓存 hazard。为获得当前完整 frontier 最小值，原型逐轮重算便宜的标量价值；测得开销包含这部分和 TP 通信。
- V = path_tokens / node_tokens × Σp_k D_k；未来区间 0/2/5/10/20/60 秒，D_k=2^(-区间中点/20)，60 秒以外权重为零。
- M 按当前受压 Full 或 SWA pool 的 token 占用计算，同 pool 的固定 bytes/token 在排序中抵消；没有声称精确建模跨池联合释放或共享祖先的边际重算成本。
- 训练是旧 frozen frontier 的秒级标签，包含 cold 和右删失；不是无压力请求服务耗时。请求结束预测存在观测时刻分布偏移。
- 预计算缓存历史快照，仅因等待而条件化，不因其他请求推进 event/LRU 特征而全树重推；这些变化是两种执行策略的真实区别。
- 测试排除了训练请求来源中的 session、轨迹和首条 user message 重叠；公共 system prefix 仍可能重叠。
- 同 session 后续请求等待上轮结束，因此策略会改变实际到达时刻。这是闭环 serving 效果，不是固定时间线下仅比较 CPU 开销。
- 未命中 prompt tokens 包含首次访问，不能全部称为 eviction 导致的重算；请求/秒也不是饱和吞吐上限。
- 原生 SWA tombstone 强制清理不属于可自由选择的 victim；保留原生内存管理。
- 等待时长包括获取已完成 future 的开销；pending_waits 才表示读到未完成任务。

- MLP 推理计时是调用路径 wall time，包含线程被调度和抢占的影响，不等于 CPU 周期或 FLOPs。
- 预计算的 inc/dec lock 等边界采用了保守的相关节点刷新，并不表示每次锁变化都使模型输入失效。当前开销不能归因于仅在请求结束提交的理想实现。
