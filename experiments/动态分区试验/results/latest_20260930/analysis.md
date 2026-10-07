# 动态分区受控实验结果

## mixed_scaled_boundary_fix

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 87.1428% | 91.7363% | 37.9507% | 7770880 | 354.9090 | 704.1630 |
| borrow | 88.8021% | 93.2366% | 41.3121% | 7918848 | 350.0680 | 795.1320 |

- borrow_vs_fixed: 总体命中率 1.9041%，Agent 命中率 1.6354%，普通请求命中率 8.8573%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 877056 | 961024 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 678144 | 811008 | agent=253300 / request=267404 | agent=27456 / request=0 |


## mixed_scaled_latest_borrow

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 84.0452% | 88.1517% | 40.0684% | 7494656 | 366.7310 | 651.0790 |
| borrow | 87.7313% | 92.4770% | 36.9086% | 7823360 | 356.8130 | 774.2850 |

- borrow_vs_fixed: 总体命中率 4.3859%，Agent 命中率 4.9067%，普通请求命中率 -7.8860%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1140224 | 1238784 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 840192 | 905472 | agent=254068 / request=336012 | agent=27456 / request=0 |


## request_agent_request_boundary_fix

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 86.2069% | 92.4017% | 19.8661% | 7687424 | 384.9070 | 628.2010 |
| borrow | 88.0356% | 92.6968% | 38.1187% | 7850496 | 382.3700 | 756.1810 |

- borrow_vs_fixed: 总体命中率 2.1213%，Agent 命中率 0.3194%，普通请求命中率 91.8781%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 987648 | 1085184 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 761600 | 882432 | agent=161652 / request=360076 | agent=0 / request=42944 |


## scan_idle_borrow_061

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 80.6073% | 87.6774% | 42.7097% | 752896 | 71.7920 | 2727.0680 |
| borrow | 80.8814% | 87.8074% | 43.7556% | 755456 | 74.5400 | 2912.7230 |

- borrow_vs_fixed: 总体命中率 0.3400%，Agent 命中率 0.1483%，普通请求命中率 2.4489%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 51456 | 85504 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 65792 | 86784 | agent=264308 / request=353676 | agent=21824 / request=0 |


## scan_idle_borrow_061_boundary_fix

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 80.5799% | 87.8074% | 41.8380% | 752640 | 75.8980 | 3194.3070 |
| borrow | 80.5799% | 87.4497% | 43.7556% | 752640 | 76.7870 | 3802.6105 |

- borrow_vs_fixed: 总体命中率 0.0000%，Agent 命中率 -0.4074%，普通请求命中率 4.5834%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 51712 | 87296 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 37888 | 84480 | agent=249972 / request=340108 | agent=27456 / request=0 |


