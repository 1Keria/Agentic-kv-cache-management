# 动态分区受控实验结果

## mixed_scaled_pair_historygate_rep2_mem045_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 89.8471% | 94.5769% | 39.1944% | 8012032 | 348.5170 | 575.6680 |
| elastic | 90.4385% | 95.1137% | 40.3709% | 8064768 | 348.2000 | 573.2270 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 441856 | 716544 | agent=218228 / request=151692 | agent=11072 / request=0 |
| elastic | 397824 | 664832 | agent=190324 / request=188812 | agent=14912 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


