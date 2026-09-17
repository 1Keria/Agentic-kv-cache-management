# Session-only 候选特征清单

候选共32维。长度基于规范化message内容字符数，不依赖服务模型tokenizer。以下所有prefix、turn、gap都限定在同一个session内。预测时点为请求到达。

|特征|组|定义|处理|
|---|---|---|---|
|`prefix_fraction`|position|目标逻辑 prefix 的内容长度 / 当前 context 内容长度|identity|
|`segment_fraction`|position|prefix 最后一个 message 的内容长度 / 当前 context 内容长度|identity|
|`creation_turn_fraction`|position|prefix 首次出现的 turn index / 当前 turn index（从1计）|identity|
|`endpoint_is_tool`|position|prefix 最后一个 message 是否为 tool|identity|
|`endpoint_is_assistant`|position|prefix 最后一个 message 是否为 assistant|identity|
|`context_chars`|context|当前 message context 的规范化字符长度，独立于 serving tokenizer|log1p|
|`tool_schema_fraction`|context|tool schema 字符长度 / (schema + message context 字符长度)|identity|
|`tool_schema_count`|context|当前请求声明的可用 tool 数量；0同时表示无tool|log1p|
|`tool_content_fraction`|context|当前 context 中 tool message 内容长度比例|identity|
|`assistant_content_fraction`|context|当前 context 中 assistant message 内容长度比例|identity|
|`tool_call_density`|context|当前 context 中 tool call 数 / assistant message 数|log1p|
|`last_message_is_tool`|context|当前已知 context 最后一个 message 是否为 tool|identity|
|`last_message_is_user`|context|当前已知 context 最后一个 message 是否为 user|identity|
|`last_assistant_call_count`|context|当前 context 最近一个 assistant message 中 tool call 数|log1p|
|`context_growth_fraction`|evolution|当前与上一请求 context 长度之差 / 上一 context 长度，可负|signed_log1p|
|`rewritten_fraction`|evolution|上一请求 context 中未保留为当前公共前缀的内容比例|identity|
|`new_tool_messages`|evolution|当前相对上一请求新增/改写后缀中的 tool message 数|log1p|
|`new_user_messages`|evolution|当前相对上一请求新增/改写后缀中的 user message 数|log1p|
|`tool_schema_changed`|evolution|当前与上一请求的工具声明是否不同|identity|
|`session_turn`|session|session 已观测请求数，按时间去重；非全局事件数|log1p|
|`session_gap_last_rel`|session|session 最近请求间隔 / 当前 session τ|relative|
|`session_gap_lag2_rel`|session|session 倒数第二个请求间隔 / 当前 session τ|relative|
|`session_gap_ewma_rel`|session|session 最近最多8个 gap 的 EWMA / τ，alpha=.6|relative|
|`session_gap_std_rel`|session|session 最近最多8个 gap 的标准差 / τ|relative|
|`prefix_gap_last_rel`|prefix_history|本session对目标prefix最近需求间隔 / τ|relative|
|`prefix_gap_lag2_rel`|prefix_history|本session对目标prefix倒数第二个需求间隔 / τ|relative|
|`prefix_gap_ewma_rel`|prefix_history|本session对prefix最近最多8个 gap 的 EWMA / τ|relative|
|`prefix_gap_std_rel`|prefix_history|本session对prefix最近最多8个 gap 的标准差 / τ|relative|
|`prefix_reuse_rate8`|prefix_history|prefix存在期间最近最多8个session请求中包含该prefix的比例|identity|
|`prefix_turn_gap_last`|prefix_history|最近两次包含该prefix的session请求相隔的turn数|log1p|
|`prefix_age_rel`|prefix_history|该逻辑prefix首次在session出现至今的时间 / τ|relative|
|`prefix_reuse_count`|prefix_history|本session对该prefix已经完成的再次需求次数，独立于缓存hit|log1p|

relative字段先除以当前τ再log1p；无历史填-1，真实0填0。其他log1p字段非负，context增长使用signed log1p。随后用训练集统计标准化。

这里刻意没有has_tool（可从schema_count得到）、remaining_fraction、gap_trend、session_gap_count、多套阈值mask或物理radix结构。不同gap统计描述最近值、较早值、加权水平和波动，不存在人为添加的确定性公式重复；数据上的冗余由相关性与消融继续检查。
