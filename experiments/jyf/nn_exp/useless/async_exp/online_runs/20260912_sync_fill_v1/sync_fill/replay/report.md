# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/cold_predictor_exp/workloads/agent050_decode32`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **613.145**
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
| TTFT_ms | 1305.082 | 17179.569 | 25591.429 | 4565.132 | 2000 |
| TPOT_ms | 40.106 | 404.688 | 670.106 | 126.155 | 2000 |
| e2e_ms | 2832.931 | 26350.011 | 42180.305 | 8445.605 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.789 |
| per_req_hit p50/p90 | 0.055 / 0.991 |
| cold_miss_rate | 0.483 |
| cached/prompt | 37225984 / 47192939 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.919 / 2.026 |
| req/s | 3.262 |
| output tok/s | 101.919 |

## OpenHands

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.800 |
| per_req_hit p50/p90 | 0.972 / 0.994 |
| TTFT_ms p50/p90 | 1122.494 / 12127.771 |
| TPOT_ms p50 | 30.001 |
| cached/prompt | 37056000 / 46293549 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.089 |
| per_req_hit p50/p90 | 0.100 / 0.359 |
| TTFT_ms p50/p90 | 2573.924 / 13406.018 |
| TPOT_ms p50 | 43.622 |
| cached/prompt | 53760 / 604033 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 967 |
| token_weighted_hit | 0.810 |
| per_req_hit p50/p90 | 0.974 / 0.994 |
| TTFT_ms p50/p90 | 1100.630 / 11919.736 |
| TPOT_ms p50 | 29.466 |
| cached/prompt | 37002240 / 45689516 |

## Request

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.189 |
| per_req_hit p50/p90 | 0.000 / 0.256 |
| TTFT_ms p50/p90 | 1943.657 / 18204.347 |
| TPOT_ms p50 | 45.168 |
| cached/prompt | 169984 / 899390 |

## Request turn0

| metric | value |
|---|---|
| n | 500 |
| token_weighted_hit | 0.002 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1783.474 / 14928.319 |
| TPOT_ms p50 | 47.906 |
| cached/prompt | 512 / 206573 |
