# dsv4_vanilla_lru LRU 基线(官方 sglang 0.5.13 / env agentkv_jyf)

本目录为 ratio_sweep_v4flash_unseen(agentic 比例 0→1, 共 11 组)的 **LRU 基线**结果。
每个 agent_XXX 子目录对应用户对比实验里同一组 workload(agentic 比例 = agent_XXX/100)。

每组子目录产物:
- replay.jsonl  逐请求明细
- summary.json  聚合指标(对比报告主要读它)
- report.md     人类可读报告
- meta.json     运行元信息(workload / arrival / wall_clock_s 等)
- replay.log    本次重放 stdout/stderr

对比参照:用户 agentic(mlp) 样本见
experiments/sglang_kv_cache/mix_replay/v4flash_vanilla/runs/run_mix_ratio000_mlp/
