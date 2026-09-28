# `system` 消息与 Agent 请求的关系调查

## 结论

不能认为“有 system 消息就是 agent”，也不能认为“没有 system 消息就是普通请求”。

这里的 `n_system_messages` 不是 OpenAI、Anthropic 或其他通用 API 规定的输入字段，而是本项目
在 `models/request_classifier/features.py` 中从 `messages` 数组逐条检查
`message.role == "system"` 后得到的派生计数。线上请求通常只会携带 `messages`、
`instructions`、`tools` 等协议字段；是否存在名为 `n_system_messages` 的字段，取决于网关或
特征提取器自己的实现。

`system` 是消息协议中的指令/上下文角色，不是请求来源或执行方式的类型字段。它既可以
出现在普通聊天、摘要、翻译、数据抽取和客服请求中，也可以出现在 OpenHands、SWE-agent
等 agent 请求中。反过来，某些 agent 客户端会把系统指令放在 API 的 `instructions`、
`developer` 字段或服务端模板中，线上可见的 `messages` 里未必有 `role=system`。

形式化地说：

```text
has_system_message 不是 agent_like 的充分条件
has_system_message 不是 agent_like 的必要条件
```

## 官方协议语义

当前环境访问以下官方站点时请求超时，因此没有把无法打开的网页内容冒充成在线检索结果；
下面列出可复核的官方文档入口和本地上游实现位置：

- OpenAI Chat Completions API：<https://platform.openai.com/docs/api-reference/chat/create>
  的 `messages` 支持 `system`、`user`、`assistant` 等角色，接口没有规定 system 只用于 agent。
- OpenAI Responses API：<https://platform.openai.com/docs/api-reference/responses/create> 的
  `instructions` 是请求级模型指令，普通应用同样可以使用，不代表 agent 工作流。
- Anthropic Messages API：<https://docs.anthropic.com/en/api/messages> 将 `system` 作为独立的
  系统提示参数，普通消息请求和工具请求都可以使用。
- OpenAI 工具调用指南：<https://platform.openai.com/docs/guides/function-calling> 允许普通应用
  调用天气、数据库、搜索或业务函数；有工具也不自动等于 agent。

因此，协议层只能说明 system 是“给模型的指令上下文”，不能从它推出“请求由 agent 应用发起”。
同样，缺少 system 也只能说明当前可见消息中没有这个角色，不能说明请求一定是普通应用。

本仓库内的上游实现提供了直接例子：

- `Engine/vllm/docs/getting_started/quickstart.md` 的普通问题
  “Who won the world series in 2020?” 带有 `system: You are a helpful assistant.`。
- `Engine/vllm/vllm/entrypoints/openai/responses/utils.py` 会把普通 Responses 请求的
  `instructions` 转成 system 消息；这不是 agent 专属路径。
- `Agent/mini-swe-agent/src/minisweagent/agents/default.py` 的 agent 模板也把 system
  消息作为第一条消息。它证明 system 对 agent 常见，但不能证明其专属性。
- `Agent/SWE-agent/sweagent/agent/models.py` 支持把 system 转成 user，因为部分模型不支持
  system role；因此 agent 请求可能没有 system role。

## 当前数据复核

我们在去重后的 66,592 条 workload 记录中发现并人工核查了 6 条 GLM 普通请求。它们是：

| GLM 原始行号 | 请求内容 |
| ---: | --- |
| 1355 | 股票估值分析与 Excel 报告 |
| 1520 | 劳动争议仲裁材料分析 |
| 1696 | 银行客户交易合规自查 |
| 1749 | 鸡舍建筑设计图片生成 |
| 1750 | 化工企业事故案例整理 |
| 1848 | 行政事业单位票据管理制度撰写 |

这 6 条没有 system 消息、工具定义或工具调用，所以它们直接否定了“GLM 来源必然是
agent”的标签假设。但这只是已核查的反例，不足以证明 GLM 中只有这 6 条普通请求；其余
GLM 请求仍需要更完整的语义审计或可靠上游标签。

在当前已修正缓存中，`n_system_messages > 0` 恰好把 24,290 条 agent-like 和 42,302 条
request 分开，因此 1 维模型在该数据上得到 100%。这是数据集标签和模板生成方式的结果，
不是消息协议层面的普遍规律。

去重缓存的逐来源交叉统计如下：

| 来源 | 标签 | `n_system_messages = 0` | `n_system_messages > 0` |
| --- | ---: | ---: | ---: |
| GLM | agent-like 16,553；request 6 | request 6 | agent-like 16,553 |
| SkillsBench/OpenHands | agent-like 7,737 | 0 | agent-like 7,737 |
| WildChat | request 42,296 | request 42,296 | 0 |

这个表说明的是当前三类数据的采集/转换模板，而不是 agent 的定义：GLM 的 6 条普通请求和
WildChat 恰好没有 system，SkillsBench 恰好都有 system。只要新增一个带 system 的普通应用
请求或一个把 system 放入 `developer`/`instructions`/服务端模板的 agent 请求，这个规则就会
产生误判。

还要注意验证集本身存在标签先验：当前标签策略只人工把上述 6 条 GLM 记录改成 `request`，
其余 GLM 记录仍暂按 `agent_like` 保留。因此，GLM 上的 100% 不是独立人工语义标注得到的
泛化证明，而是“已知反例修正后，特征与当前标签规则一致”的结果；完整 GLM 语义审计前，
不能据此宣称 system 角色可以识别 agent。

## 对分类器设计的影响

分类目标必须先定义清楚：

1. **应用来源分类**：判断请求来自 agent 应用还是普通应用。这需要可信的应用/会话标签，
   单个 request 的消息结构无法完全决定。
2. **当前轮次行为分类**：判断当前请求是否处于工具调用、多轮继续或 agent loop 中。这需要
   `tool_calls`、`tool` 返回、会话历史、前后请求间隔等上下文，不能只看 system count。
3. **缓存策略分类**：判断是否值得保留 KV cache。这通常比“是不是 agent”更接近真正目标，
   应使用会话连续性、工具返回、后续请求概率和 gap 等运行时信号。

因此建议：

- 不再把 `n_system_messages` 作为 agent 的语义定义，只把它当作低成本模板信号。
- 在完整 GLM 语义审计完成前，不把 1 维规则作为生产真值判定器；2 维模型也只能视为当前
  数据分布下的候选模型。
- 优先增加可靠标签：应用 SDK/网关来源、明确的工具调用协议、会话是否有后续请求，以及
  agent trajectory 元数据。
- 对普通应用的 function calling 单独采样，否则“有工具”也会被错误当成 agent。
