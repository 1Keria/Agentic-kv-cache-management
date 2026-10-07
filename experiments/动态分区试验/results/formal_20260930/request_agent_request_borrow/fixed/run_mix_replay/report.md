# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **383.628**
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
| TTFT_ms | 644.579 | 4139.449 | 9455.745 | 1712.726 | 1261 |
| TPOT_ms | 338.662 | 987.724 | 1966.731 | 489.411 | 1261 |
| e2e_ms | 7744.354 | 19419.700 | 33235.547 | 9543.297 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.846 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.769 |
| cached/prompt | 7547904 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.013 / 1.996 |
| req/s | 3.287 |
| output tok/s | 52.593 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.970 / 0.990 |
| TTFT_ms p50/p90 | 460.202 / 746.201 |
| TPOT_ms p50 | 127.295 |
| cached/prompt | 7386368 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 734.509 / 780.039 |
| TPOT_ms p50 | 137.775 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.913 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 458.263 / 711.797 |
| TPOT_ms p50 | 127.132 |
| cached/prompt | 7369472 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.212 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 999.674 / 4340.435 |
| TPOT_ms p50 | 554.810 |
| cached/prompt | 161536 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1284.075 / 5856.590 |
| TPOT_ms p50 | 706.764 |
| cached/prompt | 0 / 174542 |
