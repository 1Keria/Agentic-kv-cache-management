# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **356.4**
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
| TTFT_ms | 808.831 | 4906.834 | 13278.525 | 1867.390 | 1261 |
| TPOT_ms | 168.602 | 384.630 | 598.909 | 221.134 | 1261 |
| e2e_ms | 4080.494 | 10915.702 | 20664.532 | 5405.540 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.000 / 0.959 |
| cold_miss_rate | 0.707 |
| cached/prompt | 7658240 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.635 / 1.065 |
| req/s | 3.538 |
| output tok/s | 56.611 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.914 |
| per_req_hit p50/p90 | 0.969 / 0.991 |
| TTFT_ms p50/p90 | 478.888 / 2298.443 |
| TPOT_ms p50 | 128.730 |
| cached/prompt | 7457024 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.217 |
| TTFT_ms p50/p90 | 1898.584 / 6287.342 |
| TPOT_ms p50 | 361.802 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.923 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 477.577 / 2261.490 |
| TPOT_ms p50 | 127.792 |
| cached/prompt | 7451392 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.264 |
| per_req_hit p50/p90 | 0.000 / 0.486 |
| TTFT_ms p50/p90 | 934.275 / 5632.063 |
| TPOT_ms p50 | 179.634 |
| cached/prompt | 201216 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1638.562 / 6339.546 |
| TPOT_ms p50 | 255.021 |
| cached/prompt | 0 / 174542 |
