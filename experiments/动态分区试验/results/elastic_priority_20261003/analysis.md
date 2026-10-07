# 动态分区受控实验结果

## phase_stress_priority

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 41.6213% | 41.5553% | 61.9644% | 3405568 | 563.4300 | 1646.9830 |
| elastic | 39.3498% | 39.2765% | 61.9644% | 3219712 | 568.5130 | 1934.9660 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 2554112 | 4731392 | agent=66292 / request=0 | agent=2893 / request=0 |
| elastic | 3983872 | 4920064 | agent=140288 / request=25601 | agent=10240 / request=1281 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


## scan_mixed_256_priority

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 78.8258% | 87.5148% | 32.2502% | 736256 | 78.9920 | 3971.4685 |
| elastic | 80.2510% | 87.5148% | 41.3151% | 749568 | 83.1890 | 2983.8450 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 69632 | 128256 | agent=148660 / request=193612 | agent=2169 / request=0 |
| elastic | 53760 | 128000 | agent=329984 / request=264449 | agent=35431 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


