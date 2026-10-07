# 动态分区受控实验结果

## scan_mixed_256

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 80.1962% | 87.8074% | 39.3975% | 749056 | 76.7030 | 2823.3605 |
| elastic | 79.1273% | 87.1570% | 36.0853% | 739072 | 81.0200 | 4569.5855 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 58368 | 115456 | agent=148148 / request=193612 | agent=4985 / request=0 |
| elastic | 88064 | 147456 | agent=335872 / request=277761 | agent=31079 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


