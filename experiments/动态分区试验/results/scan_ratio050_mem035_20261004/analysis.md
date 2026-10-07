# 动态分区受控实验结果

## scan_ratio050_mem035_20261004

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 26.9422% | 31.9684% | 0.0000% | 251648 | 123.8370 | 13049.9640 |
| borrow | 55.9400% | 64.7499% | 8.7163% | 522496 | 101.5650 | 7008.0980 |

- borrow_vs_fixed: 总体命中率变化 28.9978 pp，Agent 命中率变化 32.7815 pp，普通请求命中率变化 8.7163 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 547584 | 655360 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 243712 | 364032 | agent=87424 / request=13696 | agent=8448 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


