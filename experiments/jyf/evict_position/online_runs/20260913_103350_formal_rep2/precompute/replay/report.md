# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position/workload`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **393.578**
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
| TTFT_ms | 517.310 | 1735.795 | 4335.554 | 777.660 | 1970 |
| TPOT_ms | 22.624 | 53.076 | 195.569 | 31.127 | 1970 |
| e2e_ms | 1299.216 | 2811.753 | 8594.945 | 1745.824 | 1970 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.941 |
| per_req_hit p50/p90 | 0.585 / 0.990 |
| cold_miss_rate | 0.446 |
| cached/prompt | 38175744 / 40548772 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.773 / 1.411 |
| req/s | 5.005 |
| output tok/s | 156.830 |

## OpenHands

| metric | value |
|---|---|
| n | 943 |
| token_weighted_hit | 0.953 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 573.715 / 1141.585 |
| TPOT_ms p50 | 16.982 |
| cached/prompt | 37940480 / 39792804 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.157 |
| per_req_hit p50/p90 | 0.000 / 0.225 |
| TTFT_ms p50/p90 | 825.743 / 2892.347 |
| TPOT_ms p50 | 24.470 |
| cached/prompt | 83712 / 532640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 910 |
| token_weighted_hit | 0.964 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 565.874 / 1102.409 |
| TPOT_ms p50 | 16.553 |
| cached/prompt | 37856768 / 39260164 |

## Request

| metric | value |
|---|---|
| n | 1027 |
| token_weighted_hit | 0.311 |
| per_req_hit p50/p90 | 0.000 / 0.527 |
| TTFT_ms p50/p90 | 438.527 / 2165.234 |
| TPOT_ms p50 | 26.991 |
| cached/prompt | 235264 / 755968 |

## Request turn0

| metric | value |
|---|---|
| n | 539 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 364.065 / 2453.622 |
| TPOT_ms p50 | 29.923 |
| cached/prompt | 0 / 174496 |
