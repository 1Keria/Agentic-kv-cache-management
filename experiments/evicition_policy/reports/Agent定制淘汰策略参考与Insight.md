# Agent 定制淘汰策略：中间过程证据与设计 Insight

日期：2026-09-28。该报告由成功 suite 的逐请求日志和全量候选画像自动生成，服务于下一阶段机制设计。

## 1. 结论边界

当前证据能够说明请求内容结构、相邻轮延续、实际命中差异和聚合缓存压力；不能精确说明某次淘汰是否存在更优合法 victim。文中的 `previous_input_lcp_shortfall_proxy_tokens` 只是内容级参照缺口，不是严格的额外重算量。

## 2. 核心观测

- 全量候选包含 108 个会话、5,348 个请求。输入长度中位数为 36,091.5 token，相邻输入 LCP 后新增内容中位数为 708.5 token。
- 共识别 35,040 个完整 256-token 上下文前缀页，仅 12 个跨 session 引用。除公共模板前缀外，主要复用机会来自同一 session 的私有长链。
- SLRU 相对 LRU 净多命中 233,472 token，但只在 117 个请求上更好、107 个请求上更差，另有 982 个请求完全相同。策略差异集中在少数竞争时刻。
- SLRU 正向差异合计 1,893,376 token、负向差异合计 1,659,904 token，净收益只保留了正向差异的 12.33%。现象是强烈抵消，而不是普遍改善。
- LFU 相对 LRU 净变化为 -942,592 token；更好/更差请求数分别为 107/157。
- 非首轮转换中严格 append 为 1,127 次，占 95.03%；主要结构确实是同 session 长链续接。
- 三策略都存在至少 8K 相邻前缀缺口代理的请求有 356 个，而三策略最大命中差至少 8K 的请求只有 108 个。仅改变排序可能无法覆盖大部分缺口。
- 长链目标组（严格 append、续接深度≥4、参照前缀≥32K、LRU 缺口代理≥8K）有 186 个请求，缺口代理合计 9,384,960 token。
- 三种策略的本地生成完整接入下一轮历史输入次数分别为 LRU 2/1,186、LFU 2/1,186、SLRU 1/1,186。因此当前数据不能直接验证新生成尾部的真实闭环复用价值。



## 3. 对定制策略的启发

1. **优先研究链级续接证据，而不是跨 session 语义共享。** 现有共享画像显示跨 session 完整前缀页极少；最小机制应先针对同一实际 token 链的多轮续接。
2. **把新增尾部与已有长历史分开。** 长历史已经证明可复用，不代表刚产生的尾部也有相同价值。可检验的最小机制是有限的续接资格迁移：只把父链的一部分历史信用授予新尾部，并设置上限或衰减。
3. **用竞争量补充绝对时间。** 工具等待秒数有长尾，但相同等待期间可能没有竞争，也可能插入大量新页。未来排序信号应记录自上次需求以来的新插入逻辑页/token、不同前缀访问数和池压力，而不是仅按 wall time。
4. **收益需要按释放成本归一化。** 大节点保留价值高时也可能占用更多页。候选比较至少同时记录未来可复用 token、当前节点 token、路径 token 和达到相同释放预算时替代 victim 的损失。
5. **先解释差异请求，再扩大策略矩阵。** `candidate_cases.csv` 已按策略命中差异排序；应先为这些请求补完整 KV 事件和合法 frontier，验证 SLRU 的收益是否来自预期的续接链保护。

## 4. 日志深挖后的修正

进一步结果见 [Agent 定制淘汰策略日志深挖](Agent定制淘汰策略日志深挖.md)，机器可读快照为 `agent_policy_deep_dive_20260928.json`。新分析补充了请求提交/完成排名、上一轮完成时的在途请求、think gap 内实际 stream token，以及高/低前缀可用状态转移。

最需要修正的是：LRU、LFU、SLRU 的闭环运行并不处于相同全局请求顺序。SLRU 相对 LRU 有 1,092/1,206 个请求的提交排名发生变化，提交时间绝对偏移中位数为 23.682 秒。因此逐请求命中差不能直接解释为同一缓存状态上的 victim 反事实。

55 个 LRU/SLRU 双向 cliff 中，有 41 个在两种策略的 think gap 内都没有新请求提交，但上一轮完成时都仍有其他请求运行；20 个 cliff 在前一轮的两种策略下都处于高前缀可用状态。这进一步说明父链热度、短等待和简单的新提交计数都不能单独决定保护。

三策略共同存在至少 8K 相邻前缀缺口代理的 356 个请求中，261 个在三种策略的 think gap 内都没有新请求提交，但三边都仍有在途请求。这个群体应优先检查活跃占用、准入、节点暴露和回收粒度；当前代理无法判断排序、回收粒度或 SWA/Full 哪一项占主导。

## 4.1 前缀需求统计对“二次机会”的修正

进一步的内容级统计见 [Agent 前缀重复需求与候选可观测性统计](Agent前缀重复需求与候选可观测性统计.md)。在冻结的 20 个会话、1,206 个请求中，共有 7,448 个不同的完整 256-token 输入前缀页；7,094 个页在观察窗内被至少两个请求需要，占 95.25%。严格追加产生且后面仍有下一轮的请求带来 6,110 个首次出现页，其中 5,641 个在下一轮再次出现，占 92.32%。这支持你的直觉：历史输入页普遍会重复，按“累计用过两次”做长期保护可能很快饱和。

但无容量输入历史树的最终末端页只有 52 个，其中 50 个只有一次观察需求，重复需求主要集中在内部历史页。这个树是内容结构参照，不是实际 radix 节点或合法候选；当前日志没有记录逐次候选、删叶后父节点暴露或物理空间，不能从中计算真实候选三类的比例。

另外，实测生成输出内容在下一轮历史中的完整页匹配非常少：LRU 5 个页、288 个输出 token；LFU 也是 5 个页、288 个输出 token；SLRU 为 3 个页、173 个输出 token。由于当前回放使用冻结历史输入、生成分支几乎不接入下一轮，这些数字只能说明本次闭环观测不足，不能证明 Agent 生成尾部普遍一次性。

因此“有限二次机会”应降级为通用基线或独立消融，暂不作为 Agent 主机制。下一步应采集真实候选 frontier，重点看：新尾部之间是否都没有近期 demand、删除子节点后祖先多久暴露、以及按最近一次真实 demand 而非累计生命周期次数能否区分后续单位空间收益。

建议第一版只实现一个可关闭的 `bounded continuation credit`：当同一可确认 token 前缀链已发生多次续接时，新暴露尾部获得有限信用；信用不跨历史改写无条件继承，并随竞争量或时间衰减。它必须与原生 SLRU 对照，并满足相同释放 token 预算。

在实现前需要通过事件诊断回答：

- 发生大额命中差异时，完整合法候选有哪些，锁定和父节点暴露如何变化；
- 被保留尾部之后是否真实再次需要，以及为保留它而替换的其他候选损失是多少；
- 信用来自同一链的历史续接，还是公共祖先/模板命中；
- 收益是否集中于某些等待竞争量、上下文增长或轮次区间。



## 5. 首批典型案例


| 排名  | 类型/标签                                                                             | task                    | turn | prompt  | LCP     | 有效等待(s) | SLRU-LRU命中差 | LFU-LRU命中差 |
| --- | --------------------------------------------------------------------------------- | ----------------------- | ---- | ------- | ------- | ------- | ----------- | ---------- |
| 1   | slru_gain / slru_large_win;slru_policy_cliff_win;long_chain_unavailable_lru_proxy | drone-planning-control  | 63   | 126,979 | 121,142 | 62.9023 | 121,088     | 3,072      |
| 2   | slru_loss / lru_large_win;lru_policy_cliff_win                                    | drone-planning-control  | 60   | 119,901 | 117,546 | 2.8424  | -117,504    | -256       |
| 3   | lfu_loss_only / lfu_under_lru_and_slru                                            | drone-planning-control  | 57   | 112,625 | 112,465 | 0.047   | 0           | -109,312   |
| 4   | lfu_loss_only / lfu_under_lru_and_slru                                            | fix-build-agentops      | 109  | 88,899  | 88,527  | 13.6786 | 0           | -88,320    |
| 5   | slru_loss / lru_large_win;lru_policy_cliff_win                                    | shock-analysis-demand   | 101  | 85,416  | 83,860  | 0.2145  | -83,712     | 0          |
| 6   | lfu_loss_only / lfu_under_lru_and_slru                                            | fix-build-agentops      | 100  | 79,845  | 79,625  | 9.0805  | 0           | -79,616    |
| 7   | slru_loss / lru_large_win;lru_policy_cliff_win                                    | shock-analysis-demand   | 68   | 79,843  | 79,043  | 0.195   | -75,776     | -75,776    |
| 8   | lfu_loss_only / lfu_under_lru_and_slru                                            | fix-build-agentops      | 97   | 78,666  | 77,030  | 0.8365  | 0           | -73,728    |
| 9   | lfu_loss_only / lfu_under_lru_and_slru                                            | shock-analysis-demand   | 65   | 75,281  | 75,096  | 1.1124  | 0           | -71,936    |
| 10  | slru_loss / lru_large_win;lru_policy_cliff_win                                    | drone-planning-control  | 42   | 72,213  | 70,437  | 0.0409  | -70,400     | 0          |
| 11  | lfu_loss_only / lfu_under_lru_and_slru                                            | syzkaller-ppdev-syzlang | 73   | 70,612  | 69,973  | 3.875   | 0           | -69,888    |
| 12  | slru_gain / slru_large_win;slru_policy_cliff_win;long_chain_unavailable_lru_proxy | shock-analysis-demand   | 58   | 72,463  | 72,068  | 0.0371  | 68,864      | 68,864     |
| 13  | lfu_loss_only / lfu_under_lru_and_slru                                            | fix-build-agentops      | 91   | 72,485  | 72,065  | 0.0966  | 0           | -68,864    |
| 14  | slru_gain / slru_large_win;slru_policy_cliff_win;long_chain_unavailable_lru_proxy | shock-analysis-demand   | 57   | 72,068  | 71,795  | 3.0996  | 68,608      | 68,608     |
| 15  | slru_loss / lru_large_win;lru_policy_cliff_win                                    | syzkaller-ppdev-syzlang | 67   | 68,431  | 68,054  | 0.0447  | -67,840     | 0          |


这些案例只是后续采集 KV 时间线的优先队列。没有完整 candidate/victim/lock/split 事件前，不将其标记为错误淘汰。

## 6. 配套文件

- `summary.json`：口径、总体统计、策略差异和解释限制。
- `reports/agent_policy_insights_20260928.json`：纳入仓库的紧凑机器可读快照。
- `reports/Agent定制淘汰策略日志深挖.md`：闭环交错、在途竞争、状态转移和正反 cliff 的进一步分析。
- `reports/agent_policy_deep_dive_20260928.json`：深挖结论的机器可读快照。
- `request_policy_deltas.csv`：1,206 个请求的对齐明细。
- `behavior_bins.csv`：按等待、增长、轮次和 LCP 长度分桶的命中差异与代理缺口。
- `session_summary.csv`：按会话汇总的策略差异与提交竞争代理。
- `candidate_cases.csv`：所有发生策略命中差异的请求，按最大绝对差异排序。
- `manifest.json`：输入和输出文件哈希。



## 7. 后续事件诊断的优先窗口

下面的窗口不是已确认的错误淘汰，而是最值得补充完整 candidate/victim 时间线的请求段：

1. **同一会话内的 SLRU 正反翻转**：`drone-planning-control`，session `openhands_eb93634abc30eb8a8ec57b65cb8e09b977148deee8b970538fd4caeeadef880c`，turn 56–64。turn 60 中 SLRU 比 LRU 少命中 117,504 token，turn 63 又比 LRU 多命中 121,088 token。该窗口最适合检查节点命中计数、父节点暴露、候选集合和排序变化。
2. **SLRU 连续保护窗口**：`drone-planning-control`，session `openhands_0bb81a9cf635697f01fa3087a1d7d0bd204da9724c5b225b727ed68c84a5e1cc`，turn 36–43。该会话 SLRU 相对 LRU 净多命中 305,664 token，是当前最强的会话级正例。
3. **续接资格迁移的反例窗口**：`syzkaller-ppdev-syzlang`，session `openhands_0ca57752127116f752c0aef0507a32422771d909683b1b911f87808524c87905`，turn 54–69。三种策略多次交替保住或丢失同一长链，可检验有限信用在什么条件下有效或有害。
4. **相对干净的 LFU 失败**：`fix-build-agentops`，session `openhands_d18eb09e77f3e071ba866ec9cea71215732c25fde65ce6471f8c1505213602ee`，turn 100 和 109。LRU/SLRU 分别保留约 80K/88K 前缀，LFU 为 0，适合检查历史频次为何没有保护当前链。
5. **策略共同失败的负控制**：`shock-analysis-supply`，turn 54–62。三种策略长期仅命中 0/3072；3072 可能是公共模板前缀，不能解释为私有长链仍然驻留。该窗口用于检查容量、准入、回收粒度或 SWA 耦合是否主导损失。

每个窗口至少需要记录：稳定前缀身份、pool、完整合法候选、锁/ref 状态、节点命中与最近访问、策略分数与排序、实际 victim、释放 token/byte、父节点暴露、后续 demand，以及相同释放预算下替代候选的未来损失。

## 8. 可复用的既有实现

- `../../../scripts/python/analyze_kv_eviction_regret.py` 已实现基于 `resident / ever_stored / last_eviction` 的 cold/eviction miss 分类和 reuse-distance 分析，可迁移其稳定前缀和事件关联框架。
- `../../jyf/nn_exp/useless/async_exp/run_experiment.py` 已实现 frozen frontier 上的单 victim shadow 排序，可复用候选结果表和右删失处理，但不能直接当 stateful cache replay。
- `../../jyf/evict_position/serving_patch.py` 已能枚举完整合法 frontier、选择 victim 并在 TP rank 间广播，可复用采集位置和一致性检查；旧 MLP Hazard 分数不作为当前机制结论。



## 9. 推荐实施顺序

1. 按 `configs/agent_policy_diagnostics_schema.json` 实现只读 KV 事件采集，先不改变淘汰决策。
2. 为上述五类窗口验证事件覆盖、稳定前缀身份、TP 去重、Full/SWA 区分和 candidate frontier 完整性。
3. 实现真正的 `h_history / h_policy / extra_recompute`，把当前相邻 LCP 缺口代理升级为事件支持的诊断量。
4. 生成损失分桶和驱逐时间线，判断策略敏感缺口与三策略共同缺口各占多少。
5. 只有在事件证据支持后，再实现可关闭的有界续接信用，并与原生 LRU/SLRU 在相同释放预算下比较。

当前总判断是：**现有证据支持将机制候选收敛到“有界的链续接信用/资格迁移”，但共同缺口和双向 cliff 同时存在，不能把长会话或高续接次数无条件设为保护对象。**
