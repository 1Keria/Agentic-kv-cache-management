# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **358.307**
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
| TTFT_ms | 773.907 | 3876.009 | 6021.465 | 1516.958 | 1261 |
| TPOT_ms | 183.717 | 350.185 | 410.677 | 210.571 | 1261 |
| e2e_ms | 4991.247 | 7141.369 | 8917.181 | 4886.089 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.866 |
| per_req_hit p50/p90 | 0.000 / 0.963 |
| cold_miss_rate | 0.657 |
| cached/prompt | 7724032 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.686 / 3344.041 |
| req/s | 3.519 |
| output tok/s | 56.309 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.912 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 466.490 / 2319.701 |
| TPOT_ms p50 | 125.965 |
| cached/prompt | 7434496 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 1785.335 / 6323.066 |
| TPOT_ms p50 | 336.196 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.920 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 461.638 / 2263.679 |
| TPOT_ms p50 | 124.792 |
| cached/prompt | 7428864 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.380 |
| per_req_hit p50/p90 | 0.000 / 0.617 |
| TTFT_ms p50/p90 | 898.565 / 4250.401 |
| TPOT_ms p50 | 196.673 |
| cached/prompt | 289536 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1258.432 / 5311.575 |
| TPOT_ms p50 | 225.012 |
| cached/prompt | 0 / 174542 |
