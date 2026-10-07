# 动态分区受控实验结果

## mixed_scaled_lowmem040_large

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 82.1591% | 88.5441% | 13.7819% | 7326464 | 363.8970 | 819.6630 |
| borrow | 81.4385% | 87.6244% | 15.1937% | 7262208 | 361.7280 | 1693.8100 |

- borrow_vs_fixed: 总体命中率 -0.8771%，Agent 命中率 -1.0387%，普通请求命中率 10.2439%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1340416 | 1463552 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 1109248 | 1544704 | agent=153268 / request=0 | agent=16761 / request=0 |


## request_agent_request_lowmem040_large

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 86.7524% | 94.1814% | 7.1935% | 7736064 | 380.7370 | 690.1220 |
| borrow | 85.3141% | 91.0081% | 24.3368% | 7607808 | 380.6140 | 1853.7460 |

- borrow_vs_fixed: 总体命中率 -1.6579%，Agent 命中率 -3.3693%，普通请求命中率 238.3165%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1047552 | 1060864 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 828416 | 1151744 | agent=90804 / request=53324 | agent=0 / request=27015 |


