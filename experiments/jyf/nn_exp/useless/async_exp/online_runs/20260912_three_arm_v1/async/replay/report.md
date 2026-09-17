# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/cold_predictor_exp/workloads/agent050_decode32`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **1111.666**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 2000 |
| n_ok | 2000 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 8370.957 | 32782.019 | 40016.010 | 12722.285 | 2000 |
| TPOT_ms | 203.587 | 658.825 | 939.492 | 277.579 | 2000 |
| e2e_ms | 17451.997 | 46968.608 | 55780.597 | 21311.279 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.540 |
| per_req_hit p50/p90 | 0.000 / 0.987 |
| cold_miss_rate | 0.586 |
| cached/prompt | 25474560 / 47192939 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.941 / 2.036 |
| req/s | 1.799 |
| output tok/s | 56.234 |

## OpenHands

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.547 |
| per_req_hit p50/p90 | 0.430 / 0.993 |
| TTFT_ms p50/p90 | 3480.912 / 29621.883 |
| TPOT_ms p50 | 199.755 |
| cached/prompt | 25336576 / 46293549 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.084 |
| per_req_hit p50/p90 | 0.067 / 0.184 |
| TTFT_ms p50/p90 | 5617.621 / 21419.998 |
| TPOT_ms p50 | 202.045 |
| cached/prompt | 50688 / 604033 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 967 |
| token_weighted_hit | 0.553 |
| per_req_hit p50/p90 | 0.729 / 0.993 |
| TTFT_ms p50/p90 | 3309.846 / 29729.180 |
| TPOT_ms p50 | 199.694 |
| cached/prompt | 25285888 / 45689516 |

## Request

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.153 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11963.604 / 35415.865 |
| TPOT_ms p50 | 219.566 |
| cached/prompt | 137984 / 899390 |

## Request turn0

| metric | value |
|---|---|
| n | 500 |
| token_weighted_hit | 0.002 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 8370.957 / 27383.914 |
| TPOT_ms p50 | 196.985 |
| cached/prompt | 512 / 206573 |
