# 动态分区受控实验结果

## mixed_scaled_lowmem040_large

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 81.7974% | 87.8598% | 16.8744% | 7294208 | 366.5920 | 1199.9320 |
| borrow | 85.9801% | 91.4224% | 27.6983% | 7667200 | 357.6130 | 774.9340 |

- borrow_vs_fixed: 总体命中率 5.1135%，Agent 命中率 4.0549%，普通请求命中率 64.1439%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1357568 | 1478656 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 1000704 | 1110016 | agent=151220 / request=175948 | agent=17273 / request=0 |


## request_agent_request_lowmem040_large

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 85.1131% | 92.4331% | 6.7229% | 7589888 | 385.1310 | 666.5940 |
| borrow | 84.7773% | 90.5498% | 22.9586% | 7559936 | 382.4920 | 2284.5310 |

- borrow_vs_fixed: 总体命中率 -0.3945%，Agent 命中率 -2.0375%，普通请求命中率 241.4985%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1197824 | 1207296 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 1175808 | 1199872 | agent=105140 / request=270156 | agent=0 / request=27015 |


