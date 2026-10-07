# 双向复用与扫描压力的受控 workload

这是基于真实 OpenHands / WildChat 请求内容的受控压力构造，不是未经变换的自然流量。它用于检查“隔离扫描干扰”与“利用闲置保障容量”能否同时发生。

共 1,277 个请求：211 个原始 Agent turn、1,050 个普通背景 turn、16 个带确定性长前缀的普通热请求。Agent 与普通背景请求的内容不变。两个普通热 session 各取真实对话的前四轮，并添加相互不同、每条链内相同的 32,000 字符 system 前缀；回访时各重复末轮 prompt 四次。服务实际 token 化后，两个末轮 prompt 分别为 17,381 和 17,729 token，合计工作集约 35.1K token，低于本次普通区约 70.4K token 的 Full 保障容量。

| 请求组 | session 启动时间 | 请求数 | 用途 |
|---|---:|---:|---|
| 普通背景第一组 | 0–40 s | 554 | 普通短请求的扫描干扰 |
| 普通热链预热 | 60 / 66 s | 8 | 建立可复用长前缀 |
| Agent session | 90–110 s | 211 | 长链复用与容量压力 |
| 普通热链回访 | 270 / 276 s | 8 | 检查末轮缓存是否跨 Agent 压力保留 |
| 普通背景后一组 | 300–340 s | 496 | 再次施加普通流量干扰 |

时间指 session 启动时刻。session 内按完成后再等待工具/请求间隔的方式回放，因此各组实际执行时间可能重叠；它们不是严格串行阶段。回放使用固定输出 16 token、`gap_scale=0.1`。历史 assistant 内容来自 trace，后续输入不依赖本次生成的 16 token。

关键判据是热链回访组的**第一条请求**是否命中：后续三次重复可能在本组内重新预热，不能用它们的命中单独证明跨阶段保留。此次末轮回访是对最新缓存端点的重复访问，不再从更早的第一轮倒放；SWA 对这两种访问的可复用条件不同。

`verification.json` 保存使用服务端 DeepSeek V4 编码器验证的 token 长度、相邻输入 LCP，以及输出预算 16 token 时的分类混淆矩阵：211 / 211 Agent、1,066 / 1,066 普通请求均分类正确。`manifest.json` 保存源数据与生成 workload 的 SHA-256。

生成命令：

```bash
python experiments/动态分区试验/scripts/build_bidirectional_reuse_workload.py \
  --source experiments/固定分区试验对比/data/token_balanced_openhands_wildchat/workload.jsonl \
  --output-dir experiments/动态分区试验/data/bidirectional_reuse_calibrated \
  --request-sessions 2 --request-turns 4 --header-chars 32000 \
  --return-last-prompt --request-first-start-s 60 \
  --request-start-spacing-s 6 --request-second-start-s 270 \
  --agent-start-s 90 --agent-end-s 110 \
  --background-workload-dir experiments/动态分区试验/data/request_agent_request
```

三组服务对照使用相同文件：`unified` 关闭分类/分区，`fixed` 固定 61/39 保障，`borrow` 固定保障与空闲借用。它们使用同一工作区引擎、相同物理池和区内 LRU；未单独运行完全未修改的上游引擎。
