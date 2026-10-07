# 动态分区受控实验结果

## mixed_scaled_old_borrow

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 88.9055% | 93.4972% | 39.7322% | 7928064 | 348.2510 | 678.6020 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 750848 | 797952 | agent=275060 / request=336012 | agent=27456 / request=0 |


