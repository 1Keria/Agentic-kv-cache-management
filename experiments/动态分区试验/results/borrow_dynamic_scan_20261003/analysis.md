# 动态分区受控实验结果

## borrow_dynamic_scan_20261003

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 79.2369% | 87.3521% | 35.7367% | 740096 | 77.2820 | 4067.5295 |
| borrow_dynamic | 79.8399% | 87.4497% | 39.0488% | 745728 | 78.5300 | 5391.0130 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 60928 | 127488 | agent=156596 / request=180044 | agent=2681 / request=0 |
| borrow_dynamic | 65792 | 129536 | agent=152667 / request=189861 | agent=6384 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


