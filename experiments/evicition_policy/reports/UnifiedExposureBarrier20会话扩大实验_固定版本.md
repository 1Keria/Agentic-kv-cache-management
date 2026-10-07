# 20 会话 Unified Exposure Barrier 扩大实验

Suite：`/mnt/dai-sys/zhoulongsheng/agentkv/experiments/evicition_policy/results/runs/large_unified_barrier_20260929T110552Z_d1643dc1`

| 策略 | cached token | 命中率 | TTFT p95 | 延迟 p95 | 测量分钟 |
|---|---:|---:|---:|---:|---:|
| lru | 31,882,240 | 65.3488% | 15.543s | 44.520s | 36.33 |
| slru | 32,220,160 | 66.0414% | 15.416s | 45.956s | 36.46 |
| unified_exposure_barrier | 32,078,080 | 65.7502% | 15.721s | 44.157s | 36.60 |

## 相对 LRU

- **slru**：cached token +337,920；命中率 +0.6926 个百分点；TTFT p95 -0.82%；延迟 p95 +3.23%。
- **unified_exposure_barrier**：cached token +195,840；命中率 +0.4014 个百分点；TTFT p95 +1.15%；延迟 p95 -0.82%。

## 解释边界

- 每种策略只运行一次，顺序固定为 LRU、SLRU、Unified Barrier。
- 会话依赖回放会因完成时间不同改变全局请求交错，逐请求差异不是固定缓存状态反事实。
- 延迟与吞吐仍需重复运行和顺序互换后才能形成正式结论。
