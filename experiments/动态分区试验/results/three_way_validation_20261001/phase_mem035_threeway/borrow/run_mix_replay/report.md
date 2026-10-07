# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **540.338**
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
| TTFT_ms | 12223.413 | 18000.571 | 20033.536 | 11360.700 | 1261 |
| TPOT_ms | 146.467 | 404.709 | 641.589 | 210.870 | 1261 |
| e2e_ms | 15756.704 | 21674.191 | 23466.601 | 14734.624 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.506 |
| per_req_hit p50/p90 | 0.000 / 0.099 |
| cold_miss_rate | 0.896 |
| cached/prompt | 4512000 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.946 / 1.969 |
| req/s | 2.334 |
| output tok/s | 37.340 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.553 |
| per_req_hit p50/p90 | 0.173 / 0.987 |
| TTFT_ms p50/p90 | 4844.641 / 10682.154 |
| TPOT_ms p50 | 136.625 |
| cached/prompt | 4512000 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.225 |
| TTFT_ms p50/p90 | 6305.658 / 8829.579 |
| TPOT_ms p50 | 142.485 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.558 |
| per_req_hit p50/p90 | 0.173 / 0.987 |
| TTFT_ms p50/p90 | 4294.095 / 10859.267 |
| TPOT_ms p50 | 136.428 |
| cached/prompt | 4503552 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 12969.684 / 18157.371 |
| TPOT_ms p50 | 148.954 |
| cached/prompt | 0 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 14420.480 / 18542.180 |
| TPOT_ms p50 | 149.697 |
| cached/prompt | 0 / 174542 |
