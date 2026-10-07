# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **343.56**
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
| TTFT_ms | 682.639 | 3025.512 | 5193.298 | 1094.758 | 1261 |
| TPOT_ms | 157.568 | 284.834 | 375.000 | 183.149 | 1261 |
| e2e_ms | 3511.039 | 6732.437 | 7762.335 | 4025.140 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.893 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.650 |
| cached/prompt | 7959296 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.653 / 10.029 |
| req/s | 3.670 |
| output tok/s | 58.726 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.940 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 462.864 / 2096.945 |
| TPOT_ms p50 | 125.349 |
| cached/prompt | 7669760 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.338 |
| TTFT_ms p50/p90 | 866.561 / 3890.825 |
| TPOT_ms p50 | 252.456 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.949 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 458.897 / 1896.955 |
| TPOT_ms p50 | 125.189 |
| cached/prompt | 7664128 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.380 |
| per_req_hit p50/p90 | 0.000 / 0.620 |
| TTFT_ms p50/p90 | 711.856 / 3160.085 |
| TPOT_ms p50 | 176.219 |
| cached/prompt | 289536 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 761.469 / 3370.635 |
| TPOT_ms p50 | 205.975 |
| cached/prompt | 0 / 174542 |
