# 动态分区受控实验结果

## bidirectional_mem035_threeway

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| unified | 60.4888% | 68.8665% | 0.0000% | 5616640 | 451.1360 | 2670.9120 |
| fixed | 33.4453% | 38.0775% | 0.0000% | 3105536 | 571.6790 | 5322.6250 |
| borrow | 63.1494% | 71.8955% | 0.0000% | 5863680 | 427.0910 | 2139.2750 |

- fixed_vs_unified: 总体命中率变化 -27.0435 pp，Agent 命中率变化 -30.7890 pp，普通请求命中率变化 0.0000 pp。
- borrow_vs_fixed: 总体命中率变化 29.7041 pp，Agent 命中率变化 33.8180 pp，普通请求命中率变化 0.0000 pp。
- borrow_vs_unified: 总体命中率变化 2.6606 pp，Agent 命中率变化 3.0290 pp，普通请求命中率变化 0.0000 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| unified | - | - | - | - |
| fixed | 5722112 | 6136064 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 2048000 | 3372800 | agent=61172 / request=10508 | agent=6989 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


## calibrated_mem035_native

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| native | 43.2488% | 48.6492% | 0.8864% | 3976960 | 620.9250 | 14421.6770 |


| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| native | - | - | - | - |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


## calibrated_mem035_threeway

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| unified | 40.1670% | 45.2874% | 0.0000% | 3693568 | 603.5330 | 11912.4000 |
| fixed | 26.2527% | 29.5994% | 0.0000% | 2414080 | 652.0490 | 12008.0360 |
| borrow | 46.5812% | 52.5194% | 0.0000% | 4283392 | 570.8380 | 12574.8790 |

- fixed_vs_unified: 总体命中率变化 -13.9143 pp，Agent 命中率变化 -15.6880 pp，普通请求命中率变化 0.0000 pp。
- borrow_vs_fixed: 总体命中率变化 20.3285 pp，Agent 命中率变化 22.9200 pp，普通请求命中率变化 0.0000 pp。
- borrow_vs_unified: 总体命中率变化 6.4142 pp，Agent 命中率变化 7.2320 pp，普通请求命中率变化 0.0000 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| unified | - | - | - | - |
| fixed | 6196480 | 6652928 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 2677504 | 4811264 | agent=70388 / request=0 | agent=6989 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


## phase_mem035_threeway

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| unified | 44.7900% | 48.9725% | 0.0000% | 3994112 | 567.5200 | 10781.5650 |
| fixed | 26.0065% | 28.4349% | 0.0000% | 2319104 | 638.2610 | 10222.1280 |
| borrow | 50.5977% | 55.3224% | 0.0000% | 4512000 | 540.3380 | 12223.4130 |

- fixed_vs_unified: 总体命中率变化 -18.7835 pp，Agent 命中率变化 -20.5376 pp，普通请求命中率变化 0.0000 pp。
- borrow_vs_fixed: 总体命中率变化 24.5912 pp，Agent 命中率变化 26.8875 pp，普通请求命中率变化 0.0000 pp。
- borrow_vs_unified: 总体命中率变化 5.8077 pp，Agent 命中率变化 6.3499 pp，普通请求命中率变化 0.0000 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| unified | - | - | - | - |
| fixed | 6042624 | 6524672 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 2712320 | 4283648 | agent=40436 / request=0 | agent=4685 / request=0 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。


