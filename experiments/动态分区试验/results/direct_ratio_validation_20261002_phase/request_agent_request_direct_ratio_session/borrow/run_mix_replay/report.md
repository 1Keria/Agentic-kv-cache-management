# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.388**
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
| TTFT_ms | 481.568 | 3854.143 | 10557.453 | 1405.823 | 1261 |
| TPOT_ms | 351.119 | 1108.977 | 1824.355 | 499.543 | 1261 |
| e2e_ms | 6650.468 | 20727.814 | 34526.310 | 9398.517 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.650 |
| cached/prompt | 8055296 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.018 / 2.002 |
| req/s | 3.315 |
| output tok/s | 53.041 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.949 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 472.327 / 639.375 |
| TPOT_ms p50 | 128.476 |
| cached/prompt | 7743744 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 700.109 / 2506.197 |
| TPOT_ms p50 | 141.472 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.957 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 469.969 / 610.601 |
| TPOT_ms p50 | 128.323 |
| cached/prompt | 7726848 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.409 |
| per_req_hit p50/p90 | 0.000 / 0.635 |
| TTFT_ms p50/p90 | 491.803 / 4434.749 |
| TPOT_ms p50 | 543.032 |
| cached/prompt | 311552 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 412.817 / 6169.478 |
| TPOT_ms p50 | 717.043 |
| cached/prompt | 0 / 174542 |
