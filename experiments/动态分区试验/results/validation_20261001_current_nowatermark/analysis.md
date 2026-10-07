# 动态分区受控实验结果

## mixed_scaled_current_nowatermark

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 89.3590% | 94.1249% | 38.3204% | 7968512 | 348.6770 | 569.4770 |
| borrow | 90.3810% | 95.1576% | 39.2280% | 8059648 | 348.1670 | 621.6740 |

- borrow_vs_fixed: 总体命中率 1.1437%，Agent 命中率 1.0972%，普通请求命中率 2.3685%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 697856 | 761600 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 375040 | 670208 | agent=194164 / request=151692 | agent=23872 / request=0 |


## request_agent_request_current_nowatermark

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 87.2892% | 93.7357% | 18.2526% | 7783936 | 380.5810 | 550.7030 |
| borrow | 89.2758% | 93.7294% | 41.5810% | 7961088 | 379.6800 | 518.3910 |

- borrow_vs_fixed: 总体命中率 2.2759%，Agent 命中率 -0.0067%，普通请求命中率 127.8086%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 888064 | 991232 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 480256 | 772096 | agent=143476 / request=310668 | agent=0 / request=42944 |


