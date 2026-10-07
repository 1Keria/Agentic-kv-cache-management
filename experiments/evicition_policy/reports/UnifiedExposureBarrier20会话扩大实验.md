# 20 会话 Unified Exposure Barrier 扩大实验

Suite：`/mnt/dai-sys/zhoulongsheng/agentkv/experiments/evicition_policy/results/runs/large_unified_barrier_20260929T082959Z_7ce5cbe5`

| 策略 | cached token | 命中率 | TTFT p95 | 延迟 p95 | 测量分钟 |
|---|---:|---:|---:|---:|---:|
| lru | 28,297,216 | 58.0006% | 19.603s | 56.145s | 41.82 |
| slru | 32,184,320 | 65.9680% | 17.043s | 48.069s | 37.67 |
| unified_exposure_barrier | 31,135,232 | 63.8177% | 17.535s | 49.269s | 38.60 |

## 相对 LRU

- **slru**：cached token +3,887,104；命中率 +7.9674 个百分点；TTFT p95 -13.06%；延迟 p95 -14.38%。
- **unified_exposure_barrier**：cached token +2,838,016；命中率 +5.8171 个百分点；TTFT p95 -10.55%；延迟 p95 -12.25%。

## 解释边界

- 每种策略只运行一次，顺序固定为 LRU、SLRU、Unified Barrier。
- 会话依赖回放会因完成时间不同改变全局请求交错，逐请求差异不是固定缓存状态反事实。
- 延迟与吞吐仍需重复运行和顺序互换后才能形成正式结论。
