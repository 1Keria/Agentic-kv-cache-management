# 动态分区受控实验结果

## mixed_mem030

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|


## mixed_mem035

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 34.9949% | 38.2627% | 0.0000% | 3120640 | 615.9580 | 13252.5040 |
| borrow | 64.2511% | 70.2508% | 0.0000% | 5729536 | 498.7820 | 14549.9750 |

- borrow_vs_fixed: 总体命中率 83.6013%，Agent 命中率 83.6013%，普通请求命中率 -。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 5321216 | 5708032 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 2190848 | 3073280 | agent=62196 / request=7692 | agent=6989 / request=0 |


## mixed_mem040

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 83.7036% | 89.3633% | 23.0931% | 7464192 | 364.0810 | 671.0930 |
| borrow | 84.4270% | 89.7462% | 27.4630% | 7528704 | 359.2140 | 722.6150 |

- borrow_vs_fixed: 总体命中率 0.8642%，Agent 命中率 0.4285%，普通请求命中率 18.9230%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1188096 | 1309440 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 857088 | 1251072 | agent=147636 / request=0 | agent=17273 / request=0 |


## mixed_mem040_ratio040

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 74.5113% | 78.1387% | 35.6649% | 6644480 | 405.6630 | 740.7960 |
| borrow | 85.8796% | 91.4318% | 26.4209% | 7658240 | 356.4000 | 808.8310 |

- borrow_vs_fixed: 总体命中率 15.2571%，Agent 命中率 17.0122%，普通请求命中率 -25.9190%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1998848 | 2169600 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 822528 | 1134336 | agent=259584 / request=0 | agent=25549 / request=0 |


## mixed_mem040_ratio080

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 84.4816% | 91.8901% | 5.1430% | 7533568 | 356.4700 | 779.6620 |
| borrow | 86.4825% | 92.3013% | 24.1688% | 7712000 | 353.6310 | 741.6890 |

- borrow_vs_fixed: 总体命中率 2.3684%，Agent 命中率 0.4475%，普通请求命中率 369.9358%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1128704 | 1228288 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 797696 | 1118208 | agent=50688 / request=75776 | agent=8858 / request=0 |


## mixed_mem045_repeat

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 89.5916% | 94.5738% | 36.2363% | 7989248 | 344.1910 | 659.7720 |
| borrow | 89.3734% | 93.9335% | 40.5390% | 7969792 | 348.9190 | 689.9990 |

- borrow_vs_fixed: 总体命中率 -0.2435%，Agent 命中率 -0.6770%，普通请求命中率 11.8740%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 682240 | 741632 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 389632 | 757248 | agent=212852 / request=151692 | agent=16448 / request=0 |


## phase_mem035

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 27.7146% | 30.2774% | 0.2689% | 2471424 | 635.4610 | 10542.7430 |
| borrow | 41.4743% | 45.2592% | 0.9412% | 3698432 | 577.3380 | 10964.7790 |

- borrow_vs_fixed: 总体命中率 49.6478%，Agent 命中率 49.4818%，普通请求命中率 250.0186%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 5895680 | 6350848 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 3143936 | 5088000 | agent=66036 / request=0 | agent=6989 / request=0 |


## scan256_mem035

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 39.5499% | 46.9282% | 0.0000% | 369408 | 113.9170 | 9872.2125 |
| borrow | 33.4928% | 39.7410% | 0.0000% | 312832 | 109.9090 | 9811.5445 |

- borrow_vs_fixed: 总体命中率 -15.3151%，Agent 命中率 -15.3153%，普通请求命中率 -。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 438272 | 544000 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 341504 | 580864 | agent=70388 / request=24332 | agent=6989 / request=0 |


## scan256_mem035_reverse

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 51.8836% | 60.6522% | 4.8811% | 484608 | 105.4650 | 9000.6795 |
| fixed | 43.1130% | 51.1560% | 0.0000% | 402688 | 106.6130 | 9653.2380 |

- borrow_vs_fixed: 总体命中率 20.3433%，Agent 命中率 18.5632%，普通请求命中率 -。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 301056 | 421120 | agent=67828 / request=33548 | agent=6989 / request=0 |
| fixed | 401152 | 504064 | agent=0 / request=0 | agent=0 / request=0 |


