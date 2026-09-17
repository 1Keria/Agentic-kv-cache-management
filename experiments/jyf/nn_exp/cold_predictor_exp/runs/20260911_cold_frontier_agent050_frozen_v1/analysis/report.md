# Cold Predictor Experiment

Trace: `/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/cold_predictor_exp/runs/20260911_cold_frontier_agent050_frozen_v1/frontier_trace/frontier_pid3797866_140187773175760.jsonl`

## Cold share in real LRU eviction frontier

| frontier | events | candidate exposures | cold node fraction | cold token fraction | event p50 / p90 |
|---|---:|---:|---:|---:|---:|
| full | 626 | 4515 | 0.9825 | 0.9766 | 1.0000 / 1.0000 |
| swa | 692 | 25370 | 0.2318 | 0.2372 | 0.2500 / 0.6145 |

Victim cold fraction: nodes=0.3771976558337773, tokens=0.3082063217959306

## Predict reuse within 5 future cache-access events — cold frontier only

| strategy | N | positive rate | AUC | AP | Brier | token-Brier | top10 positive recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| unified_mlp_3seed_ensemble | 1844 | 0.0992 | 0.7765 | 0.4535 | 0.07424 | 0.11561 | 0.4153 |
| cold_only_logistic | 1844 | 0.0992 | 0.7487 | 0.4194 | 0.07686 | 0.10768 | 0.4262 |
| unified_logistic | 1844 | 0.0992 | 0.7155 | 0.3403 | 0.08278 | 0.14326 | 0.3388 |
| parent_sibling_calibrated | 1844 | 0.0992 | 0.6740 | 0.1792 | 0.08648 | 0.19312 | 0.1530 |
| lru_recency_calibrated | 1844 | 0.0992 | 0.5985 | 0.1423 | 0.08908 | 0.19721 | 0.1749 |
| cold_global_prior | 1844 | 0.0992 | 0.5000 | 0.0992 | 0.08990 | 0.20620 | — |
| pessimistic_zero | 1844 | 0.0992 | 0.5000 | 0.0992 | 0.09924 | 0.25303 | — |
| cold_only_mlp_3seed_ensemble | 1844 | 0.0992 | 0.7694 | 0.2903 | 0.10139 | 0.17724 | 0.3279 |

## Predict reuse within 20 future cache-access events — cold frontier only

| strategy | N | positive rate | AUC | AP | Brier | token-Brier | top10 positive recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| cold_only_logistic | 1840 | 0.2141 | 0.7310 | 0.4702 | 0.15218 | 0.17590 | 0.2437 |
| unified_mlp_3seed_ensemble | 1840 | 0.2141 | 0.7219 | 0.4452 | 0.15359 | 0.19923 | 0.2335 |
| cold_only_mlp_3seed_ensemble | 1840 | 0.2141 | 0.7059 | 0.4398 | 0.15703 | 0.20551 | 0.2437 |
| parent_sibling_calibrated | 1840 | 0.2141 | 0.5901 | 0.2796 | 0.16745 | 0.26925 | 0.1091 |
| lru_recency_calibrated | 1840 | 0.2141 | 0.5683 | 0.2594 | 0.16964 | 0.26095 | 0.1421 |
| cold_global_prior | 1840 | 0.2141 | 0.5000 | 0.2141 | 0.17017 | 0.27177 | — |
| unified_logistic | 1840 | 0.2141 | 0.6687 | 0.3688 | 0.17046 | 0.22749 | 0.2081 |
| pessimistic_zero | 1840 | 0.2141 | 0.5000 | 0.2141 | 0.21413 | 0.42370 | — |

## Predict reuse within 100 future cache-access events — cold frontier only

| strategy | N | positive rate | AUC | AP | Brier | token-Brier | top10 positive recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| cold_only_logistic | 1770 | 0.3802 | 0.7939 | 0.7073 | 0.18271 | 0.14018 | 0.2140 |
| unified_mlp_3seed_ensemble | 1770 | 0.3802 | 0.7798 | 0.6919 | 0.18419 | 0.13441 | 0.2110 |
| cold_only_mlp_3seed_ensemble | 1770 | 0.3802 | 0.7684 | 0.6855 | 0.19259 | 0.15254 | 0.2184 |
| unified_logistic | 1770 | 0.3802 | 0.7579 | 0.6584 | 0.20155 | 0.13496 | 0.2036 |
| parent_sibling_calibrated | 1770 | 0.3802 | 0.6285 | 0.5080 | 0.21940 | 0.28226 | 0.1694 |
| lru_recency_calibrated | 1770 | 0.3802 | 0.5909 | 0.4571 | 0.23114 | 0.26048 | 0.1412 |
| cold_global_prior | 1770 | 0.3802 | 0.5000 | 0.3802 | 0.23744 | 0.28057 | — |
| pessimistic_zero | 1770 | 0.3802 | 0.5000 | 0.3802 | 0.38023 | 0.65846 | — |

