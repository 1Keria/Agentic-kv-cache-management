# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position/workload`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **412.067**
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
| TTFT_ms | 494.049 | 2221.529 | 5865.820 | 889.270 | 1970 |
| TPOT_ms | 20.753 | 76.825 | 275.806 | 35.609 | 1970 |
| e2e_ms | 1294.758 | 3859.318 | 9802.567 | 1976.228 | 1970 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.919 |
| per_req_hit p50/p90 | 0.589 / 0.990 |
| cold_miss_rate | 0.413 |
| cached/prompt | 37280512 / 40548772 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.750 / 1.549 |
| req/s | 4.781 |
| output tok/s | 149.815 |

## OpenHands

| metric | value |
|---|---|
| n | 943 |
| token_weighted_hit | 0.930 |
| per_req_hit p50/p90 | 0.977 / 0.994 |
| TTFT_ms p50/p90 | 542.098 / 1272.921 |
| TPOT_ms p50 | 17.062 |
| cached/prompt | 36991488 / 39792804 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.231 |
| per_req_hit p50/p90 | 0.225 / 0.299 |
| TTFT_ms p50/p90 | 850.697 / 3855.425 |
| TPOT_ms p50 | 26.386 |
| cached/prompt | 122880 / 532640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 910 |
| token_weighted_hit | 0.939 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 529.527 / 1252.086 |
| TPOT_ms p50 | 16.351 |
| cached/prompt | 36868608 / 39260164 |

## Request

| metric | value |
|---|---|
| n | 1027 |
| token_weighted_hit | 0.382 |
| per_req_hit p50/p90 | 0.000 / 0.609 |
| TTFT_ms p50/p90 | 390.123 / 2548.548 |
| TPOT_ms p50 | 24.381 |
| cached/prompt | 289024 / 755968 |

## Request turn0

| metric | value |
|---|---|
| n | 539 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 367.674 / 2729.619 |
| TPOT_ms p50 | 29.237 |
| cached/prompt | 0 / 174496 |
