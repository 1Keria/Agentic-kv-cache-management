# 动态分区受控实验结果

## scan_mixed_256_priority

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 79.6755% | 87.8074% | 36.0853% | 744192 | 76.4200 | 3076.8965 |
| borrow | 79.6207% | 87.4497% | 37.6542% | 743680 | 77.4380 | 2821.9880 |

- borrow_vs_fixed: 总体命中率 -0.0688%，Agent 命中率 -0.4074%，普通请求命中率 4.3478%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 71680 | 130816 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 62976 | 130048 | agent=158900 / request=180044 | agent=14713 / request=0 |


