# 动态分区受控实验结果

## request_agent_request_borrow_elastic_mem045_mi16_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 89.7724% | 95.0823% | 32.9085% | 8005376 | 444.5680 | 406.3640 |
| elastic | 88.9887% | 94.6837% | 28.0008% | 7935488 | 448.9070 | 423.8070 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 321024 | 725248 | agent=162420 / request=82572 | agent=0 / request=8896 |
| elastic | 513280 | 794880 | agent=467456 / request=354049 | agent=27904 / request=16641 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


