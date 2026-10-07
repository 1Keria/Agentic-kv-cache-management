# 动态分区受控实验结果

## high_pressure_fixed_borrow_20261003_inflight2

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 89.0191% | 89.1325% | 77.4555% | 2423552 | 348.8210 | 331.6110 |
| borrow | 89.0191% | 89.1325% | 77.4555% | 2423552 | 355.4380 | 332.8545 |

- borrow_vs_fixed: 总体命中率变化 0.0000 pp，Agent 命中率变化 0.0000 pp，普通请求命中率变化 0.0000 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 235008 | 265472 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 194048 | 263168 | agent=35940 / request=0 | agent=3892 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


