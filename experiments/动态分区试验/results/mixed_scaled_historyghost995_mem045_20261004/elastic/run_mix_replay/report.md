# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30145`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **354.891**
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
| TTFT_ms | 678.493 | 3051.016 | 4710.811 | 1267.713 | 1261 |
| TPOT_ms | 154.954 | 312.605 | 380.825 | 188.675 | 1261 |
| e2e_ms | 3873.462 | 6997.190 | 8117.322 | 4286.520 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.892 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.635 |
| cached/prompt | 7953152 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.636 / 1.070 |
| req/s | 3.553 |
| output tok/s | 56.851 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.937 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 481.834 / 2282.756 |
| TPOT_ms p50 | 125.769 |
| cached/prompt | 7641344 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.156 |
| per_req_hit p50/p90 | 0.211 / 0.225 |
| TTFT_ms p50/p90 | 970.081 / 3369.234 |
| TPOT_ms p50 | 274.802 |
| cached/prompt | 12800 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 480.032 / 2257.138 |
| TPOT_ms p50 | 124.760 |
| cached/prompt | 7628544 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.409 |
| per_req_hit p50/p90 | 0.000 / 0.630 |
| TTFT_ms p50/p90 | 754.862 / 3123.691 |
| TPOT_ms p50 | 164.283 |
| cached/prompt | 311808 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1733.491 / 3154.572 |
| TPOT_ms p50 | 216.338 |
| cached/prompt | 0 / 174542 |
