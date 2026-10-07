# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **386.365**
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
| TTFT_ms | 615.377 | 3166.318 | 5852.144 | 1336.001 | 1261 |
| TPOT_ms | 318.441 | 838.136 | 1303.704 | 441.286 | 1261 |
| e2e_ms | 7889.697 | 15120.748 | 26153.431 | 8396.577 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.860 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.768 |
| cached/prompt | 7669760 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.954 / 1.958 |
| req/s | 3.264 |
| output tok/s | 52.220 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.920 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 460.763 / 828.784 |
| TPOT_ms p50 | 130.662 |
| cached/prompt | 7503872 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 739.245 / 1511.823 |
| TPOT_ms p50 | 136.662 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.927 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 458.934 / 755.471 |
| TPOT_ms p50 | 130.576 |
| cached/prompt | 7486976 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.218 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 844.107 / 3332.441 |
| TPOT_ms p50 | 506.554 |
| cached/prompt | 165888 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 770.673 / 4185.244 |
| TPOT_ms p50 | 662.326 |
| cached/prompt | 0 / 174542 |
