# 动态分区受控实验结果

## mixed_scaled_batchfix

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 88.6327% | 93.3779% | 37.8162% | 7903744 | 348.5140 | 645.6100 |
| borrow | 88.1275% | 92.8317% | 37.7490% | 7858688 | 350.7090 | 626.6180 |

- borrow_vs_fixed: 总体命中率 -0.5700%，Agent 命中率 -0.5849%，普通请求命中率 -0.1777%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 749312 | 825856 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 713216 | 873472 | agent=237172 / request=267404 | agent=27456 / request=0 |


## scan_lowmem_040_batchfix

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 77.6473% | 85.7261% | 34.3421% | 725248 | 77.8400 | 3104.4505 |
| borrow | 79.5110% | 87.5148% | 36.6083% | 742656 | 78.8230 | 4319.9180 |

- borrow_vs_fixed: 总体命中率 2.4002%，Agent 命中率 2.0865%，普通请求命中率 6.5989%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 85760 | 148736 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 68608 | 123904 | agent=155060 / request=193612 | agent=9849 / request=0 |


