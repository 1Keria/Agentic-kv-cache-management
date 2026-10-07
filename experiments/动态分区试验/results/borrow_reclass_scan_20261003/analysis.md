# 动态分区受控实验结果

## scan_mixed_256

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 80.0866% | 87.5148% | 40.2691% | 748032 | 81.2090 | 3066.6935 |
| borrow_reclass | 79.2369% | 87.0920% | 37.1313% | 740096 | 75.9950 | 3355.1710 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 46592 | 117248 | agent=148916 / request=180044 | agent=11129 / request=0 |
| borrow_reclass | 59136 | 124416 | agent=147380 / request=193612 | agent=1913 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


