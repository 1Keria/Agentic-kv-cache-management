# SkillsBench with-skills LLM 轨迹

来源：[benchflow/skillsbench-leaderboard](https://huggingface.co/datasets/benchflow/skillsbench-leaderboard)  
只拉 **OpenHands × GLM-5.1 / DeepSeek-V4-Flash / DeepSeek-V4-Pro** 的 `with-skills` 包，且仅保留可重放的 `llm_trajectory.jsonl`。

目录保持 HF 原路径：`submissions/skillsbench/v1.1/<config>/...`  
续传脚本：`scripts/python/download_skillsbench_with_skills.py`

下载完成（2026-08-18）：**910** 个 jsonl，约 **12.0 GB**。

## 包清单

| 模型 | 配置 | files | 体积 |
|---|---|---:|---:|
| GLM-5.1 | `openhands-with-skills__glm-glm-5.1-src-runner04-20260609` | 273 | 3.83 GB |
| GLM-5.1 | `openhands-with-skills__glm-glm-5.1` | 245 | 4.19 GB |
| V4-Flash | `openhands-with-skills__deepseek-deepseek-v4-flash-src-runner03` | 140 | 1.40 GB |
| V4-Flash | `openhands-with-skills__deepseek-deepseek-v4-flash-src-runner05-20260610` | 35 | 0.58 GB |
| V4-Flash | `openhands-with-skills__deepseek-deepseek-v4-flash` | 6 | 0.18 GB |
| V4-Pro | `openhands-with-skills__deepseek-deepseek-v4-pro-src-runner03` | 157 | 1.34 GB |
| V4-Pro | `openhands-with-skills__deepseek-deepseek-v4-pro` | 54 | 0.48 GB |

不同 `src-*` 包之间任务会重叠，不要把 trial 数直接相加。

ACP-only 的 `zai-glm-5.1*` / 无双前缀的 `deepseek-v4-*` **没有下载**。
