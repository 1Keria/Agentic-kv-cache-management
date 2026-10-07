# 动态分区受控实验结果

## mixed_scaled_direct_ratio

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 89.0260% | 93.5474% | 40.6062% | 7938816 | 354.9440 | 710.1630 |
| dynamic | 89.6117% | 94.2882% | 39.5306% | 7991040 | 346.1280 | 601.0020 |
| borrow | 90.0940% | 94.9724% | 37.8498% | 8034048 | 345.6850 | 660.7530 |

- dynamic_vs_fixed: 总体命中率变化 0.5857 pp，Agent 命中率变化 0.7408 pp，普通请求命中率变化 -1.0756 pp。
- borrow_vs_fixed: 总体命中率变化 1.0680 pp，Agent 命中率变化 1.4250 pp，普通请求命中率变化 -2.7564 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 732928 | 792064 | agent=0 / request=0 | agent=0 / request=0 |
| dynamic | 691200 | 737024 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 409088 | 695552 | agent=217716 / request=151692 | agent=8000 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。

- dynamic ratio: 0.61 -> 0.6888700700410276，范围 [0.5127183960918333, 0.6888700700410276]，更新 27 次。

