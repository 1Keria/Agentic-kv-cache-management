# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30143`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **346.493**
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
| TTFT_ms | 768.041 | 2916.555 | 4521.915 | 1432.224 | 1261 |
| TPOT_ms | 147.460 | 253.698 | 371.750 | 168.858 | 1261 |
| e2e_ms | 3816.500 | 6394.208 | 7575.125 | 4133.946 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.897 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.636 |
| cached/prompt | 8001792 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.631 / 1.051 |
| req/s | 3.639 |
| output tok/s | 58.229 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 470.770 / 2295.519 |
| TPOT_ms p50 | 127.463 |
| cached/prompt | 7704320 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 2528.168 / 3317.253 |
| TPOT_ms p50 | 231.805 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.952 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 467.433 / 2186.862 |
| TPOT_ms p50 | 126.665 |
| cached/prompt | 7687424 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.391 |
| per_req_hit p50/p90 | 0.000 / 0.621 |
| TTFT_ms p50/p90 | 902.539 / 2956.745 |
| TPOT_ms p50 | 157.138 |
| cached/prompt | 297472 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2298.169 / 3029.160 |
| TPOT_ms p50 | 180.718 |
| cached/prompt | 0 / 174542 |
