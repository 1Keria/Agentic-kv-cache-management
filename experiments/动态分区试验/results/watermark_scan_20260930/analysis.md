# 动态分区受控实验结果

## scan_mixed_256_hysteresis

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 80.7444% | 87.8074% | 42.8840% | 754176 | 68.3270 | 2726.9380 |
| borrow | 80.8814% | 87.8074% | 43.7556% | 755456 | 74.6810 | 4923.2165 |

- borrow_vs_fixed: 总体命中率 0.1697%，Agent 命中率 0.0000%，普通请求命中率 2.0325%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 51200 | 85760 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 66304 | 84736 | agent=264820 / request=353676 | agent=23360 / request=0 |


