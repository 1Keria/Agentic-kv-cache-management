# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **349.188**
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
| TTFT_ms | 700.358 | 4151.968 | 6166.062 | 1505.068 | 1261 |
| TPOT_ms | 143.130 | 248.909 | 314.448 | 163.793 | 1261 |
| e2e_ms | 3532.894 | 6356.009 | 8914.665 | 4125.760 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.904 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.636 |
| cached/prompt | 8062976 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.666 / 1.072 |
| req/s | 3.611 |
| output tok/s | 57.780 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.950 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 452.934 / 2230.491 |
| TPOT_ms p50 | 128.340 |
| cached/prompt | 7748864 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.137 |
| per_req_hit p50/p90 | 0.212 / 0.225 |
| TTFT_ms p50/p90 | 984.624 / 6184.424 |
| TPOT_ms p50 | 223.348 |
| cached/prompt | 11264 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.958 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 449.228 / 2152.374 |
| TPOT_ms p50 | 128.043 |
| cached/prompt | 7737600 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.412 |
| per_req_hit p50/p90 | 0.000 / 0.627 |
| TTFT_ms p50/p90 | 788.375 / 4289.292 |
| TPOT_ms p50 | 146.207 |
| cached/prompt | 314112 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1917.553 / 5768.430 |
| TPOT_ms p50 | 166.638 |
| cached/prompt | 0 / 174542 |
