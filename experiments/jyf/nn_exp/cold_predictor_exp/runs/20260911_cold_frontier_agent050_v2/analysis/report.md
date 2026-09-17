# Cold Predictor Experiment

Trace: `/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/cold_predictor_exp/runs/20260911_cold_frontier_agent050_v2/frontier_trace/frontier_pid2619179_139632434279120.jsonl`

## Cold share in real LRU eviction frontier

| frontier | events | candidate exposures | cold node fraction | cold token fraction | event p50 / p90 |
|---|---:|---:|---:|---:|---:|
| full | 700 | 5182 | 0.9867 | 0.9808 | 1.0000 / 1.0000 |
| swa | 4237 | 40284 | 0.4232 | 0.8875 | 0.4167 / 1.0000 |

Victim cold fraction: nodes=0.775377969762419, tokens=0.9662382692636394

## Predict reuse within 5 future cache-access events — cold frontier only

| strategy | N | positive rate | AUC | AP | Brier | token-Brier | top10 positive recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| cold_only_logistic | 3454 | 0.0182 | 0.9026 | 0.7023 | 0.01310 | 0.01436 | 0.8095 |
| unified_logistic | 3454 | 0.0182 | 0.9008 | 0.5891 | 0.01409 | 0.01489 | 0.7619 |
| parent_sibling_calibrated | 3454 | 0.0182 | 0.7984 | 0.1962 | 0.01751 | 0.01915 | 0.4603 |
| unified_mlp_3seed_ensemble | 3454 | 0.0182 | 0.7786 | 0.0645 | 0.01753 | 0.01931 | 0.4286 |
| lru_recency_calibrated | 3454 | 0.0182 | 0.6472 | 0.0401 | 0.01787 | 0.01949 | 0.3016 |
| cold_global_prior | 3454 | 0.0182 | 0.5000 | 0.0182 | 0.01795 | 0.01963 | — |
| pessimistic_zero | 3454 | 0.0182 | 0.5000 | 0.0182 | 0.01824 | 0.01996 | — |
| cold_only_mlp_3seed_ensemble | 3454 | 0.0182 | 0.4931 | 0.0168 | 0.02286 | 0.02483 | 0.0000 |

## Predict reuse within 20 future cache-access events — cold frontier only

| strategy | N | positive rate | AUC | AP | Brier | token-Brier | top10 positive recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| cold_only_logistic | 3454 | 0.0316 | 0.8785 | 0.5258 | 0.02266 | 0.02471 | 0.7523 |
| unified_logistic | 3454 | 0.0316 | 0.8495 | 0.2627 | 0.02713 | 0.02996 | 0.5780 |
| unified_mlp_3seed_ensemble | 3454 | 0.0316 | 0.8054 | 0.2004 | 0.02836 | 0.03114 | 0.4037 |
| parent_sibling_calibrated | 3454 | 0.0316 | 0.7331 | 0.1540 | 0.02907 | 0.03164 | 0.3303 |
| lru_recency_calibrated | 3454 | 0.0316 | 0.5932 | 0.0500 | 0.03044 | 0.03305 | 0.2110 |
| cold_global_prior | 3454 | 0.0316 | 0.5000 | 0.0316 | 0.03056 | 0.03336 | — |
| pessimistic_zero | 3454 | 0.0316 | 0.5000 | 0.0316 | 0.03156 | 0.03453 | — |
| cold_only_mlp_3seed_ensemble | 3454 | 0.0316 | 0.5303 | 0.0308 | 0.03486 | 0.03787 | 0.0000 |

## Predict reuse within 100 future cache-access events — cold frontier only

| strategy | N | positive rate | AUC | AP | Brier | token-Brier | top10 positive recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| cold_only_logistic | 3452 | 0.1527 | 0.9134 | 0.7146 | 0.07332 | 0.08788 | 0.4839 |
| unified_logistic | 3452 | 0.1527 | 0.9136 | 0.7150 | 0.07440 | 0.08930 | 0.4820 |
| unified_mlp_3seed_ensemble | 3452 | 0.1527 | 0.8820 | 0.6058 | 0.09064 | 0.10762 | 0.4402 |
| cold_only_mlp_3seed_ensemble | 3452 | 0.1527 | 0.8393 | 0.5531 | 0.10435 | 0.12169 | 0.4478 |
| parent_sibling_calibrated | 3452 | 0.1527 | 0.6618 | 0.2311 | 0.12164 | 0.13779 | 0.1101 |
| lru_recency_calibrated | 3452 | 0.1527 | 0.5223 | 0.1736 | 0.12962 | 0.14118 | 0.1309 |
| cold_global_prior | 3452 | 0.1527 | 0.5000 | 0.1527 | 0.12970 | 0.14144 | — |
| pessimistic_zero | 3452 | 0.1527 | 0.5000 | 0.1527 | 0.15266 | 0.17052 | — |

