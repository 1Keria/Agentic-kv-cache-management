# 动态分区受控实验结果

## request_agent_request_activity_floor_mem045_mi16_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 89.9590% | 95.1922% | 33.9169% | 8022016 | 445.8120 | 409.7650 |
| elastic | 89.8270% | 94.8971% | 35.5304% | 8010240 | 450.5280 | 471.6990 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 344576 | 706304 | agent=171892 / request=108428 | agent=0 / request=8896 |
| elastic | 416256 | 718592 | agent=170356 / request=165260 | agent=0 / request=9664 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


