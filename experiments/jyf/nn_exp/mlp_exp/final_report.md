# 独立 Prefix Reuse MLP 实验结论

## 结论

当前数据上建议采用 **Initial MLP + Conditional Shift**，暂不实现周期性 Re-predict。

- Static 明显最差：等待 20 秒后，K=10 的 token-weighted Brier@20 为 0.19162；Shift 降至 0.07462。
- Re-predict 在短等待时有小幅收益，但不稳定：
  - age=5s、K=10：Shift 0.21099，Re-predict 0.20271，后者相对改善 3.92%；
  - age=20s、K=10：Shift 0.07462，Re-predict 0.07170，相对改善 3.92%；
  - age=20s、K=20：Shift 0.07169，Re-predict 0.07267，Shift 反而更好 1.34%。
- 长间隔模式下 Shift 更稳定。age=600s、future=3600s：
  - K=10：Shift 0.00472，Re-predict 0.00533；
  - K=20：Shift 0.00463，Re-predict 0.00515。
- 三个种子的方向基本一致。Re-predict 的短期收益未达到预先建议的 5% 门槛，而且需要每个检查点重新执行网络。

因此，时间流逝的信息非常重要，但当前结果支持通过缓存初始 hazard curve 并做条件化来利用这条信息；没有充分证据证明需要重新运行 MLP。

## 分桶建议

- 如果控制器只关注未来 5/20/60 秒，K=5 已足够，且最简单。
- 如果还需要区分小时级长尾，建议 K=10，边界为：
  `[2, 5, 10, 20, 60, 180, 600, 1800, 7200, +inf)`。
- K=20 没有带来稳定收益：短期部分更容易过拟合，长时间尺度只有很小改善。

综合考虑，推荐 **K=10 + Shift** 作为下一阶段默认配置；同时保留 K=5 作为低开销消融。

## 数据与实验范围

- 原始请求：16,559 条；坏行：1 条。
- 逻辑 message-boundary prefix：210,719 个。
- 样本：373,228 条。
- 至少已有一个历史 reuse gap 的有效样本：162,509 条。
- 其中观测到下一次 reuse 的样本：83,223 条。
- train/validation/test 按首个 user anchor hash 分组，避免同一 trajectory 跨集合。
- 每种分桶训练 3 个随机种子；每个种子包含 Initial MLP 和 age-aware Landmark MLP。
- 时间标签为 request-start 到 next-request-start，不是严格 unlock-to-hit；原始日志没有可靠的请求结束时间。
- 本实验不使用 radix tree、不依赖现有 AgentKV/SGLang MLP，也没有运行在线服务或真实 KV eviction replay。

## 数据形态

已观测 reuse gap：

- P10：2.55s
- P25：3.49s
- P50：5.98s
- P75：11.43s
- P90：20.00s
- P95：48.03s
- P99：约 7200s

分布明显双峰。测试集中超过 60 秒的 295 个已观测事件，最短约 3551 秒，中位约 10805 秒。因此 age=60–600 秒时的短期 Brier 接近零，本身不具有策略区分力；为此额外评估了 600/1800 秒 age 和 600–7200 秒 future horizon。

## 主要结果（3 seeds 均值）

| Buckets | Age | Strategy | token-Brier@20 | token-NLL |
|---|---:|---|---:|---:|
| K=5 | 5s | Static | 0.21504 | 0.97422 |
| K=5 | 5s | Shift | 0.20442 | 0.93556 |
| K=5 | 5s | Re-predict | 0.20349 | 0.91171 |
| K=5 | 20s | Static | 0.18746 | 0.68026 |
| K=5 | 20s | Shift | 0.07436 | 0.38642 |
| K=5 | 20s | Re-predict | 0.07171 | 0.33580 |
| K=10 | 5s | Static | 0.22160 | 1.45460 |
| K=10 | 5s | Shift | 0.21099 | 1.17708 |
| K=10 | 5s | Re-predict | 0.20271 | 1.18277 |
| K=10 | 20s | Static | 0.19162 | 0.82103 |
| K=10 | 20s | Shift | 0.07462 | 0.47367 |
| K=10 | 20s | Re-predict | 0.07170 | 0.42477 |
| K=20 | 5s | Static | 0.22336 | 1.85789 |
| K=20 | 5s | Shift | 0.21370 | 1.38897 |
| K=20 | 5s | Re-predict | 0.20631 | 1.40991 |
| K=20 | 20s | Static | 0.19085 | 0.89944 |
| K=20 | 20s | Shift | **0.07169** | **0.46516** |
| K=20 | 20s | Re-predict | 0.07267 | 0.48295 |

不同 K 的离散 NLL 不能直接横向比较，因为类别粒度不同；Brier 可以在相同预测 horizon 上比较。

## 下一步

如果进入系统实验，优先实现 K=10 Initial MLP 的一次性推理和 hazard curve 条件右移。只有当真实 eviction replay 显示 Re-predict 能稳定减少至少 5% recomputed tokens，才值得增加周期性推理。
