# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30133`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **350.862**
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
| TTFT_ms | 611.342 | 3075.444 | 4375.131 | 1229.360 | 1261 |
| TPOT_ms | 153.159 | 298.025 | 437.247 | 185.636 | 1261 |
| e2e_ms | 4041.597 | 6312.831 | 7771.694 | 4199.536 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.891 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.638 |
| cached/prompt | 7942912 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.635 / 1.065 |
| req/s | 3.594 |
| output tok/s | 57.504 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.937 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 452.378 / 2190.825 |
| TPOT_ms p50 | 124.107 |
| cached/prompt | 7644160 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.137 |
| per_req_hit p50/p90 | 0.211 / 0.225 |
| TTFT_ms p50/p90 | 894.232 / 3367.747 |
| TPOT_ms p50 | 246.023 |
| cached/prompt | 11264 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 447.709 / 2160.363 |
| TPOT_ms p50 | 122.371 |
| cached/prompt | 7632896 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.392 |
| per_req_hit p50/p90 | 0.000 / 0.625 |
| TTFT_ms p50/p90 | 674.716 / 3138.005 |
| TPOT_ms p50 | 156.149 |
| cached/prompt | 298752 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 758.458 / 3156.261 |
| TPOT_ms p50 | 202.441 |
| cached/prompt | 0 / 174542 |
