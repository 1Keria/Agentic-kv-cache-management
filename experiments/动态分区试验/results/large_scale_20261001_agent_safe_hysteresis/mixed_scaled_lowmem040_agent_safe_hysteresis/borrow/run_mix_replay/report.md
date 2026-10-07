# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **354.848**
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
| TTFT_ms | 719.509 | 4659.516 | 8675.987 | 1808.594 | 1261 |
| TPOT_ms | 186.083 | 504.599 | 795.343 | 257.177 | 1261 |
| e2e_ms | 4069.301 | 13925.390 | 18004.690 | 5923.432 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.860 |
| per_req_hit p50/p90 | 0.000 / 0.963 |
| cold_miss_rate | 0.724 |
| cached/prompt | 7669248 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.617 / 1.057 |
| req/s | 3.554 |
| output tok/s | 56.858 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.919 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 474.483 / 2119.297 |
| TPOT_ms p50 | 124.977 |
| cached/prompt | 7495424 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 892.270 / 5407.836 |
| TPOT_ms p50 | 281.701 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.928 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 471.895 / 1555.222 |
| TPOT_ms p50 | 123.781 |
| cached/prompt | 7489792 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.228 |
| per_req_hit p50/p90 | 0.000 / 0.429 |
| TTFT_ms p50/p90 | 793.332 / 4867.317 |
| TPOT_ms p50 | 211.541 |
| cached/prompt | 173824 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2325.609 / 6417.770 |
| TPOT_ms p50 | 281.669 |
| cached/prompt | 0 / 174542 |
