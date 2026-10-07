# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **343.835**
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
| TTFT_ms | 762.188 | 3046.811 | 4323.860 | 1276.925 | 1261 |
| TPOT_ms | 140.894 | 239.947 | 295.319 | 157.316 | 1261 |
| e2e_ms | 3371.869 | 5693.755 | 6693.526 | 3793.973 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.905 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.633 |
| cached/prompt | 8068608 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.662 / 1.283 |
| req/s | 3.667 |
| output tok/s | 58.679 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.951 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 474.536 / 2246.898 |
| TPOT_ms p50 | 124.864 |
| cached/prompt | 7755520 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.212 / 0.225 |
| TTFT_ms p50/p90 | 2013.886 / 3488.572 |
| TPOT_ms p50 | 203.266 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.959 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 472.296 / 2155.951 |
| TPOT_ms p50 | 124.564 |
| cached/prompt | 7741440 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.411 |
| per_req_hit p50/p90 | 0.000 / 0.627 |
| TTFT_ms p50/p90 | 856.574 / 3088.737 |
| TPOT_ms p50 | 142.783 |
| cached/prompt | 313088 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1123.167 / 3045.996 |
| TPOT_ms p50 | 147.896 |
| cached/prompt | 0 / 174542 |
