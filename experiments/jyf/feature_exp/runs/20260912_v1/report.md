# Server-visible feature ablation

Dataset: `third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl`

Warm-prefix test samples use `history >= 1`. Conversation anchors are split 70/15/15, and final observations are right-censored at trace end.

All learned rows use the same 2x64 ReLU discrete-hazard MLP. `constant` is a learned population hazard with no features.

| features | NLL ↓ | mean Brier ↓ | AUC@5s ↑ | AUC@20s ↑ | AUC@60s ↑ | ΔNLL vs constant |
|---|---:|---:|---:|---:|---:|---:|
| constant | 1.5332 ± 0.0000 | 0.2211 | 0.5000 | 0.5000 | 0.5000 | +0.0000 |
| history_recent | 1.4586 ± 0.0049 | 0.2101 | 0.6912 | 0.6247 | 0.6118 | -0.0746 |
| history_summary | 1.4508 ± 0.0017 | 0.2093 | 0.6989 | 0.6289 | 0.6138 | -0.0823 |
| history | 1.4598 ± 0.0018 | 0.2109 | 0.6852 | 0.6141 | 0.5995 | -0.0734 |
| radix_tokens | 1.5302 ± 0.0020 | 0.2174 | 0.5465 | 0.5577 | 0.5636 | -0.0030 |
| radix_shape | 1.5345 ± 0.0009 | 0.2212 | 0.5013 | 0.5012 | 0.5012 | +0.0013 |
| radix | 1.5321 ± 0.0017 | 0.2174 | 0.5508 | 0.5593 | 0.5656 | -0.0010 |
| tools_size | 1.5092 ± 0.0005 | 0.2138 | 0.6734 | 0.6006 | 0.6016 | -0.0240 |
| tools_identity | 1.5080 ± 0.0030 | 0.2080 | 0.6879 | 0.6222 | 0.6250 | -0.0252 |
| tools | 1.5044 ± 0.0020 | 0.2083 | 0.6901 | 0.6249 | 0.6253 | -0.0288 |
| history_recent+tools_size | 1.4297 ± 0.0058 | 0.2033 | 0.7375 | 0.6506 | 0.6476 | -0.1035 |
| history_recent+tools_identity | 1.4632 ± 0.0149 | 0.2039 | 0.7083 | 0.6575 | 0.6601 | -0.0700 |
| history_summary+tools_size | 1.4251 ± 0.0066 | 0.2029 | 0.7470 | 0.6646 | 0.6593 | -0.1081 |
| history_summary+tools_identity | 1.4284 ± 0.0045 | 0.1958 | 0.7499 | 0.6853 | 0.6835 | -0.1048 |
| history_summary+tools | 1.4289 ± 0.0023 | 0.1959 | 0.7452 | 0.6824 | 0.6800 | -0.1043 |
| history+radix | 1.4503 ± 0.0062 | 0.2080 | 0.6884 | 0.6311 | 0.6235 | -0.0829 |
| history+tools | 1.4302 ± 0.0088 | 0.1982 | 0.7324 | 0.6696 | 0.6727 | -0.1029 |
| all | 1.4228 ± 0.0042 | 0.1972 | 0.7409 | 0.6742 | 0.6765 | -0.1104 |

## Feature groups

- `history_recent`: log_recent_gap_1, log_recent_gap_2, log_recent_gap_3, log_recent_gap_4, log_recent_gap_5, log_recent_gap_6, log_recent_gap_7, log_recent_gap_8, recent_gap_mask_1, recent_gap_mask_2, recent_gap_mask_3, recent_gap_mask_4, recent_gap_mask_5, recent_gap_mask_6, recent_gap_mask_7, recent_gap_mask_8
- `history_summary`: gap statistics, reuse count, and prior-access counts in fixed windows.
- `history`: `history_recent` plus `history_summary`.
- `radix_tokens`: log_prefix_tokens, log_node_tokens
- `radix_shape`: log_child_count, is_leaf
- `radix`: `radix_tokens` plus `radix_shape`.
- `tools_size`: tool count and serialized schema bytes.
- `tools_identity`: a 32-dimensional signed hash of tool names.
- `tools`: `tools_size` plus `tools_identity`.

The tree features are evaluated because they are server-visible, not because the experiment assumes they are useful. Incremental rows (`history+radix`, `history+tools`, `all`) determine whether they add signal after reuse history is known.

Parsed 16559 requests into 373228 prefix observations; 162509 have at least one previous reuse.
