# 动态分区受控实验结果

## fixed_borrow_pair_20261003

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 79.4014% | 87.8074% | 34.3421% | 741632 | 77.5530 | 2821.5520 |
| borrow | 79.8399% | 87.8074% | 37.1313% | 745728 | 75.3570 | 2849.0815 |

- borrow_vs_fixed: 总体命中率变化 0.4385 pp，Agent 命中率变化 0.0000 pp，普通请求命中率变化 2.7892 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 69888 | 129792 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 64768 | 122368 | agent=150708 / request=193612 | agent=3705 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


