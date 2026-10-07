# 动态分区受控实验结果

## scan_mixed_256_old

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 80.8814% | 87.8074% | 43.7556% | 755456 | 72.9560 | 3170.0390 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 66816 | 83968 | agent=265332 / request=353676 | agent=22592 / request=0 |


