# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **379.313**
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
| TTFT_ms | 500.274 | 4118.174 | 7276.202 | 1396.608 | 1261 |
| TPOT_ms | 328.350 | 802.446 | 1602.884 | 438.109 | 1261 |
| e2e_ms | 7287.362 | 15832.919 | 30992.041 | 8406.357 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.901 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.651 |
| cached/prompt | 8038400 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.957 / 1.956 |
| req/s | 3.324 |
| output tok/s | 53.191 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.949 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 458.515 / 670.823 |
| TPOT_ms p50 | 133.484 |
| cached/prompt | 7742720 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 685.064 / 920.701 |
| TPOT_ms p50 | 137.514 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.957 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 457.220 / 628.100 |
| TPOT_ms p50 | 133.409 |
| cached/prompt | 7725824 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.388 |
| per_req_hit p50/p90 | 0.000 / 0.625 |
| TTFT_ms p50/p90 | 549.220 / 4407.814 |
| TPOT_ms p50 | 453.110 |
| cached/prompt | 295680 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 420.680 / 5364.086 |
| TPOT_ms p50 | 630.500 |
| cached/prompt | 0 / 174542 |
