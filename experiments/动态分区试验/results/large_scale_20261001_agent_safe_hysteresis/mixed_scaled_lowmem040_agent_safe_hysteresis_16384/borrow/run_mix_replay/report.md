# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **356.313**
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
| TTFT_ms | 710.810 | 3145.717 | 12344.776 | 1443.381 | 1261 |
| TPOT_ms | 171.991 | 472.614 | 921.478 | 238.924 | 1261 |
| e2e_ms | 3650.970 | 9122.028 | 20137.628 | 5266.166 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.861 |
| per_req_hit p50/p90 | 0.000 / 0.960 |
| cold_miss_rate | 0.704 |
| cached/prompt | 7678464 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.658 / 61.145 |
| req/s | 3.539 |
| output tok/s | 56.624 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.917 |
| per_req_hit p50/p90 | 0.969 / 0.991 |
| TTFT_ms p50/p90 | 474.862 / 2248.199 |
| TPOT_ms p50 | 128.405 |
| cached/prompt | 7477248 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 965.591 / 4377.117 |
| TPOT_ms p50 | 251.791 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.925 |
| per_req_hit p50/p90 | 0.970 / 0.992 |
| TTFT_ms p50/p90 | 472.867 / 2239.187 |
| TPOT_ms p50 | 127.846 |
| cached/prompt | 7471616 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.264 |
| per_req_hit p50/p90 | 0.000 / 0.500 |
| TTFT_ms p50/p90 | 778.093 / 3209.098 |
| TPOT_ms p50 | 179.601 |
| cached/prompt | 201216 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 961.894 / 3435.666 |
| TPOT_ms p50 | 238.261 |
| cached/prompt | 0 / 174542 |
