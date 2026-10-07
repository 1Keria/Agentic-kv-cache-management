# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **345.685**
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
| TTFT_ms | 660.753 | 3393.995 | 5970.668 | 1337.780 | 1261 |
| TPOT_ms | 158.737 | 350.530 | 570.001 | 208.266 | 1261 |
| e2e_ms | 3795.883 | 7875.650 | 9868.156 | 4670.033 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.901 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.646 |
| cached/prompt | 8034048 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.687 / 10385.582 |
| req/s | 3.648 |
| output tok/s | 58.365 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.950 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 449.490 / 2167.246 |
| TPOT_ms p50 | 126.761 |
| cached/prompt | 7745792 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 937.769 / 7970.236 |
| TPOT_ms p50 | 274.928 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.958 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 441.821 / 2136.623 |
| TPOT_ms p50 | 126.102 |
| cached/prompt | 7737344 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.378 |
| per_req_hit p50/p90 | 0.000 / 0.610 |
| TTFT_ms p50/p90 | 755.061 / 3398.432 |
| TPOT_ms p50 | 176.992 |
| cached/prompt | 288256 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1829.525 / 3577.331 |
| TPOT_ms p50 | 245.454 |
| cached/prompt | 0 / 174542 |
