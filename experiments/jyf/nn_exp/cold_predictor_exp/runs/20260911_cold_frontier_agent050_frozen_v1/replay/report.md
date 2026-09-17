# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/cold_predictor_exp/workloads/agent050_decode32`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **11010.07**
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
| TTFT_ms | 335.946 | 1626.790 | 5002.450 | 668.507 | 2000 |
| TPOT_ms | 8.364 | 58.049 | 202.051 | 24.924 | 2000 |
| e2e_ms | 701.312 | 3024.050 | 10648.103 | 1418.485 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.923 |
| per_req_hit p50/p90 | 0.631 / 0.992 |
| cold_miss_rate | 0.441 |
| cached/prompt | 43542528 / 47192939 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.730 / 1.801 |
| req/s | 0.182 |
| output tok/s | 5.677 |

## OpenHands

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.936 |
| per_req_hit p50/p90 | 0.981 / 0.995 |
| TTFT_ms p50/p90 | 351.416 / 971.237 |
| TPOT_ms p50 | 7.688 |
| cached/prompt | 43329024 / 46293549 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.126 |
| per_req_hit p50/p90 | 0.137 / 0.512 |
| TTFT_ms p50/p90 | 2439.547 / 3729.561 |
| TPOT_ms p50 | 78.881 |
| cached/prompt | 76032 / 604033 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 967 |
| token_weighted_hit | 0.947 |
| per_req_hit p50/p90 | 0.982 / 0.995 |
| TTFT_ms p50/p90 | 345.748 / 759.457 |
| TPOT_ms p50 | 7.682 |
| cached/prompt | 43252992 / 45689516 |

## Request

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.237 |
| per_req_hit p50/p90 | 0.000 / 0.484 |
| TTFT_ms p50/p90 | 301.924 / 2118.596 |
| TPOT_ms p50 | 18.886 |
| cached/prompt | 213504 / 899390 |

## Request turn0

| metric | value |
|---|---|
| n | 500 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 359.139 / 4063.689 |
| TPOT_ms p50 | 44.672 |
| cached/prompt | 0 / 206573 |
