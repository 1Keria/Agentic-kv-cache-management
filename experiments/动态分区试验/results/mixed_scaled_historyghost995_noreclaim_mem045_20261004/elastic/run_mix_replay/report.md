# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **348.345**
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
| TTFT_ms | 665.062 | 3368.376 | 5609.479 | 1303.526 | 1261 |
| TPOT_ms | 141.366 | 254.052 | 343.875 | 166.093 | 1261 |
| e2e_ms | 3567.038 | 6198.582 | 7912.910 | 3961.009 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.904 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.636 |
| cached/prompt | 8057856 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.686 / 74.703 |
| req/s | 3.620 |
| output tok/s | 57.919 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.951 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 484.381 / 2247.282 |
| TPOT_ms p50 | 124.248 |
| cached/prompt | 7756544 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.212 / 0.225 |
| TTFT_ms p50/p90 | 1185.861 / 4299.385 |
| TPOT_ms p50 | 251.001 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.959 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 478.603 / 2203.336 |
| TPOT_ms p50 | 123.130 |
| cached/prompt | 7742464 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.396 |
| per_req_hit p50/p90 | 0.000 / 0.625 |
| TTFT_ms p50/p90 | 741.386 / 4206.232 |
| TPOT_ms p50 | 144.737 |
| cached/prompt | 301312 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 837.363 / 5309.914 |
| TPOT_ms p50 | 161.855 |
| cached/prompt | 0 / 174542 |
