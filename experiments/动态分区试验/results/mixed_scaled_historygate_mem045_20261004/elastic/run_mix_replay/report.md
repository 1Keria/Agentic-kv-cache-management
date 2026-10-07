# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30139`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **344.198**
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
| TTFT_ms | 596.371 | 2936.375 | 8039.605 | 1407.105 | 1261 |
| TPOT_ms | 143.869 | 271.377 | 345.306 | 174.238 | 1261 |
| e2e_ms | 3319.500 | 6328.978 | 10517.597 | 4194.918 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.902 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.632 |
| cached/prompt | 8040704 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.668 / 19.739 |
| req/s | 3.664 |
| output tok/s | 58.617 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.946 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 465.699 / 2174.438 |
| TPOT_ms p50 | 125.090 |
| cached/prompt | 7716352 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.220 / 0.227 |
| TTFT_ms p50/p90 | 875.173 / 6379.519 |
| TPOT_ms p50 | 230.106 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.954 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 462.244 / 1348.690 |
| TPOT_ms p50 | 124.255 |
| cached/prompt | 7702272 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.426 |
| per_req_hit p50/p90 | 0.000 / 0.636 |
| TTFT_ms p50/p90 | 651.894 / 4242.309 |
| TPOT_ms p50 | 153.146 |
| cached/prompt | 324352 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 674.208 / 5930.166 |
| TPOT_ms p50 | 195.064 |
| cached/prompt | 0 / 174542 |
