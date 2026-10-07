# 动态分区受控实验结果

## scan_mixed_256

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| borrow | 78.4695% | 85.4659% | 40.9664% | 732928 | 80.0020 | 3269.1470 |
| elastic | 79.4014% | 86.6367% | 40.6178% | 741632 | 81.0860 | 3319.6670 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| borrow | 78848 | 146944 | agent=149172 / request=193612 | agent=3193 / request=2951 |
| elastic | 59904 | 132352 | agent=333312 / request=264449 | agent=35431 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


