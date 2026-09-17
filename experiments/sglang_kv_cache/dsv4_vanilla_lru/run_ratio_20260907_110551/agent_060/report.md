# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_060`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **11385.448**
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
| TTFT_ms | 296.035 | 891.541 | 3860.894 | 499.773 | 2000 |
| TPOT_ms | 9.271 | 25.973 | 47.725 | 13.445 | 2000 |
| e2e_ms | 2532.386 | 10943.091 | 20999.513 | 4515.461 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.924 |
| per_req_hit p50/p90 | 0.913 / 0.994 |
| cold_miss_rate | 0.379 |
| cached/prompt | 52134400 / 56434574 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.786 / 2.722 |
| req/s | 0.176 |
| output tok/s | 58.209 |

## OpenHands

| metric | value |
|---|---|
| n | 1200 |
| token_weighted_hit | 0.932 |
| per_req_hit p50/p90 | 0.981 / 0.995 |
| TTFT_ms p50/p90 | 334.453 / 704.817 |
| TPOT_ms p50 | 8.255 |
| cached/prompt | 52009984 / 55775070 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.140 |
| per_req_hit p50/p90 | 0.153 / 0.522 |
| TTFT_ms p50/p90 | 2303.650 / 4023.122 |
| TPOT_ms p50 | 37.021 |
| cached/prompt | 98560 / 705133 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 1161 |
| token_weighted_hit | 0.943 |
| per_req_hit p50/p90 | 0.982 / 0.995 |
| TTFT_ms p50/p90 | 329.288 / 605.433 |
| TPOT_ms p50 | 8.177 |
| cached/prompt | 51911424 / 55069937 |

## Request

| metric | value |
|---|---|
| n | 800 |
| token_weighted_hit | 0.189 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 169.685 / 1497.950 |
| TPOT_ms p50 | 14.055 |
| cached/prompt | 124416 / 659504 |

## Request turn0

| metric | value |
|---|---|
| n | 399 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 173.372 / 2511.501 |
| TPOT_ms p50 | 23.090 |
| cached/prompt | 0 / 156131 |
