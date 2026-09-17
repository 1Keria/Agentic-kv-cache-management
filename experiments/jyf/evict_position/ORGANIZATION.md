# evict_position 目录说明

## 源码与入口

根目录下保留可直接运行的脚本，避免破坏现有相对路径：

- 	rain.py / 	raining_base.py：训练数据读取、特征构造和 hazard MLP 训练。
- serving_patch.py：SGLang serving 侧 radix cache/frontier 集成。
- predictor.py：在线 predictor 封装。
- un_online.sh / un_suite.py：在线三种 eviction policy 实验入口。
- eport.py / valuate_shift.py：在线结果和分布 shift 分析。
- prepare_workload.py：生成 workload。
- 	est_cache.py / 	est_math.py：cache 行为和数学逻辑测试。
- enchmark_predictor.py / monitor_gpu.py / status.py：性能、GPU 和运行状态辅助工具。

## 数据与运行产物

- 	raining/：训练样本、checkpoint 和训练结果。
- workload/：在线实验使用的 workload。
- 	ests/：本地 cache 测试输出。
- online_runs/：正式在线实验；每个 run 内含日志、source snapshot、metrics 和配置哈希。

## 归档产物

- docs/：Markdown 报告和结论。
- esults/：JSON 汇总、迁移记录和 benchmark 结果。
- logs/：根目录运行日志。
- .cache/：Python __pycache__，可安全删除或重新生成。

现有脚本依赖 	raining/、workload/、	ests/ 和 online_runs/ 的路径，因此这些目录保持原位置。
