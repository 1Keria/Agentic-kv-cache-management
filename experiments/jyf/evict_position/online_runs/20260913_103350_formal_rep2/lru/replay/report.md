# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position/workload`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **413.097**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 1970 |
| n_ok | 1970 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 516.962 | 2158.649 | 6267.870 | 891.363 | 1970 |
| TPOT_ms | 20.500 | 74.124 | 252.945 | 34.831 | 1970 |
| e2e_ms | 1264.558 | 4606.033 | 10602.180 | 1975.856 | 1970 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.920 |
| per_req_hit p50/p90 | 0.592 / 0.990 |
| cold_miss_rate | 0.414 |
| cached/prompt | 37304320 / 40548772 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.788 / 1.387 |
| req/s | 4.769 |
| output tok/s | 149.427 |

## OpenHands

| metric | value |
|---|---|
| n | 943 |
| token_weighted_hit | 0.930 |
| per_req_hit p50/p90 | 0.977 / 0.994 |
| TTFT_ms p50/p90 | 547.565 / 1240.340 |
| TPOT_ms p50 | 15.372 |
| cached/prompt | 37014272 / 39792804 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.237 |
| per_req_hit p50/p90 | 0.224 / 0.299 |
| TTFT_ms p50/p90 | 747.411 / 2779.558 |
| TPOT_ms p50 | 23.212 |
| cached/prompt | 126208 / 532640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 910 |
| token_weighted_hit | 0.940 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 533.412 / 1188.525 |
| TPOT_ms p50 | 14.929 |
| cached/prompt | 36888064 / 39260164 |

## Request

| metric | value |
|---|---|
| n | 1027 |
| token_weighted_hit | 0.384 |
| per_req_hit p50/p90 | 0.000 / 0.607 |
| TTFT_ms p50/p90 | 454.124 / 2408.992 |
| TPOT_ms p50 | 24.842 |
| cached/prompt | 290048 / 755968 |

## Request turn0

| metric | value |
|---|---|
| n | 539 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 412.741 / 2874.376 |
| TPOT_ms p50 | 25.864 |
| cached/prompt | 0 / 174496 |
