# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_040`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **11413.488**
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
| TTFT_ms | 296.857 | 843.831 | 3143.443 | 465.935 | 2000 |
| TPOT_ms | 10.457 | 38.963 | 211.788 | 23.254 | 2000 |
| e2e_ms | 3567.023 | 13929.503 | 22849.697 | 5802.435 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.929 |
| per_req_hit p50/p90 | 0.000 / 0.992 |
| cold_miss_rate | 0.542 |
| cached/prompt | 34469888 / 37090706 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.863 / 1.997 |
| req/s | 0.175 |
| output tok/s | 62.790 |

## OpenHands

| metric | value |
|---|---|
| n | 800 |
| token_weighted_hit | 0.950 |
| per_req_hit p50/p90 | 0.982 / 0.995 |
| TTFT_ms p50/p90 | 334.238 / 710.641 |
| TPOT_ms p50 | 8.346 |
| cached/prompt | 34216704 / 36001441 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 28 |
| token_weighted_hit | 0.106 |
| per_req_hit p50/p90 | 0.138 / 0.413 |
| TTFT_ms p50/p90 | 2127.414 / 3669.479 |
| TPOT_ms p50 | 46.337 |
| cached/prompt | 53504 / 502400 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 772 |
| token_weighted_hit | 0.962 |
| per_req_hit p50/p90 | 0.983 / 0.995 |
| TTFT_ms p50/p90 | 330.209 / 613.241 |
| TPOT_ms p50 | 8.262 |
| cached/prompt | 34163200 / 35499041 |

## Request

| metric | value |
|---|---|
| n | 1200 |
| token_weighted_hit | 0.232 |
| per_req_hit p50/p90 | 0.000 / 0.373 |
| TTFT_ms p50/p90 | 278.397 / 1119.688 |
| TPOT_ms p50 | 15.651 |
| cached/prompt | 253184 / 1089265 |

## Request turn0

| metric | value |
|---|---|
| n | 601 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 333.856 / 2121.145 |
| TPOT_ms p50 | 26.933 |
| cached/prompt | 0 / 252557 |
