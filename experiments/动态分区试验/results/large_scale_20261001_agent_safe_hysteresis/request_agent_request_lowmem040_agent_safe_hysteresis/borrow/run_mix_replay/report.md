# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **386.683**
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
| TTFT_ms | 746.981 | 5119.055 | 10482.287 | 2080.062 | 1261 |
| TPOT_ms | 339.368 | 615.031 | 961.204 | 349.947 | 1261 |
| e2e_ms | 7074.207 | 14218.486 | 19065.801 | 7679.210 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.799 |
| cached/prompt | 7622912 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.961 / 1.896 |
| req/s | 3.261 |
| output tok/s | 52.177 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.924 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 432.452 / 706.072 |
| TPOT_ms p50 | 129.619 |
| cached/prompt | 7538176 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 655.277 / 1641.633 |
| TPOT_ms p50 | 132.013 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.932 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 431.133 / 644.837 |
| TPOT_ms p50 | 129.478 |
| cached/prompt | 7521280 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.111 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1375.025 / 5432.735 |
| TPOT_ms p50 | 369.904 |
| cached/prompt | 84736 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2203.403 / 5829.543 |
| TPOT_ms p50 | 452.204 |
| cached/prompt | 0 / 174542 |
