# 动态分区受控实验结果

## request_agent_request_hysteresis

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 86.0088% | 92.0062% | 21.7821% | 7669760 | 386.3650 | 615.3770 |
| borrow | 88.0557% | 92.6842% | 38.4885% | 7852288 | 380.8860 | 780.4640 |

- borrow_vs_fixed: 总体命中率 2.3799%，Agent 命中率 0.7369%，普通请求命中率 76.6978%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1003776 | 1100288 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 881408 | 881408 | agent=206708 / request=430220 | agent=0 / request=42944 |


