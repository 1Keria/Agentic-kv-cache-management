# 动态分区受控实验结果

## scan_mixed_256_both

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 79.9770% | 87.0920% | 41.8380% | 747008 | 75.7820 | 3029.2200 |
| elastic | 78.1132% | 85.4659% | 38.7002% | 729600 | 77.6490 | 3291.5575 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 55808 | 115456 | agent=149172 / request=193612 | agent=2425 / request=0 |
| elastic | 62208 | 146432 | agent=324096 / request=264449 | agent=13927 / request=14439 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


