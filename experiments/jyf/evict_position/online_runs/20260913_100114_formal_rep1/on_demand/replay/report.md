# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position/workload`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **383.633**
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
| TTFT_ms | 489.034 | 1712.952 | 3538.770 | 705.118 | 1970 |
| TPOT_ms | 21.431 | 55.314 | 282.432 | 34.071 | 1970 |
| e2e_ms | 1258.179 | 2842.475 | 11455.503 | 1761.570 | 1970 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.942 |
| per_req_hit p50/p90 | 0.593 / 0.990 |
| cold_miss_rate | 0.445 |
| cached/prompt | 38187520 / 40548772 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.771 / 1.743 |
| req/s | 5.135 |
| output tok/s | 160.932 |

## OpenHands

| metric | value |
|---|---|
| n | 943 |
| token_weighted_hit | 0.954 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 532.433 / 1084.982 |
| TPOT_ms p50 | 15.537 |
| cached/prompt | 37956352 / 39792804 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.121 |
| per_req_hit p50/p90 | 0.000 / 0.179 |
| TTFT_ms p50/p90 | 799.394 / 2883.348 |
| TPOT_ms p50 | 31.755 |
| cached/prompt | 64512 / 532640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 910 |
| token_weighted_hit | 0.965 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 522.323 / 1044.757 |
| TPOT_ms p50 | 15.119 |
| cached/prompt | 37891840 / 39260164 |

## Request

| metric | value |
|---|---|
| n | 1027 |
| token_weighted_hit | 0.306 |
| per_req_hit p50/p90 | 0.000 / 0.527 |
| TTFT_ms p50/p90 | 424.387 / 1881.551 |
| TPOT_ms p50 | 25.846 |
| cached/prompt | 231168 / 755968 |

## Request turn0

| metric | value |
|---|---|
| n | 539 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 345.571 / 1801.470 |
| TPOT_ms p50 | 27.543 |
| cached/prompt | 0 / 174496 |
