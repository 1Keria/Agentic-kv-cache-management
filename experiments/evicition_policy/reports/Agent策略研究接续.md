# 纯 Agent KV 策略研究接续

更新日期：2026-10-09。仅涵盖 Agent 请求缓存策略论文研究。

本轮状态：已完成。8 个接受条件共 9,648 请求，两份分析审计通过；新增策略拆分为零。47 项基础/检查点检查和新增 4 项检查通过。本轮实验与后处理进程均已结束。

最新结论：保留按已到达输入工作集预留 Full 空间的版本作为下一阶段候选。单独浅检查点只在半容量净提高 0.7213 个百分点；新增祖先降级没有带来净命中增量。工作空间版本半容量/四分之一容量/恢复命中率为 41.2471% / 7.1944% / 81.1870%，相对 v2 为 +3.2097 / +7.0045 / +17.7582 个百分点；全程 44.1648%，比 v2 提高 9.1102 个百分点。恒定容量各新变体均为 36.5831%，与 v2 相同。

注意退化分布：变容量相对 v2，10 个会话净改善、6 个净退化、4 个相同；半容量有 52 请求改善、61 请求退化。候选通过阶段净收益门槛，不代表所有会话受益。

## 接续约束

- 始终使用简体中文，先给结论；不主动 commit/push。
- 新增代码、配置、数据、日志、测试与报告只放在 `experiments/evicition_policy/`。
- 不覆盖项目 `Engine/sglang`、已有环境和历史结果；只操作本实验拥有的进程。
- 研究范围已从原生策略扩展到有限保护机制。不要重新启用身份分类器、业务分区或旧 Exposure Barrier。
- 在下一节点先读本文件、实验 README 和最新验证报告，再继续已有问题；不用重新跑已完成验证。

## 已建立的证据链

1. 原生 LRU/SLRU 顺序互换 GPU 复验没有稳定优劣，保留 LRU 主基线。
2. 只读诊断发现 Full/SWA 联合复用缺口，提出统一依赖保护。
3. 有限完整输入边界保护 v1 已完成五轮 GPU 对照，平均命中率 65.4876% → 75.1989%，但只验证一个固定压力点。
4. 加入真实硬预算执行层后，v1 缩容阶段退化；全程增益主要集中在恢复阶段。
5. 有限准入保留 v2 在半容量有效，四分之一容量仍约 0.19%，恢复阶段落后 v1。
6. 本轮验证真实浅检查点、驻留祖先降级，以及按已到达输入工作集预留 Full 空间。首轮因新增窗口尾拆分不满足结构审计，结果保留后重跑只读边界版本。

## 最新结果入口

- [v2 报告](有限准入保留_v2验证_20261009.md)
- [v3 最终报告](浅检查点与工作空间预留_v3验证_20261009.md)、[紧凑机器结果](浅检查点与工作空间预留_v3验证_20261009.json)
- v3 无拆分结果：`results/checkpoint_frontier/20261009_v3_native/`
- 工作空间无拆分结果：`results/checkpoint_frontier/20261009_workspace_native/`
- [v3 分析](../results/analysis/checkpoint_frontier_native_20261009/summary.json)
- [工作空间分析](../results/analysis/workspace_frontier_native_20261009/summary.json)
- [比较图](figures/checkpoint_frontier_20261009/native_checkpoint_comparison.png)（同目录有 SVG/PDF）
- 最终交付哈希清单：`results/checkpoint_frontier/20261009_delivery_audit/manifest.json`
- 本轮测试回执：`results/checkpoint_frontier/20261009_v3_tests/`、`results/checkpoint_frontier/20261009_native_workspace_tests/`
- 被拒绝的结构变化轮次：`results/checkpoint_frontier/20261009_v3_fixed/`、`results/checkpoint_frontier/20261009_workspace/`；各含 `audit_rejection/receipt.json`。
- 更早共享祖先身份问题的中断预跑：`results/checkpoint_frontier/20261009_v3/`，不得混入正式结果。

## 冻结设置

20 个完整会话、1,206 请求，每条件输入 48,787,785 token。合成串行轮询、历史输入-only。Full/SWA 物理初始容量 589,824/52,224；请求索引 301、603、904 依次半容量、四分之一容量、恢复。页/窗口/分块为 256/128/8,192。

保护最多 8 个单元、Full 262,144、SWA 4,096，受硬预算裁剪。工作空间候选使用：

`Full保护上限 = min(262144, max(0, Full硬预算 − 已到达完整输入页对齐长度的高水位))`

高水位只使用已到达请求；扩容不清缓存且可恢复保护上限。该公式会双计活跃与保护前缀共享的页，且长请求后高水位不下降；尚未证明最优。

## 代码和复核入口

冻结历史源码 `bounded_frontier.py`、`replay_resizable_native.py`、`retained_frontier.py` 不修改。v3 在独立 `checkpoint_frontier.py` 中实现；`native_checkpoint_frontier.py` 只读查找已有精确节点、不额外拆分；`workspace_checkpoint.py` 增加已到达输入工作空间上限。

协议：`configs/checkpoint_frontier_probe_v3_native.json` 和 `configs/checkpoint_workspace_probe_v3_native.json`。源码、配置、顺序和结果哈希均留在各运行目录，`executed_sources/` 保存实际源码副本。运行环境为本实验 `runtime/venv/bin/python`；native CPU 导入使用 `runtime/frontier_pristine_20261008_v1/` 的完整官方包。系统 `python3` 仅用于分析和绘图。

新增运行须使用新结果目录。分析复核命令（输出目录必须不存在）：

```bash
experiments/evicition_policy/runtime/venv/bin/python experiments/evicition_policy/scripts/analyze_checkpoint_frontier.py --source experiments/evicition_policy/results/checkpoint_frontier/20261009_v3_native --output experiments/evicition_policy/results/analysis/<新的v3复核目录>
experiments/evicition_policy/runtime/venv/bin/python experiments/evicition_policy/scripts/analyze_workspace_frontier.py --source experiments/evicition_policy/results/checkpoint_frontier/20261009_workspace_native --v3-analysis experiments/evicition_policy/results/analysis/<新的v3复核目录>/summary.json --output experiments/evicition_policy/results/analysis/<新的workspace复核目录>
```

## 下一阶段边界

本轮工作空间预留已通过半容量、四分之一容量和恢复阶段门槛，优先做独立会话、顺序对照、容量扫描和长请求占比验证，评估共享页双计代价。不要根据这条已探索轨迹不断调参后当作泛化结果。暂不继续微调当前轨迹上的保护预算比例；不要未经独立验证就声称已解决所有极端缩容或动态分区问题。

本轮是 CPU 树和真实索引释放验证，未运行 KV tensor payload、GPU kernels、decode、TTFT、自然时间或混合流量分区反馈。更早 GPU v1 结果的容量/协议不同，不能与本轮命中增量合并。

## 换节点继续

在可访问同一共享项目的节点进入项目根目录，然后要求新对话：

> 请先读取 `experiments/evicition_policy/reports/Agent策略研究接续.md`、实验 README 和最新报告，继续纯 Agent KV 策略论文研究。保留冻结结果，不主动 commit/push。

所有主证据使用项目内相对路径。`/mnt/dai-sys/zhoulongsheng/agentkv` 与当前 `/share/dai-sys/zhoulongsheng/agentkv` 指向同一共享项目；其他节点路径可能不同，应重新核对实际路径和官方包导入，不重置原有实验环境。
