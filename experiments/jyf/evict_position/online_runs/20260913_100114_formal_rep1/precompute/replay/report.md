# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position/workload`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **393.2**
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
| TTFT_ms | 544.344 | 1702.107 | 3373.967 | 750.149 | 1970 |
| TPOT_ms | 21.855 | 57.487 | 220.579 | 32.438 | 1970 |
| e2e_ms | 1328.233 | 2900.494 | 7614.017 | 1759.912 | 1970 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.941 |
| per_req_hit p50/p90 | 0.597 / 0.990 |
| cold_miss_rate | 0.451 |
| cached/prompt | 38175232 / 40548772 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.791 / 1.546 |
| req/s | 5.010 |
| output tok/s | 156.989 |

## OpenHands

| metric | value |
|---|---|
| n | 943 |
| token_weighted_hit | 0.953 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 595.823 / 1221.253 |
| TPOT_ms p50 | 17.093 |
| cached/prompt | 37941248 / 39792804 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.118 |
| per_req_hit p50/p90 | 0.000 / 0.179 |
| TTFT_ms p50/p90 | 844.129 / 3291.090 |
| TPOT_ms p50 | 33.659 |
| cached/prompt | 62976 / 532640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 910 |
| token_weighted_hit | 0.965 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 587.031 / 1197.075 |
| TPOT_ms p50 | 16.461 |
| cached/prompt | 37878272 / 39260164 |

## Request

| metric | value |
|---|---|
| n | 1027 |
| token_weighted_hit | 0.310 |
| per_req_hit p50/p90 | 0.000 / 0.530 |
| TTFT_ms p50/p90 | 483.935 / 1926.696 |
| TPOT_ms p50 | 26.862 |
| cached/prompt | 233984 / 755968 |

## Request turn0

| metric | value |
|---|---|
| n | 539 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 394.642 / 1951.444 |
| TPOT_ms p50 | 29.134 |
| cached/prompt | 0 / 174496 |
