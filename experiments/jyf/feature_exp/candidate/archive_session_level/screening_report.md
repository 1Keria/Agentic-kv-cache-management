# Session-only 特征探索结果

本实验严格将输入限定为session上下文和该session的逻辑prefix历史。没有复用之前的cache frontier样本或serving特征。完整32维清单见 `feature_catalog.md`。

## 标签及数据边界

- 对象 `(推断session, logical message-boundary prefix)`；当前请求中出现的prefix，在后续同session请求中再次出现即为需求，无论缓存是否命中。
- 标签 `Z=(next_request_start-current_request_start)/tau_session`，τ为当前已知的最近最多8个session请求gap的median。尚未观测复用的prefix按日志全局结束时间右删失。
- session以 tenant + 首个user message内容推断，未获得权威session ID；相同首个user消息可能合并不同trajectory，属于数据限制。
- 只有request-start，没有response完成时间，因此原始gap含历史服务延迟；模型接口与serving状态无关，但数据不能证明理想时间标签已剥离服务延迟。
- 16,559请求、373,228原始样本；排除164,865个无session历史τ的样本后，正式使用208,363样本、3,448个session；训练/验证/测试session=2,415/526/507。
- τ完全来自当前session已有历史，未使用训练全局默认值；session首请求没有物理时间尺度，当前实验不替它制造相对时间标签。prefix首次出现但session已有历史的样本仍保留。
- 固定9个relative有限边界 `.125,.25,.5,1,2,4,8,16,64`；输出9个hazard加尾部概率。没有用测试数据选择bucket或特征。
- 相同32维输入宽度、两层64unit，消融列标准化后置零；所有组3 seeds；验证IPCW IBS(0–8τ)用于筛选。
- 所有报表阈值@1/@2/@4都指当前session的1/2/4个τ，不是秒。主指标IBS越低越好。

## 相关性

训练集抽取最多60,000个样本计算Spearman。没有训练集恒定列或完全相同列。下表列出绝对相关系数≥0.8的候选对；相关性只辅助解释，删除依据为消融。

|特征A|特征B|Spearman|
|---|---|---:|
|last_message_is_tool|last_message_is_user|-1.0000|
|last_message_is_user|new_user_messages|0.9760|
|last_message_is_tool|new_user_messages|-0.9760|
|prefix_age_rel|prefix_reuse_count|0.9755|
|prefix_gap_std_rel|prefix_reuse_count|0.9443|
|prefix_gap_std_rel|prefix_age_rel|0.9372|
|creation_turn_fraction|prefix_reuse_count|-0.8985|
|creation_turn_fraction|prefix_age_rel|-0.8857|
|prefix_gap_last_rel|prefix_gap_ewma_rel|0.8726|
|session_turn|session_gap_std_rel|0.8681|
|creation_turn_fraction|prefix_gap_std_rel|-0.8529|
|prefix_gap_lag2_rel|prefix_gap_std_rel|0.8496|
|prefix_gap_lag2_rel|prefix_reuse_count|0.8471|
|prefix_gap_lag2_rel|prefix_age_rel|0.8305|

与未来复用的阈值关联见 `correlations.json/target_associations`。该分析在每个阈值只纳入可判定标签，存在删失选择限制；没有把只观察到复用的duration相关系数当作主筛选证据。

## 组级消融（验证集）

|方案|IBS|相对full变化|
|---|---:|---:|
|full|0.185427|+0.00%|
|without_group_context|0.191884|+3.48%|
|without_group_evolution|0.179899|-2.98%|
|without_group_position|0.189397|+2.14%|
|without_group_prefix_history|0.215055|+15.98%|
|without_group_session|0.166447|-10.24%|

## 单项消融（验证集）

正变化表示删掉后变差。预设保留门槛为删除后IBS恶化超过1%；这是实用筛选门槛，不是显著性检验。

|删除特征|IBS|相对full变化|进入精简集合|
|---|---:|---:|---|
|prefix_fraction|0.188127|+1.46%|是|
|segment_fraction|0.184366|-0.57%|否|
|creation_turn_fraction|0.194166|+4.71%|是|
|endpoint_is_tool|0.196399|+5.92%|是|
|endpoint_is_assistant|0.190550|+2.76%|是|
|context_chars|0.188261|+1.53%|是|
|tool_schema_fraction|0.186092|+0.36%|否|
|tool_schema_count|0.198091|+6.83%|是|
|tool_content_fraction|0.198828|+7.23%|是|
|assistant_content_fraction|0.184219|-0.65%|否|
|tool_call_density|0.194356|+4.82%|是|
|last_message_is_tool|0.196696|+6.08%|是|
|last_message_is_user|0.194555|+4.92%|是|
|last_assistant_call_count|0.188358|+1.58%|是|
|context_growth_fraction|0.190458|+2.71%|是|
|rewritten_fraction|0.178352|-3.82%|否|
|new_tool_messages|0.190071|+2.50%|是|
|new_user_messages|0.187688|+1.22%|是|
|tool_schema_changed|0.188589|+1.71%|是|
|session_turn|0.175186|-5.52%|否|
|session_gap_last_rel|0.191509|+3.28%|是|
|session_gap_lag2_rel|0.182017|-1.84%|否|
|session_gap_ewma_rel|0.189317|+2.10%|是|
|session_gap_std_rel|0.183984|-0.78%|否|
|prefix_gap_last_rel|0.201523|+8.68%|是|
|prefix_gap_lag2_rel|0.186262|+0.45%|否|
|prefix_gap_ewma_rel|0.199975|+7.85%|是|
|prefix_gap_std_rel|0.188194|+1.49%|是|
|prefix_reuse_rate8|0.188655|+1.74%|是|
|prefix_turn_gap_last|0.206541|+11.39%|是|
|prefix_age_rel|0.189320|+2.10%|是|
|prefix_reuse_count|0.188779|+1.81%|是|

## 冻结候选与测试结果

验证集选定方案：**selected**。单项门槛得到的精简集为：

- `prefix_fraction`：目标逻辑 prefix 的内容长度 / 当前 context 内容长度
- `creation_turn_fraction`：prefix 首次出现的 turn index / 当前 turn index（从1计）
- `endpoint_is_tool`：prefix 最后一个 message 是否为 tool
- `endpoint_is_assistant`：prefix 最后一个 message 是否为 assistant
- `context_chars`：当前 message context 的规范化字符长度，独立于 serving tokenizer
- `tool_schema_count`：当前请求声明的可用 tool 数量；0同时表示无tool
- `tool_content_fraction`：当前 context 中 tool message 内容长度比例
- `tool_call_density`：当前 context 中 tool call 数 / assistant message 数
- `last_message_is_tool`：当前已知 context 最后一个 message 是否为 tool
- `last_message_is_user`：当前已知 context 最后一个 message 是否为 user
- `last_assistant_call_count`：当前 context 最近一个 assistant message 中 tool call 数
- `context_growth_fraction`：当前与上一请求 context 长度之差 / 上一 context 长度，可负
- `new_tool_messages`：当前相对上一请求新增/改写后缀中的 tool message 数
- `new_user_messages`：当前相对上一请求新增/改写后缀中的 user message 数
- `tool_schema_changed`：当前与上一请求的工具声明是否不同
- `session_gap_last_rel`：session 最近请求间隔 / 当前 session τ
- `session_gap_ewma_rel`：session 最近最多8个 gap 的 EWMA / τ，alpha=.6
- `prefix_gap_last_rel`：本session对目标prefix最近需求间隔 / τ
- `prefix_gap_ewma_rel`：本session对prefix最近最多8个 gap 的 EWMA / τ
- `prefix_gap_std_rel`：本session对prefix最近最多8个 gap 的标准差 / τ
- `prefix_reuse_rate8`：prefix存在期间最近最多8个session请求中包含该prefix的比例
- `prefix_turn_gap_last`：最近两次包含该prefix的session请求相隔的turn数
- `prefix_age_rel`：该逻辑prefix首次在session出现至今的时间 / τ
- `prefix_reuse_count`：本session对该prefix已经完成的再次需求次数，独立于缓存hit

|模型|维数|验证IBS|测试IBS|测试AUC@1/2/4τ|测试Brier@1/2/4τ|
|---|---:|---:|---:|---|---|
|full|32|0.185427|0.239721|0.5862 / 0.6043 / 0.6122|0.2019 / 0.2553 / 0.2606|
|selected|24|0.161792|0.230732|0.5767 / 0.6041 / 0.6156|0.1990 / 0.2480 / 0.2512|
|only_group_context|9|0.183265|0.243008|0.5693 / 0.5944 / 0.6118|0.1933 / 0.2653 / 0.2677|
|only_group_evolution|5|0.177675|0.251019|0.5685 / 0.5578 / 0.5501|0.1918 / 0.2739 / 0.2807|
|only_group_position|5|0.174234|0.249123|0.5328 / 0.5410 / 0.5459|0.1937 / 0.2730 / 0.2771|
|only_group_prefix_history|8|0.171706|0.261140|0.5192 / 0.5150 / 0.5224|0.2345 / 0.2701 / 0.2807|
|only_group_session|5|0.180318|0.293618|0.5337 / 0.5478 / 0.5468|0.2844 / 0.2929 / 0.3085|

精简集−full 的测试 IBS 差值为 -0.008989，按session重采样95% CI [-0.015469, -0.002576]；session等权平均差值 +0.006569。负数更好。

## 如何使用结论

- 选择依据是验证集，不因测试指标回头调整。单组模型仅用于解释信息来源，不额外参与这轮预定义full/selected选择。
- 一次联合删除可能移除相互替代的信号，故必须检查selected整体结果；若验证不优于full，则保留full，不能强行宣布精简成功。
- 本轮是一个原始日志workload、一个session split；没有验证跨agent/workload泛化。不能将相关性、消融小差异表述成普遍因果规律。
- 字符长度输入虽不依赖serving tokenizer，仍会随任务内容变化；接口不含workload身份不等于跨workload精度已经成立。
- 按推断session隔离优于随机prefix曝光切分，但仍需真实session ID及response完成时间才能验证完全理想的session行为目标。
