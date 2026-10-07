# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **352.465**
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
| TTFT_ms | 715.963 | 3879.911 | 7388.446 | 1762.904 | 1261 |
| TPOT_ms | 179.119 | 460.620 | 976.288 | 259.987 | 1261 |
| e2e_ms | 3774.281 | 12163.545 | 18227.752 | 5922.692 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.862 |
| per_req_hit p50/p90 | 0.000 / 0.956 |
| cold_miss_rate | 0.710 |
| cached/prompt | 7683584 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.626 / 1.066 |
| req/s | 3.578 |
| output tok/s | 57.243 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.918 |
| per_req_hit p50/p90 | 0.969 / 0.991 |
| TTFT_ms p50/p90 | 475.115 / 2209.203 |
| TPOT_ms p50 | 132.074 |
| cached/prompt | 7488512 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.225 |
| TTFT_ms p50/p90 | 2442.108 / 3631.112 |
| TPOT_ms p50 | 320.386 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.927 |
| per_req_hit p50/p90 | 0.969 / 0.991 |
| TTFT_ms p50/p90 | 473.813 / 1486.945 |
| TPOT_ms p50 | 131.178 |
| cached/prompt | 7482880 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.256 |
| per_req_hit p50/p90 | 0.000 / 0.497 |
| TTFT_ms p50/p90 | 817.974 / 4761.655 |
| TPOT_ms p50 | 193.368 |
| cached/prompt | 195072 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2619.361 / 6317.119 |
| TPOT_ms p50 | 296.936 |
| cached/prompt | 0 / 174542 |
