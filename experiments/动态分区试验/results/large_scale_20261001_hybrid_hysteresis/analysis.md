# 动态分区受控实验结果

## mixed_scaled_lowmem040_hybrid_hysteresis

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 84.0797% | 90.2014% | 18.5215% | 7497728 | 359.0380 | 749.8480 |
| borrow | 86.1639% | 91.8179% | 25.6142% | 7683584 | 352.4650 | 715.9630 |

- borrow_vs_fixed: 总体命中率 2.4788%，Agent 命中率 1.7921%，普通请求命中率 38.2944%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1171456 | 1275904 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 666112 | 1111808 | agent=122548 / request=588 | agent=14713 / request=1159 |


## request_agent_request_lowmem040_hybrid_hysteresis

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 86.2586% | 93.7357% | 6.1851% | 7692032 | 380.4440 | 585.3690 |
| borrow | 58.2426% | 62.4476% | 13.2105% | 5193728 | 447.4690 | 2277.5960 |

- borrow_vs_fixed: 总体命中率 -32.4791%，Agent 命中率 -33.3791%，普通请求命中率 113.5859%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1001216 | 1106688 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 1719808 | 3600640 | agent=112820 / request=2124 | agent=3961 / request=22151 |


