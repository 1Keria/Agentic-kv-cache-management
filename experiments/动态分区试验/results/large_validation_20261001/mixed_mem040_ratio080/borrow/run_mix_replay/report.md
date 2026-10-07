# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **353.631**
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
| TTFT_ms | 741.689 | 5678.824 | 9878.038 | 2037.885 | 1261 |
| TPOT_ms | 183.940 | 545.205 | 784.195 | 254.163 | 1261 |
| e2e_ms | 3992.549 | 16401.960 | 17671.497 | 6104.493 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.865 |
| per_req_hit p50/p90 | 0.000 / 0.961 |
| cold_miss_rate | 0.722 |
| cached/prompt | 7712000 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.627 / 1.067 |
| req/s | 3.566 |
| output tok/s | 57.054 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.923 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 467.164 / 2000.925 |
| TPOT_ms p50 | 127.899 |
| cached/prompt | 7527936 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 926.805 / 8303.700 |
| TPOT_ms p50 | 358.867 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.931 |
| per_req_hit p50/p90 | 0.970 / 0.992 |
| TTFT_ms p50/p90 | 464.309 / 1668.516 |
| TPOT_ms p50 | 127.448 |
| cached/prompt | 7519488 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.242 |
| per_req_hit p50/p90 | 0.000 / 0.453 |
| TTFT_ms p50/p90 | 834.552 / 7824.964 |
| TPOT_ms p50 | 191.581 |
| cached/prompt | 184064 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1330.050 / 8424.029 |
| TPOT_ms p50 | 233.827 |
| cached/prompt | 0 / 174542 |
