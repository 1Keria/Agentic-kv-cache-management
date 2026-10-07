# 动态分区受控实验结果

## compact4_borrow_elastic_mem035_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 32.6415% | 32.0662% | 61.9644% | 448512 | 243.4790 | 912.8970 |
| elastic | 33.4985% | 32.9400% | 61.9644% | 460288 | 238.1850 | 730.5410 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 167936 | 903168 | agent=66292 / request=0 | agent=2893 / request=2483 |
| elastic | 408064 | 891392 | agent=140288 / request=25601 | agent=10240 / request=5889 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


