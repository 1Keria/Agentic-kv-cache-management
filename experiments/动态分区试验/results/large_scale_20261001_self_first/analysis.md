# 动态分区受控实验结果

## request_agent_request_lowmem040_large

| 策略 | 总体命中率 | Agent 命中率 | 普通请求命中率 | cached token | 墙钟秒 | TTFT p50 |
|---|---:|---:|---:|---:|---:|---:|
| fixed | 83.6261% | 90.8794% | 5.9498% | 7457280 | 381.7890 | 606.1780 |
| borrow | 85.0557% | 91.1524% | 19.7653% | 7584768 | 381.2330 | 795.8150 |

- borrow_vs_fixed: 总体命中率 1.7095%，Agent 命中率 0.3004%，普通请求命中率 232.2011%。

| 策略 | Full 驱逐 token | SWA 驱逐 token | Full 可借用空闲 token（Agent / Request） | SWA 可借用空闲 token（Agent / Request） |
|---|---:|---:|---:|---:|
| fixed | 1208064 | 1327104 | agent=0 / request=0 | agent=0 / request=0 |
| borrow | 987136 | 1174784 | agent=110772 / request=184908 | agent=0 / request=27015 |


