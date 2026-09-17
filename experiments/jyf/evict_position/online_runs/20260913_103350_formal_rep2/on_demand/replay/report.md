# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position/workload`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **383.28**
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
| TTFT_ms | 458.671 | 1531.215 | 3919.402 | 704.293 | 1970 |
| TPOT_ms | 20.617 | 61.084 | 207.881 | 32.634 | 1970 |
| e2e_ms | 1217.526 | 3182.575 | 7908.848 | 1717.810 | 1970 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.940 |
| per_req_hit p50/p90 | 0.573 / 0.990 |
| cold_miss_rate | 0.450 |
| cached/prompt | 38132480 / 40548772 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.710 / 1.650 |
| req/s | 5.140 |
| output tok/s | 161.096 |

## OpenHands

| metric | value |
|---|---|
| n | 943 |
| token_weighted_hit | 0.953 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 501.834 / 1050.212 |
| TPOT_ms p50 | 15.998 |
| cached/prompt | 37904384 / 39792804 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.118 |
| per_req_hit p50/p90 | 0.000 / 0.179 |
| TTFT_ms p50/p90 | 872.859 / 3232.822 |
| TPOT_ms p50 | 23.389 |
| cached/prompt | 62720 / 532640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 910 |
| token_weighted_hit | 0.964 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 487.083 / 1008.569 |
| TPOT_ms p50 | 15.565 |
| cached/prompt | 37841664 / 39260164 |

## Request

| metric | value |
|---|---|
| n | 1027 |
| token_weighted_hit | 0.302 |
| per_req_hit p50/p90 | 0.000 / 0.512 |
| TTFT_ms p50/p90 | 388.673 / 2052.846 |
| TPOT_ms p50 | 24.079 |
| cached/prompt | 228096 / 755968 |

## Request turn0

| metric | value |
|---|---|
| n | 539 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 327.304 / 1922.836 |
| TPOT_ms p50 | 24.537 |
| cached/prompt | 0 / 174496 |
