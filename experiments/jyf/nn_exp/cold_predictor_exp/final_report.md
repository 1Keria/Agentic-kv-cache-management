# Cold-node predictor experiment

## Experiment scope

- Workload: held-out `agent_050`, 533 sessions / 2000 turns, 50% OpenHands and 50% request traffic.
- Runtime: DeepSeek-V4-Flash, SGLang TP=8, unchanged LRU eviction policy.
- Pressure replay: 9 accelerated waves over 300 seconds; decode capped at 32 tokens. This is a controlled cache-pressure experiment, not a production-latency replay.
- Collection completed with 2000/2000 successful turns and no request failures.
- Instrumentation snapshots the actual Full and SWA eviction frontiers immediately before every real `evict()` and records actual victims. It does not change the eviction choice.
- Cold definition: a node has received zero genuine prefix matches since insertion.
- One TP trace is analyzed because all eight TP ranks contain equivalent cache events.

`req_seq` in this experiment counts genuine cache `match_prefix` events. A user turn may produce multiple such events, so horizons 5/20/100 below mean future cache-access events, not exactly 5/20/100 user requests.

## How much of the real frontier is cold?

| Location | Cold node exposure | Cold token exposure |
|---|---:|---:|
| Full frontier | 98.67% | 98.08% |
| SWA frontier | 42.32% | 88.75% |
| Actual LRU victims | 77.54% | 96.62% |

Cold nodes dominate the bytes at risk. The SWA frontier contains many warm small nodes, but its cold candidates account for 88.75% of candidate token exposure. Across actual victims, 96.62% of evicted tokens belong to cold nodes. Therefore cold start is not an edge case and cannot safely be represented as “infinite reuse distance” without a separate estimate.

There were 5,102 eviction calls and 6,945 victims in the selected trace. Full-frontier event-level cold-node fraction had median 100% and p90 100%; SWA had median 41.67% and p90 100%.

## Labeling and censoring

For each candidate exposure at cache-access event `t`, the label is whether the same stable token-prefix digest is demanded within the next H events, with H in {5, 20, 100}. A later demand is detected even if the original node was evicted and subsequently rebuilt.

Right-censored negatives near the end of the run are excluded unless a positive reuse is already observed inside the horizon. Prefix digests, rather than exposure rows, are split 70/15/15 into train/validation/test so repeated appearances of the same prefix cannot leak across splits.

## Compared strategies

1. `pessimistic_zero`: every cold node receives reuse probability zero.
2. `cold_global_prior`: every cold node receives the training-set cold reuse rate.
3. `lru_recency_calibrated`: LRU position only, with probability calibration.
4. `parent_sibling_calibrated`: parent-hit and sibling-warmth heuristic, with probability calibration.
5. `unified_logistic`: one linear predictor trained on warm and cold rows, with cold/hit/gap indicators.
6. `unified_mlp_3seed_ensemble`: one 64-hidden-unit MLP trained on warm and cold rows; three-seed probability ensemble.
7. `cold_only_logistic`: a separate linear cold-start head using features available for cold nodes.
8. `cold_only_mlp_3seed_ensemble`: a separate cold-start MLP using the same cold-available features.

Cold-available features include node/path length, depth, age, LRU location, parent reuse count, sibling count and warm-sibling fraction, trajectory turn, traffic type, and Full/SWA identity. They do not require the cold node to have its own previous reuse gap.

## Predictor results on cold test candidates

| Horizon | Method | AUC | AP | Brier | token-Brier | Top-10% positive recall |
|---:|---|---:|---:|---:|---:|---:|
| 5 | cold-only Logistic | 0.9026 | 0.7023 | 0.01310 | 0.01436 | 0.8095 |
| 5 | unified Logistic | 0.9008 | 0.5891 | 0.01409 | 0.01489 | 0.7619 |
| 5 | unified MLP | 0.7786 | 0.0645 | 0.01753 | 0.01931 | 0.4286 |
| 5 | global prior | 0.5000 | 0.0182 | 0.01795 | 0.01963 | n/a |
| 20 | cold-only Logistic | 0.8785 | 0.5258 | 0.02266 | 0.02471 | 0.7523 |
| 20 | unified Logistic | 0.8495 | 0.2627 | 0.02713 | 0.02996 | 0.5780 |
| 20 | unified MLP | 0.8054 | 0.2004 | 0.02836 | 0.03114 | 0.4037 |
| 20 | global prior | 0.5000 | 0.0316 | 0.03056 | 0.03336 | n/a |
| 100 | cold-only Logistic | 0.9134 | 0.7146 | 0.07332 | 0.08788 | 0.4839 |
| 100 | unified Logistic | 0.9136 | 0.7150 | 0.07440 | 0.08930 | 0.4820 |
| 100 | unified MLP | 0.8820 | 0.6058 | 0.09064 | 0.10762 | 0.4402 |
| 100 | global prior | 0.5000 | 0.1527 | 0.12970 | 0.14144 | n/a |

Cold-test sizes are 3,454 exposures for horizons 5 and 20 and 3,452 for horizon 100. Their positive rates are 1.82%, 3.16%, and 15.27%, respectively.

## Recommendation

Use a two-path predictor in the first implementation:

- If the node has no own reuse history, route it to a small cold-start Logistic head.
- Once the node has at least one genuine reuse, route it to the regular history-aware predictor using recent gaps and gap statistics.
- Feed both heads a shared context block: path/node length, age, trajectory progress, recent prefix growth, parent/sibling reuse signals, and Full/SWA identity.
- Return a calibrated reuse probability or bucket distribution; do not encode cold nodes as infinite distance.

The cold-only MLP underperformed its linear counterpart, especially at short horizons. The likely cause is severe class imbalance plus a small number of unique cold prefixes; adding nonlinearity increased variance without adding useful signal. A larger MLP is therefore not justified by this trace. The unified Logistic is a reasonable simpler deployment alternative, especially at horizon 100, but the separate cold head is materially better for imminent reuse at horizons 5 and 20.

Before replacing LRU, the next validation should use the predicted probabilities in a held-out eviction replay and compare hit rate, recomputed tokens, and evicted-then-soon-reused tokens. The current experiment establishes frontier prevalence and predictive separability; it does not yet claim an end-to-end cache-policy improvement.
