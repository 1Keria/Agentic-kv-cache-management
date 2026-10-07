# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **354.034**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 1261 |
| n_ok | 1261 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 728.029 | 3607.856 | 4943.468 | 1475.554 | 1261 |
| TPOT_ms | 145.153 | 253.658 | 324.425 | 168.070 | 1261 |
| e2e_ms | 4071.971 | 6312.637 | 7581.609 | 4164.668 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.888 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.640 |
| cached/prompt | 7917824 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.643 / 1.046 |
| req/s | 3.562 |
| output tok/s | 56.989 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.934 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 465.649 / 2247.168 |
| TPOT_ms p50 | 129.826 |
| cached/prompt | 7614720 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 2281.335 / 3606.686 |
| TPOT_ms p50 | 230.320 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.941 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 459.432 / 2171.463 |
| TPOT_ms p50 | 128.783 |
| cached/prompt | 7597824 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.398 |
| per_req_hit p50/p90 | 0.000 / 0.620 |
| TTFT_ms p50/p90 | 806.193 / 4260.895 |
| TPOT_ms p50 | 149.658 |
| cached/prompt | 303104 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2004.693 / 4706.666 |
| TPOT_ms p50 | 160.791 |
| cached/prompt | 0 / 174542 |
