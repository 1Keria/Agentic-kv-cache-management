# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **508.184**
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
| TTFT_ms | 15772.543 | 29032.995 | 46831.033 | 14338.690 | 1261 |
| TPOT_ms | 854.829 | 2273.582 | 3058.492 | 1028.691 | 1261 |
| e2e_ms | 35134.032 | 48906.512 | 77683.868 | 30797.746 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.805 |
| per_req_hit p50/p90 | 0.000 / 0.951 |
| cold_miss_rate | 0.851 |
| cached/prompt | 7180032 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.713 / 48.058 |
| req/s | 2.481 |
| output tok/s | 39.702 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.966 / 0.991 |
| TTFT_ms p50/p90 | 590.050 / 11920.630 |
| TPOT_ms p50 | 135.093 |
| cached/prompt | 7156992 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.343 |
| TTFT_ms p50/p90 | 11239.766 / 21125.739 |
| TPOT_ms p50 | 2212.189 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.885 |
| per_req_hit p50/p90 | 0.968 / 0.991 |
| TTFT_ms p50/p90 | 581.256 / 11807.426 |
| TPOT_ms p50 | 134.942 |
| cached/prompt | 7148544 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.030 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 16819.039 / 30744.369 |
| TPOT_ms p50 | 886.562 |
| cached/prompt | 23040 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 15835.533 / 22006.677 |
| TPOT_ms p50 | 985.581 |
| cached/prompt | 0 / 174542 |
