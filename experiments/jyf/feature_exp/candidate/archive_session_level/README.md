# Session-only candidate feature experiments

## 模型边界

对象是 `(session, logical prefix)`，不是物理 radix node。prefix 用 session 内 message 边界定义，历史记录它在该 session 请求中再次出现的规律；不读取 cache hit、eviction、node split、LRU、全局 event 计数、并发量或 workload 标签。模型不输入 tenant ID、model ID、agent 框架名或 prompt 内容 hash。

预测在当前请求到达时进行。所有 Context 来自当前已知请求，History 只用截至当前请求的历史；不读取当前 response。输出是 `Z = next_session_prefix_demand_gap / tau_session` 的固定维度 hazard。τ 取本 session 最近最多8个已完成请求 gap 的 median，并固定为本次预测的时间尺度。

**数据限制**：当前日志没有可靠 response 完成时间，也没有权威 session ID。实验按 tenant + first-user-message 分组推断 session，标签使用原始 request-start 间隔。它不依赖本次 serving replay，但历史秒数仍含日志产生时的服务延迟。因此这是 session-only 接口下的实测代理目标，不是对完全剥离 serving 延迟的理想标签的证明。

## 候选特征

32 个候选见 `feature_catalog.md`（由代码定义自动生成）。分组如下：

1. position：逻辑 prefix 在 session context 中的位置。
2. context：当前上下文、工具可用性与工具使用信息。
3. evolution：相邻请求的上下文增长、改写及工具声明变化。
4. session：本 session 的历史交互节奏。
5. prefix_history：本 session 对目标 prefix 的重复需求规律。

工具是否可用由 `tool_schema_count == 0` 表示，不重复加入 `has_tool`；没有用 serving tokenizer，内容长度统一按规范化 message 字符数计算。message 内容 hash 只用于身份与公共前缀判定，不作为模型特征。

排除确定性重复：`remaining_fraction=1-prefix_fraction`、`gap_trend=last-prev`、`session_gap_count=session_turn-1`。不加入物理 depth/children/leaf/age。固定预测时点 idle 恒为0，因此没有 idle 输入。相对时间缺失填 -1，真实0映射0，不靠多个重复 mask 区分。session_turn 与 prefix_reuse_count 提供历史支持量。

## 实验流程

- train/validation/test 按推断 session 分组，70/15/15，固定 hash 排序；模型特征标准化与常数筛选只用 train。
- 训练集 Spearman 特征相关矩阵；与 horizon=1/2/4 个 τ 内复用标签的秩相关，仅使用该 horizon 标签可判定的样本。
- 去掉训练集恒定或逐元素完全相同列；相关不等于无效，不用相关系数直接删除互补特征。
- full、逐组删除、逐特征删除，每组 seed=41/42/43，相同固定32维宽度，被消融列标准化后置零。
- 固定相对边界 `.125,.25,.5,1,2,4,8,16,64`，9个hazard加尾部概率，共10个桶；两层64隐藏单元，训练最大60 epoch、patience=6。
- censor-aware hazard likelihood；训练给每个session相同总权重，避免长context产生大量prefix样本主导拟合。
- 验证集的主指标为 relative 0–8 区间的 IPCW Integrated Brier；缺失/右删失不当作负例。
- 预定义筛选：单项删除导致验证 IBS 恶化超过1%的特征进入精简集合；精简集合再联合训练，验证结果必须优于 full 才作为最终选择。未达到1%不等于证明无信息，可能与其他特征可替代。
- 最后对 full、精简集合、单组模型报告测试指标。不得根据测试结果重新挑特征。

## 复现

```bash
cd /share/dai-sys/zhoulongsheng/agentkv/experiments/jyf/feature_exp/candidate
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /share/dai-sys/apps/anaconda3/envs/agentkv_zls/bin/python run_candidate.py \
 --data /share/dai-sys/zhoulongsheng/agentkv/third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl \
 --out runs/20260916_session_v2 --device cuda:0 --epochs 60
```

`run_candidate.py` 定义全部数据处理和筛选流程。`runs/20260916_session_v2` 为正式结果目录；`v1` 是删除重复计数候选前中止的数据准备，不用于结果。

运行输出：`samples.npz` 是处理后的全部样本；`dataset_meta.json` 是数据口径、分组和限制；`correlations.json` 是相关分析；`screening.json` 是验证集全部消融；`results.json` 是冻结选择及测试指标；`*.pt` 为最终候选与单组模型；`*predictions.npz` 保存验证/测试预测，支持独立复核。
