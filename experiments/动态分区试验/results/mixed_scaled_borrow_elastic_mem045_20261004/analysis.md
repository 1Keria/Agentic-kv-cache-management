# 动态分区受控实验结果

## mixed_scaled_borrow_elastic_mem045_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 88.9485% | 93.5882% | 39.2616% | 7931904 | 353.1310 | 686.4150 |
| elastic | 90.4758% | 95.1576% | 40.3373% | 8068096 | 346.2770 | 601.0600 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 661248 | 796416 | agent=216436 / request=336012 | agent=320 / request=0 |
| elastic | 280320 | 661248 | agent=466944 / request=215553 | agent=46592 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


