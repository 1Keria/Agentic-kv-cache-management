---
license: other
private: true
---

# agentkv-runtime

Private runtime artifacts that cannot go to GitHub because of size or data sensitivity.

Companion code: https://github.com/1Keria/Agentic-kv-cache-management

## Contents

- `models/` — request-classifier and MLP checkpoints/training tensors
- `workloads/` — expanded workload files
- `experiments/session_return/` — GLM session-return replay dumps
- `experiments/sglang_kv_cache/` — KV diagnostic traces
- `experiments/jyf/` — large workload and frontier traces
- `experiments/固定分区试验对比/` — fixed-partition data and complete results
- `experiments/evicition_policy/` — derived Agent workloads and complete LRU/LFU/SLRU evidence

Third-party raw copies such as WildChat and SkillsBench are not included. Derived data is accompanied by source manifests and hashes in the code repository.

The 2026-09-28 migration is documented in `docs/数据与模型迁移.md` in the companion GitHub repository.
