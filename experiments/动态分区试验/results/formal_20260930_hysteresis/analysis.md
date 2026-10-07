# 动态分区受控实验结果

## mixed_scaled_hysteresis

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 86.8327% | 91.3690% | 38.2532% | 7743232 | 357.6340 | 703.0830 |
| borrow | 87.1945% | 91.7049% | 38.8919% | 7775488 | 357.2870 | 781.4400 |

- borrow_vs_fixed: 总体命中率 0.4167%，Agent 命中率 0.3676%，普通请求命中率 1.6697%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 899328 | 991232 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 903424 | 953344 | agent=275060 / request=336012 | agent=27456 / request=0 |


