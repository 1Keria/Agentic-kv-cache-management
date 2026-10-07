# 动态分区受控实验结果

## mixed_scaled_batchfix2

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 89.2557% | 94.0402% | 38.0179% | 7959296 | 343.5600 | 682.6390 |
| borrow | 89.1380% | 93.6824% | 40.4718% | 7948800 | 353.4470 | 751.0430 |

- borrow_vs_fixed: 总体命中率 -0.1319%，Agent 命中率 -0.3805%，普通请求命中率 6.4546%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 695552 | 772096 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 630784 | 777728 | agent=238708 / request=267404 | agent=27456 / request=0 |


## request_agent_request_batchfix2

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 85.6959% | 91.9403% | 18.8241% | 7641856 | 385.9650 | 701.0680 |
| borrow | 88.0069% | 92.6873% | 37.8834% | 7847936 | 380.1680 | 648.0280 |

- borrow_vs_fixed: 总体命中率 2.6967%，Agent 命中率 0.8125%，普通请求命中率 101.2495%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1040896 | 1132288 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 823552 | 883968 | agent=145268 / request=430220 | agent=0 / request=42944 |


