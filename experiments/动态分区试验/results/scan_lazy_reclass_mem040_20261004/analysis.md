# 动态分区受控实验结果

## scan_lazy_reclass_mem040_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 78.4695% | 85.8887% | 38.7002% | 732928 | 76.1390 | 4536.2260 |
| borrow_lazy_reclass | 78.4969% | 85.8887% | 38.8745% | 733184 | 76.6260 | 2827.0650 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 60672 | 133376 | agent=151988 / request=180044 | agent=6777 / request=0 |
| borrow_lazy_reclass | 60672 | 132096 | agent=150964 / request=180044 | agent=5753 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


