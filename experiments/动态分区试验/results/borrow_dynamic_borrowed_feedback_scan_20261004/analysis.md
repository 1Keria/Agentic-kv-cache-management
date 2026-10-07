# 动态分区受控实验结果

## borrow_dynamic_borrowed_feedback_scan_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 78.4969% | 85.8887% | 38.8745% | 733184 | 82.6210 | 3301.3050 |
| borrow_dynamic | 78.0858% | 85.8887% | 36.2596% | 729344 | 78.7370 | 3690.0440 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 74752 | 143104 | agent=157620 / request=180300 | agent=5497 / request=0 |
| borrow_dynamic | 61952 | 136192 | agent=160684 / request=170580 | agent=9771 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


