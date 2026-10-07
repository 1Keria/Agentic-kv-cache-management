# 动态分区受控实验结果

## scan128_serial_ratio061_mem035_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 78.3916% | 83.7144% | 49.2865% | 402944 | 451.3230 | 260.1435 |
| borrow | 78.9395% | 84.3625% | 49.2865% | 405760 | 452.6440 | 255.5830 |

- borrow_vs_fixed: 总体命中率变化 0.5479 pp，Agent 命中率变化 0.6481 pp，普通请求命中率变化 0.0000 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 37376 | 87808 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 7936 | 78592 | agent=46324 / request=46348 | agent=0 / request=5043 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


