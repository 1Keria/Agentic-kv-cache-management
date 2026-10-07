# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **348.677**
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
| TTFT_ms | 569.477 | 3379.421 | 5807.907 | 1210.560 | 1261 |
| TPOT_ms | 158.744 | 406.349 | 487.555 | 202.633 | 1261 |
| e2e_ms | 3679.295 | 7679.088 | 9199.915 | 4452.694 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.894 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.646 |
| cached/prompt | 7968512 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.712 / 2494.817 |
| req/s | 3.616 |
| output tok/s | 57.864 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.941 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 454.816 / 2156.812 |
| TPOT_ms p50 | 127.845 |
| cached/prompt | 7676672 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 803.687 / 4546.787 |
| TPOT_ms p50 | 287.798 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.949 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 451.647 / 2138.581 |
| TPOT_ms p50 | 127.298 |
| cached/prompt | 7659776 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.383 |
| per_req_hit p50/p90 | 0.000 / 0.621 |
| TTFT_ms p50/p90 | 621.646 / 4216.962 |
| TPOT_ms p50 | 165.432 |
| cached/prompt | 291840 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 619.550 / 5187.411 |
| TPOT_ms p50 | 194.589 |
| cached/prompt | 0 / 174542 |
