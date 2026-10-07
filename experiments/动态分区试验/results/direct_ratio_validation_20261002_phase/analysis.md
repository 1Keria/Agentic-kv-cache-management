# 动态分区受控实验结果

## request_agent_request_direct_ratio_session

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 87.6825% | 94.2160% | 17.7148% | 7819008 | 380.6600 | 514.2980 |
| dynamic | 87.6423% | 93.7546% | 22.1855% | 7815424 | 381.0800 | 519.4840 |
| borrow | 90.3322% | 94.9473% | 40.9087% | 8055296 | 380.3880 | 481.5680 |

- dynamic_vs_fixed: 总体命中率变化 -0.0402 pp，Agent 命中率变化 -0.4614 pp，普通请求命中率变化 4.4707 pp。
- borrow_vs_fixed: 总体命中率变化 2.6497 pp，Agent 命中率变化 0.7313 pp，普通请求命中率变化 23.1939 pp。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 857088 | 952832 | agent=0 / request=0 | agent=0 / request=0 |
| dynamic | 854528 | 955392 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 286464 | 675584 | agent=137844 / request=108428 | agent=0 / request=40128 |

到达阶段按 session 分组；阶段内各 turn 等上一轮完成后才发送，实际执行区间可能重叠。
未命中输入包含首次新增内容和缓存丢失后的计算，不能直接称为驱逐导致的额外重算。
可借用空闲 token 表示对侧剩余保障容量；已标记 borrowed 的缓存量见 `*_cached_borrowed_tokens`。

- dynamic ratio: 0.61 -> 0.5697487950391462，范围 [0.4460038676907778, 0.7429057258876506]，更新 64 次。

