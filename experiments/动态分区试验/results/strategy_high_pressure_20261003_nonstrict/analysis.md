# 动态分区受控实验结果

## requestheavy_mem035_swa020

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 87.7381% | 89.2370% | 66.0244% | 2528768 | 352.1630 | 340.5290 |
| borrow_request_reclass | 87.7381% | 89.2370% | 66.0244% | 2528768 | 370.8580 | 368.1855 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 248320 | 320000 | agent=16484 / request=20380 | agent=0 / request=11724 |
| borrow_request_reclass | 248320 | 320000 | agent=16484 / request=20380 | agent=0 / request=11724 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


