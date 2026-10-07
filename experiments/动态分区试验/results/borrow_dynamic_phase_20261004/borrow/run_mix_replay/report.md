# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **379.713**
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
| TTFT_ms | 477.679 | 3074.296 | 5455.819 | 1099.851 | 1261 |
| TPOT_ms | 284.548 | 746.716 | 1501.547 | 426.699 | 1261 |
| e2e_ms | 5893.457 | 15357.747 | 28995.076 | 7927.037 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.636 |
| cached/prompt | 8054528 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.902 / 1.885 |
| req/s | 3.321 |
| output tok/s | 53.135 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.949 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 461.065 / 651.083 |
| TPOT_ms p50 | 126.098 |
| cached/prompt | 7743744 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 670.622 / 719.586 |
| TPOT_ms p50 | 133.696 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.957 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 458.389 / 600.353 |
| TPOT_ms p50 | 126.092 |
| cached/prompt | 7726848 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.408 |
| per_req_hit p50/p90 | 0.000 / 0.635 |
| TTFT_ms p50/p90 | 519.407 / 3514.301 |
| TPOT_ms p50 | 480.377 |
| cached/prompt | 310784 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 477.082 / 4548.489 |
| TPOT_ms p50 | 627.505 |
| cached/prompt | 0 / 174542 |
