# 结果目录

保存以下内容：

- `offline_ratio_selection.json` / `.md`：离线 Agent 缓存容量比例扫描结果；
- `selected_ratio.env`：当前选中的 `AGENT_CACHE_CAPACITY_RATIO=0.58`；
- 统一缓存完整 GPU 回放结果；
- 固定分区完整 GPU 回放结果；
- 两次实验的汇总对比报告。

正式配对运行写入 `runs/<UTC 时间>/`，包含启动参数、workload SHA256、
模型、Full/SWA KV 容量、两次回放、`/server_info`、服务日志和对比报告。
