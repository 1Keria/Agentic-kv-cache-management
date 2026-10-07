# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **357.287**
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
| TTFT_ms | 781.440 | 3404.667 | 5546.086 | 1525.746 | 1261 |
| TPOT_ms | 158.995 | 343.990 | 496.818 | 206.064 | 1261 |
| e2e_ms | 4940.309 | 7714.831 | 8822.455 | 4822.770 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.872 |
| per_req_hit p50/p90 | 0.000 / 0.963 |
| cold_miss_rate | 0.651 |
| cached/prompt | 7775488 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.655 / 489.260 |
| req/s | 3.529 |
| output tok/s | 56.470 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.917 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 448.566 / 2305.258 |
| TPOT_ms p50 | 126.066 |
| cached/prompt | 7479296 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 2307.340 / 4639.475 |
| TPOT_ms p50 | 316.862 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.926 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 444.118 / 2240.831 |
| TPOT_ms p50 | 125.794 |
| cached/prompt | 7473664 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.389 |
| per_req_hit p50/p90 | 0.000 / 0.615 |
| TTFT_ms p50/p90 | 963.947 / 4279.955 |
| TPOT_ms p50 | 170.798 |
| cached/prompt | 296192 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1810.853 / 4753.758 |
| TPOT_ms p50 | 222.874 |
| cached/prompt | 0 / 174542 |
