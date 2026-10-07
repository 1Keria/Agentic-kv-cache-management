# 动态分区受控实验结果

## scan_lowmem_030

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|


## scan_lowmem_040

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 77.5650% | 85.8887% | 32.9475% | 724480 | 74.2280 | 2816.9625 |
| borrow | 78.3599% | 85.8887% | 38.0029% | 731904 | 81.8180 | 3270.0660 |

- borrow_vs_fixed: 总体命中率 1.0248%，Agent 命中率 0.0000%，普通请求命中率 15.3438%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 91392 | 157952 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 85248 | 143360 | agent=156852 / request=193612 | agent=10617 / request=0 |


