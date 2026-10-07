# 动态分区受控实验结果

## scan_ratio061_mem035_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 49.6636% | 58.0830% | 4.5325% | 463872 | 111.8650 | 9504.6250 |
| borrow | 36.2610% | 43.0256% | 0.0000% | 338688 | 111.8860 | 9179.9320 |

- borrow_vs_fixed: 总体命中率变化 -13.4026 pp，Agent 命中率变化 -15.0574 pp，普通请求命中率变化 -4.5325 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 346624 | 446208 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 360960 | 549888 | agent=70388 / request=25612 | agent=6989 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


