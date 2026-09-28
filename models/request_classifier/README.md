# Request Classifier

这是缓存策略第一层使用的请求级分类器，输出
`P(agent_like | request features)`。完整实验记录见
[`docs/请求分类模型特征预算实验.md`](../../docs/请求分类模型特征预算实验.md)。

本目录的 Python 源码保存在 GitHub；`cache/` 和 `checkpoints/` 保存在私有 Hugging Face 数据集 `1Keria/agentkv-runtime` 的同名路径。首次复现实验前按 [`docs/数据与模型迁移.md`](../../docs/数据与模型迁移.md) 恢复模型文件，不要把 checkpoint 或训练缓存直接提交到 Git。

## 数据与输入

实验覆盖三类真实来源：`third_party/glm-5dot1_onlinedata`、`third_party/skillsbench` 和
`third_party/wildchat`。GLM 是混合真实流量，不应按来源名直接视为 agent；当前已核查 6 条
普通 GLM 请求并修正标签。`workloads/` 下的 36 个文件是派生 workload，不是独立数据集；按
来源身份、调用位置、`max_tokens` 和 `prompt_body` 去重后为 66,592 条、31,166 个来源组。

模型只读取请求到达时可见的 `prompt_body` 结构和 `max_tokens`，不使用标签、session/source
身份、到达间隔、缓存结果或原始文本词汇。完整候选特征见 `features.py`。

### 特征释义

| 特征 | 含义 |
| --- | --- |
| `has_tools` | 是否提供工具定义 |
| `log_tool_count` | 工具数量的 `log1p` |
| `log_tool_schema_chars` | 紧凑 JSON 工具 schema 字符数的 `log1p` |
| `log_message_count` | 消息总数的 `log1p` |
| `n_system_messages` / `n_user_messages` | system / user 消息数量 |
| `n_assistant_messages` / `n_tool_messages` | assistant / tool 消息数量 |
| `n_function_messages` | function 角色消息数量 |
| `log_tool_call_count` | `tool_calls` 数量的 `log1p` |
| `has_tool_role` | 是否出现 tool 角色 |
| `has_tool_calls` | 是否出现 `tool_calls` 或旧格式 `function_call` |
| `log_content_chars` | 所有消息 content 字符规模的 `log1p` |
| `log_system_chars` / `log_tool_message_chars` | system / tool content 字符规模的 `log1p` |
| `log_max_tokens` | 输出 token 预算的 `log1p` |

`log1p(x)=log(1+x)`，用于压缩长尾。字符特征只使用长度，不使用具体文本词汇；
`function_call` 只影响 `has_tool_calls`，不计入 `log_tool_call_count`。

## 最终预算

| 预算 | 特征 | GLM 混合流量 accuracy |
| ---: | --- | ---: |
| 1 | `n_system_messages` | 100.0000% |
| 2 | `has_tools`, `n_system_messages` | 99.9879% |
| 4 | `has_tools`, `log_message_count`, `n_system_messages`, `n_tool_messages` | 99.9879% |
| 8 | 4 维 + 工具数量/schema/call/内容长度 | 99.9879% |
| 12 | 8 维 + 工具调用/系统与工具内容/输出预算 | 99.9879% |
| 16 | 全部 16 维 | 99.9879% |

修正标签后 1 维在当前数据上达到 100%，但由于 GLM 尚未完成完整语义审计，暂不指定生产默认；
2 维是带工具冗余的低维候选，4 维是稳健扩展，16 维只作消融。

### 最新并行搜索结果

本轮使用 7 张 H100 对每个预算独立搜索，并用来源留出做主验收。详细结果见
`checkpoints/feature_budget_identity_experiment.json`，新 checkpoint 位于
`checkpoints/final_searched/`。

| 预算 | 最佳输入特征 | 跨来源 accuracy |
| ---: | --- | ---: |
| 1 | `log_system_chars` | 100.0000% |
| 2 | `n_system_messages`, `log_max_tokens` | 100.0000% |
| 4 | `has_tools`, `n_system_messages`, `log_system_chars`, `log_tool_message_chars` | 100.0000% |
| 8 | `has_tools`, `log_tool_count`, `log_tool_schema_chars`, `log_message_count`, `n_system_messages`, `n_assistant_messages`, `log_system_chars`, `log_max_tokens` | 99.9687% |
| 12 | `log_tool_count`, `log_tool_schema_chars`, `log_message_count`, `n_system_messages`, `n_user_messages`, `n_assistant_messages`, `n_tool_messages`, `n_function_messages`, `has_tool_role`, `log_content_chars`, `log_system_chars`, `log_tool_message_chars` | 99.9543% |
| 16 | 全部 16 个候选特征 | 99.9471% |

当前数据下，1 维是最低延迟候选，4 维是推荐的实验默认；这些结果仍受 GLM 标签审计完整性和
system 模板分布限制，不能直接等同于未知线上流量的身份识别保证。

额外验证的 system-free 4 维候选为 `has_tools`、`log_tool_count`、`has_tool_calls`、
`log_content_chars`，跨来源 accuracy 为 99.9952%（漏 2 条 Agent）。它略低于 system-heavy
4 维，但不依赖 `n_system_messages`，适合 system 协议不稳定的实验对照。反事实压力测试见
`checkpoints/feature_budget_counterfactual.json`。

## 推理

```python
from models.request_classifier.infer import RequestClassifier

classifier = RequestClassifier.load(
    "models/request_classifier/checkpoints/final_system_free/budget_4/request_classifier.pt"
)
q_agent = classifier.predict_proba(prompt_body, max_tokens)
traffic_class = classifier.classify(prompt_body, max_tokens)
```

保留 `q_agent` 概率，再由缓存区域配置决定逻辑归属；不要把离线真实标签传给分类器。

当前接入系统的 system-free 4 维 checkpoint 为：

```text
models/request_classifier/checkpoints/final_system_free/budget_4/request_classifier.pt
```

区域接入、固定 token 配额和后端限制见
[`docs/请求分类区域接入方案.md`](../../docs/请求分类区域接入方案.md)。

## 复现实验

```bash
python models/request_classifier/search_budgets.py \
  --cache models/request_classifier/cache/raw_source_unique_corrected.npz \
  --device cuda:0
python models/request_classifier/cross_source_eval.py \
  --cache models/request_classifier/cache/raw_source_unique_corrected.npz \
  --search-report models/request_classifier/checkpoints/feature_budget_search.json \
  --out models/request_classifier/checkpoints/cross_source_eval_v2.json \
  --device cuda:0
python models/request_classifier/finalize_budgets.py \
  --cache models/request_classifier/cache/raw_source_unique_corrected.npz \
  --device cuda:0
```
