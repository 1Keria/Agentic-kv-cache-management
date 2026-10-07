# 动态分区受控实验结果

## mixed_scaled_pair_historygate_rep1_mem045_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 89.0260% | 93.7043% | 38.9255% | 7938816 | 350.0310 | 603.8130 |
| elastic | 90.6136% | 95.1922% | 41.5810% | 8080384 | 343.9200 | 613.1800 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 675328 | 787456 | agent=199284 / request=335756 | agent=832 / request=192 |
| elastic | 317952 | 649216 | agent=187252 / request=124300 | agent=18752 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


