# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/cold_predictor_exp/workloads/agent050_decode32`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **1731.296**
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
| TTFT_ms | 33841.906 | 46635.810 | 56489.860 | 29604.791 | 2000 |
| TPOT_ms | 329.993 | 761.477 | 1476.015 | 386.411 | 2000 |
| e2e_ms | 45046.615 | 59309.091 | 69027.360 | 41138.866 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.328 |
| per_req_hit p50/p90 | 0.000 / 0.683 |
| cold_miss_rate | 0.597 |
| cached/prompt | 15500288 / 47192939 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.945 / 2.079 |
| req/s | 1.155 |
| output tok/s | 36.115 |

## OpenHands

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.335 |
| per_req_hit p50/p90 | 0.072 / 0.991 |
| TTFT_ms p50/p90 | 31022.694 / 43231.623 |
| TPOT_ms p50 | 326.075 |
| cached/prompt | 15490816 / 46293549 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.079 |
| per_req_hit p50/p90 | 0.053 / 0.299 |
| TTFT_ms p50/p90 | 31537.048 / 44524.316 |
| TPOT_ms p50 | 241.705 |
| cached/prompt | 47872 / 604033 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 967 |
| token_weighted_hit | 0.338 |
| per_req_hit p50/p90 | 0.072 / 0.992 |
| TTFT_ms p50/p90 | 31016.826 / 43048.068 |
| TPOT_ms p50 | 328.082 |
| cached/prompt | 15442944 / 45689516 |

## Request

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.011 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 37244.626 / 50675.924 |
| TPOT_ms p50 | 340.211 |
| cached/prompt | 9472 / 899390 |

## Request turn0

| metric | value |
|---|---|
| n | 500 |
| token_weighted_hit | 0.002 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 33287.038 / 50123.231 |
| TPOT_ms p50 | 247.838 |
| cached/prompt | 512 / 206573 |
