# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/cold_predictor_exp/workloads/agent050_decode32`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **1130.435**
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
| TTFT_ms | 8400.391 | 35701.428 | 42050.212 | 14374.052 | 2000 |
| TPOT_ms | 95.142 | 540.999 | 865.077 | 212.582 | 2000 |
| e2e_ms | 16492.871 | 48180.545 | 60316.132 | 20608.544 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.524 |
| per_req_hit p50/p90 | 0.000 / 0.986 |
| cold_miss_rate | 0.533 |
| cached/prompt | 24731904 / 47192939 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.953 / 2.027 |
| req/s | 1.769 |
| output tok/s | 55.252 |

## OpenHands

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.532 |
| per_req_hit p50/p90 | 0.251 / 0.993 |
| TTFT_ms p50/p90 | 4385.834 / 33745.944 |
| TPOT_ms p50 | 160.019 |
| cached/prompt | 24610816 / 46293549 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.098 |
| per_req_hit p50/p90 | 0.110 / 0.305 |
| TTFT_ms p50/p90 | 4921.342 / 27353.589 |
| TPOT_ms p50 | 71.890 |
| cached/prompt | 59136 / 604033 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 967 |
| token_weighted_hit | 0.537 |
| per_req_hit p50/p90 | 0.404 / 0.993 |
| TTFT_ms p50/p90 | 4223.469 / 33753.869 |
| TPOT_ms p50 | 165.433 |
| cached/prompt | 24551680 / 45689516 |

## Request

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.135 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13245.722 / 37448.960 |
| TPOT_ms p50 | 66.208 |
| cached/prompt | 121088 / 899390 |

## Request turn0

| metric | value |
|---|---|
| n | 500 |
| token_weighted_hit | 0.002 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 6026.082 / 31287.731 |
| TPOT_ms p50 | 66.453 |
| cached/prompt | 512 / 206573 |
