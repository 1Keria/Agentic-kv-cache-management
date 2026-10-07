# 动态分区受控实验结果

## mixed_scaled_lowmem040_agent_safe_hysteresis

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 81.4672% | 87.4768% | 17.1097% | 7264768 | 362.5340 | 880.6020 |
| borrow | 86.0031% | 91.9026% | 22.8242% | 7669248 | 354.8480 | 719.5090 |

- borrow_vs_fixed: 总体命中率 5.5678%，Agent 命中率 5.0594%，普通请求命中率 33.3992%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1380608 | 1502720 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 778752 | 1127424 | agent=138420 / request=0 | agent=17273 / request=0 |


## mixed_scaled_lowmem040_agent_safe_hysteresis_16384

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 85.5524% | 92.1977% | 14.3870% | 7629056 | 352.5000 | 928.3510 |
| borrow | 86.1064% | 91.6798% | 26.4209% | 7678464 | 356.3130 | 710.8100 |

- borrow_vs_fixed: 总体命中率 0.6476%，Agent 命中率 -0.5617%，普通请求命中率 83.6443%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1043200 | 1139712 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 746752 | 1100032 | agent=127668 / request=0 | agent=17273 / request=0 |


## request_agent_request_lowmem040_agent_safe_hysteresis

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 85.4777% | 92.6591% | 8.5717% | 7622400 | 380.9430 | 686.6810 |
| borrow | 85.4835% | 92.4268% | 11.1264% | 7622912 | 386.6830 | 746.9810 |

- borrow_vs_fixed: 总体命中率 0.0068%，Agent 命中率 -0.2507%，普通请求命中率 29.8039%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1054464 | 1165056 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 789760 | 1165056 | agent=95924 / request=40524 | agent=0 / request=27015 |


## scan_mixed_256_agent_safe_hysteresis_16384

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 76.3317% | 84.1000% | 34.6907% | 712960 | 72.7290 | 2828.6985 |
| borrow | 79.6755% | 87.0920% | 39.9205% | 744192 | 72.1370 | 3228.5440 |

- borrow_vs_fixed: 总体命中率 4.3806%，Agent 命中率 3.5577%，普通请求命中率 15.0755%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 96000 | 161280 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 53760 | 118528 | agent=157620 / request=180300 | agent=9849 / request=0 |


## scan_mixed_256_agent_safe_hysteresis_8192

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 76.3043% | 83.7423% | 36.4340% | 712704 | 76.2510 | 2956.2005 |
| borrow | 79.1821% | 87.5148% | 34.5164% | 739584 | 74.6050 | 2854.6420 |

- borrow_vs_fixed: 总体命中率 3.7715%，Agent 命中率 4.5049%，普通请求命中率 -5.2632%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 95488 | 159488 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 71424 | 125952 | agent=166068 / request=180300 | agent=15993 / request=0 |


## scan_mixed_256_ratio040_agent_safe

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 80.4977% | 87.4172% | 43.4070% | 751872 | 75.5870 | 3555.8490 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 49152 | 121856 | agent=241408 / request=87296 | agent=7117 / request=0 |


## scan_mixed_256_ratio080_agent_safe

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 78.4147% | 87.8074% | 28.0664% | 732416 | 81.1710 | 2845.8855 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 78592 | 134656 | agent=69120 / request=277760 | agent=4762 / request=0 |


