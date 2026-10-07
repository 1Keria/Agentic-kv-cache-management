# 动态分区受控实验结果

## mixed_scaled_borrow

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 87.9638% | 92.6560% | 37.7154% | 7844096 | 354.4210 | 632.9320 |
| borrow | 87.6509% | 92.3892% | 36.9086% | 7816192 | 353.5160 | 606.6770 |

- borrow_vs_fixed: 总体命中率 -0.3557%，Agent 命中率 -0.2879%，普通请求命中率 -2.1392%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 807680 | 888576 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 856832 | 912384 | agent=275060 / request=335756 | agent=27456 / request=0 |


## request_agent_request_borrow

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 84.6423% | 90.5655% | 21.2107% | 7547904 | 383.6280 | 644.5790 |
| borrow | 88.0844% | 92.6968% | 38.6902% | 7854848 | 381.1270 | 618.7470 |

- borrow_vs_fixed: 总体命中率 4.0666%，Agent 命中率 2.3533%，普通请求命中率 82.4089%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1124864 | 1222912 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 877824 | 877824 | agent=206708 / request=430220 | agent=0 / request=42944 |


