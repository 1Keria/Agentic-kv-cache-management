# 动态分区受控实验结果

## scan_mixed_256_tier

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| elastic | 78.2777% | 85.4659% | 39.7461% | 731136 | 72.7180 | 2918.2800 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| elastic | 65280 | 131840 | agent=327936 / request=277761 | agent=25959 / request=2151 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


## scan_mixed_256_tier_both

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 80.2236% | 87.4497% | 41.4894% | 749312 | 81.2430 | 2661.7135 |
| elastic | 79.7029% | 87.5148% | 37.8286% | 744448 | 83.7330 | 2963.8550 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 63744 | 122112 | agent=147124 / request=193612 | agent=10617 / request=0 |
| elastic | 59136 | 132864 | agent=332800 / request=264193 | agent=26215 / request=1127 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


