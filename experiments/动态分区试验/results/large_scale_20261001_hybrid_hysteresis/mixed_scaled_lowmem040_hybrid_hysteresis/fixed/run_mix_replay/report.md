# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **359.038**
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
| TTFT_ms | 749.848 | 4551.974 | 9486.082 | 1608.909 | 1261 |
| TPOT_ms | 173.095 | 454.470 | 630.034 | 230.643 | 1261 |
| e2e_ms | 4114.524 | 10252.654 | 14964.651 | 5299.196 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.841 |
| per_req_hit p50/p90 | 0.000 / 0.963 |
| cold_miss_rate | 0.748 |
| cached/prompt | 7497728 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.629 / 1.189 |
| req/s | 3.512 |
| output tok/s | 56.195 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.902 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 469.146 / 2392.846 |
| TPOT_ms p50 | 127.849 |
| cached/prompt | 7356672 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 1025.761 / 3157.378 |
| TPOT_ms p50 | 309.060 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.910 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 466.283 / 2256.022 |
| TPOT_ms p50 | 126.204 |
| cached/prompt | 7351040 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.185 |
| per_req_hit p50/p90 | 0.000 / 0.351 |
| TTFT_ms p50/p90 | 803.808 / 4697.619 |
| TPOT_ms p50 | 180.854 |
| cached/prompt | 141056 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 931.030 / 5023.432 |
| TPOT_ms p50 | 225.340 |
| cached/prompt | 0 / 174542 |
