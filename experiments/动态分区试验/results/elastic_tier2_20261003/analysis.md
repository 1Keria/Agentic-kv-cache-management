# 动态分区受控实验结果

## phase_stress_tier2

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 43.3139% | 43.2535% | 61.9644% | 3544064 | 563.6900 | 1850.9820 |
| elastic | 41.9091% | 41.8441% | 61.9644% | 3429120 | 566.7490 | 1814.3340 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 2163712 | 4592384 | agent=66292 / request=0 | agent=2893 / request=0 |
| elastic | 2592768 | 4705024 | agent=140288 / request=0 | agent=10240 / request=1281 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


## scan_mixed_256_tier2

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 77.6199% | 85.4659% | 35.5623% | 724992 | 77.1450 | 4028.2325 |
| elastic | 79.8673% | 87.5148% | 38.8745% | 745984 | 79.0620 | 2894.1480 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 78080 | 136960 | agent=153268 / request=193612 | agent=4729 / request=0 |
| elastic | 53760 | 120320 | agent=335616 / request=264449 | agent=35175 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


