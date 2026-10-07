# 动态分区受控实验结果

## mixed_scaled_exactpages

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 89.7409% | 94.5236% | 38.5221% | 8002560 | 347.3940 | 630.3780 |
| borrow | 90.4758% | 95.0603% | 41.3793% | 8068096 | 346.1780 | 694.1170 |

- borrow_vs_fixed: 总体命中率 0.8189%，Agent 命中率 0.5678%，普通请求命中率 7.4170%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 673792 | 727552 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 504576 | 663296 | agent=223860 / request=267404 | agent=26944 / request=0 |


## request_agent_request_exactpages

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 88.0873% | 94.9473% | 14.6223% | 7855104 | 381.1420 | 521.2100 |
| borrow | 90.4786% | 95.1922% | 40.0012% | 8068352 | 379.9590 | 484.7640 |

- borrow_vs_fixed: 总体命中率 2.7147%，Agent 命中率 0.2579%，普通请求命中率 173.5630%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 834816 | 928512 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 616960 | 665088 | agent=157044 / request=430220 | agent=0 / request=42944 |


## scan_mixed_256_exactpages

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 80.5799% | 87.8074% | 41.8380% | 752640 | 72.3510 | 3030.6640 |
| borrow | 80.8814% | 87.8074% | 43.7556% | 755456 | 72.6750 | 3612.3170 |

- borrow_vs_fixed: 总体命中率 0.3742%，Agent 命中率 0.0000%，普通请求命中率 4.5834%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 52992 | 87552 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 55552 | 88320 | agent=254068 / request=353676 | agent=25152 / request=0 |


