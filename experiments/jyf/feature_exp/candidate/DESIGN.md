# 实验设计：session 独立、无 eviction 的 node-level reuse

## 目标

验证在理想资源环境中，radix node 的 session 内复用时间是否可预测，以及去掉全局 event/LRU 特征后，哪些输入仍然有效。

## 数据单位

- 每个 session 独立构造一棵 radix tree。
- 不同 session 不共享 node、hit、gap 或统计量。
- node 永不 eviction，因此没有 incarnation reset。
- message 是树上的 segment；样本是累计 prefix 对应的持久化 node demand。
- 同一个 node 的连续两次 demand 产生一个 reuse gap。
- session 最后一次 demand 是 right-censored。

当前输入数据没有真实 tokenizer，因此 node 长度先用规范化 message 表示长度近似；如果之后有 tokenizer，应替换为 token 数而不改实验协议。

## 四个对照模型

1. Old-10 absolute：原 16 维去除 6 个 event/LRU 特征后，保留 10 维，直接预测秒级 reuse time。
2. Old-10 relative：同一 10 维，但 seconds history 除以 session scale tau_session。
3. Candidate-32：当前候选 session/context/history 特征全部挂到 node demand 上。
4. Candidate-8：当前筛选出的 8 维，仍然挂到 node demand 上。

所有模型必须使用相同 session split、相同 node 样本和相同 censor-aware hazard loss。

## 旧 16 维的保留版本

    node_tokens
    path_tokens
    age_seconds
    idle_seconds
    hits
    gap_present
    recent_gap_seconds
    gap_ewma_seconds
    gap_std_seconds
    is_agent

删除：

    age_events
    idle_events
    recent_gap_events
    gap_ewma_events
    gap_std_events
    lru_frac

## 当前脚本

run_node_experiment.py 负责构造 node-level 数据集，输出：

- node_samples.npz
- node_dataset_meta.json

训练/消融脚本应读取该文件，在四个模型之间固定 split 和 label 后比较 IBS、AUC@多个时间 horizon、censor NLL，以及按 cold/warm node 分组的结果。

is_agent 当前输入中没有显式 workload metadata，因此暂时为常数 0；这只保留列兼容性，不能解释为真实 workload 特征。

