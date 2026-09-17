# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position/workload`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **383.52**
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
| TTFT_ms | 494.606 | 1675.790 | 3310.954 | 712.463 | 1970 |
| TPOT_ms | 19.663 | 56.708 | 222.085 | 30.937 | 1970 |
| e2e_ms | 1221.758 | 2974.167 | 7752.986 | 1669.553 | 1970 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.940 |
| per_req_hit p50/p90 | 0.551 / 0.990 |
| cold_miss_rate | 0.457 |
| cached/prompt | 38130176 / 40548772 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.722 / 1.378 |
| req/s | 5.137 |
| output tok/s | 160.980 |

## OpenHands

| metric | value |
|---|---|
| n | 943 |
| token_weighted_hit | 0.953 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 537.747 / 1041.906 |
| TPOT_ms p50 | 15.785 |
| cached/prompt | 37920000 / 39792804 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.118 |
| per_req_hit p50/p90 | 0.000 / 0.179 |
| TTFT_ms p50/p90 | 868.089 / 2576.400 |
| TPOT_ms p50 | 23.572 |
| cached/prompt | 62720 / 532640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 910 |
| token_weighted_hit | 0.964 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 524.711 / 971.701 |
| TPOT_ms p50 | 15.546 |
| cached/prompt | 37857280 / 39260164 |

## Request

| metric | value |
|---|---|
| n | 1027 |
| token_weighted_hit | 0.278 |
| per_req_hit p50/p90 | 0.000 / 0.487 |
| TTFT_ms p50/p90 | 447.166 / 2223.516 |
| TPOT_ms p50 | 22.564 |
| cached/prompt | 210176 / 755968 |

## Request turn0

| metric | value |
|---|---|
| n | 539 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 396.097 / 1864.097 |
| TPOT_ms p50 | 25.492 |
| cached/prompt | 0 / 174496 |
