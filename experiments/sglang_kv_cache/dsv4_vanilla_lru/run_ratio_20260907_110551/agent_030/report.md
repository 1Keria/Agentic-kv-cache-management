# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_030`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **12867.855**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 2000 |
| n_ok | 2000 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 315.518 | 785.258 | 3635.589 | 481.103 | 2000 |
| TPOT_ms | 11.828 | 48.335 | 420.847 | 33.168 | 2000 |
| e2e_ms | 4322.128 | 14594.463 | 22506.378 | 6326.684 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.921 |
| per_req_hit p50/p90 | 0.000 / 0.989 |
| cold_miss_rate | 0.585 |
| cached/prompt | 25395200 / 27573039 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.702 / 1.392 |
| req/s | 0.155 |
| output tok/s | 55.421 |

## OpenHands

| metric | value |
|---|---|
| n | 600 |
| token_weighted_hit | 0.951 |
| per_req_hit p50/p90 | 0.981 / 0.995 |
| TTFT_ms p50/p90 | 329.886 / 697.078 |
| TPOT_ms p50 | 8.181 |
| cached/prompt | 24993024 / 26289570 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 21 |
| token_weighted_hit | 0.074 |
| per_req_hit p50/p90 | 0.000 / 0.174 |
| TTFT_ms p50/p90 | 1892.462 / 3742.812 |
| TPOT_ms p50 | 50.179 |
| cached/prompt | 28160 / 378895 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 579 |
| token_weighted_hit | 0.963 |
| per_req_hit p50/p90 | 0.982 / 0.995 |
| TTFT_ms p50/p90 | 325.522 / 630.358 |
| TPOT_ms p50 | 8.072 |
| cached/prompt | 24964864 / 25910675 |

## Request

| metric | value |
|---|---|
| n | 1400 |
| token_weighted_hit | 0.313 |
| per_req_hit p50/p90 | 0.000 / 0.601 |
| TTFT_ms p50/p90 | 306.993 / 955.142 |
| TPOT_ms p50 | 16.239 |
| cached/prompt | 402176 / 1283469 |

## Request turn0

| metric | value |
|---|---|
| n | 711 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 379.939 / 1815.113 |
| TPOT_ms p50 | 28.425 |
| cached/prompt | 0 / 312109 |
