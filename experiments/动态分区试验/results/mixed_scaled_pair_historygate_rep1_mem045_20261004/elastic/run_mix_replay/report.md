# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **343.92**
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
| TTFT_ms | 613.180 | 3068.725 | 5098.802 | 1180.081 | 1261 |
| TPOT_ms | 151.063 | 303.471 | 353.554 | 185.749 | 1261 |
| e2e_ms | 3409.453 | 7458.217 | 8484.081 | 4152.070 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.630 |
| cached/prompt | 8080384 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.666 / 11.153 |
| req/s | 3.667 |
| output tok/s | 58.665 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.952 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 458.111 / 2260.426 |
| TPOT_ms p50 | 127.525 |
| cached/prompt | 7763712 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 832.966 / 3741.097 |
| TPOT_ms p50 | 256.829 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.960 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 451.987 / 1335.263 |
| TPOT_ms p50 | 127.210 |
| cached/prompt | 7746816 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.416 |
| per_req_hit p50/p90 | 0.000 / 0.630 |
| TTFT_ms p50/p90 | 676.134 / 3094.707 |
| TPOT_ms p50 | 155.235 |
| cached/prompt | 316672 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 710.752 / 3297.845 |
| TPOT_ms p50 | 220.317 |
| cached/prompt | 0 / 174542 |
