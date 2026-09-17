# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position/workload`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **418.548**
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
| TTFT_ms | 498.306 | 2056.567 | 5771.947 | 855.552 | 1970 |
| TPOT_ms | 23.261 | 116.042 | 272.368 | 44.002 | 1970 |
| e2e_ms | 1355.704 | 6072.048 | 11093.613 | 2221.733 | 1970 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.915 |
| per_req_hit p50/p90 | 0.557 / 0.990 |
| cold_miss_rate | 0.419 |
| cached/prompt | 37107712 / 40548772 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.746 / 1.476 |
| req/s | 4.707 |
| output tok/s | 147.465 |

## OpenHands

| metric | value |
|---|---|
| n | 943 |
| token_weighted_hit | 0.925 |
| per_req_hit p50/p90 | 0.977 / 0.994 |
| TTFT_ms p50/p90 | 553.185 / 1203.408 |
| TPOT_ms p50 | 18.096 |
| cached/prompt | 36823552 / 39792804 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.223 |
| per_req_hit p50/p90 | 0.225 / 0.299 |
| TTFT_ms p50/p90 | 697.192 / 3268.099 |
| TPOT_ms p50 | 29.599 |
| cached/prompt | 119040 / 532640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 910 |
| token_weighted_hit | 0.935 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 547.043 / 1198.235 |
| TPOT_ms p50 | 16.913 |
| cached/prompt | 36704512 / 39260164 |

## Request

| metric | value |
|---|---|
| n | 1027 |
| token_weighted_hit | 0.376 |
| per_req_hit p50/p90 | 0.000 / 0.595 |
| TTFT_ms p50/p90 | 390.274 / 2350.880 |
| TPOT_ms p50 | 29.599 |
| cached/prompt | 284160 / 755968 |

## Request turn0

| metric | value |
|---|---|
| n | 539 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 325.480 / 2612.869 |
| TPOT_ms p50 | 30.068 |
| cached/prompt | 0 / 174496 |
