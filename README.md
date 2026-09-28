# Agentic KV Cache Management

本仓库保存 Agent 请求识别、KV Cache 分区与原生淘汰策略实验的代码、配置、测试和精简报告。

## 存储分工

- GitHub：代码、脚本、配置、测试、设计文档、精简实验结论和数据清单。
- Hugging Face 私有数据集 `1Keria/agentkv-runtime`：模型检查点、派生 workload、完整实验结果和大型运行日志。
- 第三方原始数据不重复上传；通过来源清单和哈希恢复。

详细目录、远端 revision 和恢复命令见 [`docs/数据与模型迁移.md`](docs/数据与模型迁移.md)。

## 当前实验

- 固定分区对照：[`experiments/固定分区试验对比/`](experiments/固定分区试验对比/)
- 原生淘汰策略探索：[`experiments/evicition_policy/`](experiments/evicition_policy/)
- 请求分类模型：[`models/request_classifier/`](models/request_classifier/)

大型文件不要直接加入 Git 历史；先同步到 Hugging Face，再在 GitHub 中更新清单与恢复说明。
