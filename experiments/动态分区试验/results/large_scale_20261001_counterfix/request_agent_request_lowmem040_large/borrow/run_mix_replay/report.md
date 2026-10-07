# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.614**
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
| TTFT_ms | 1853.746 | 5338.954 | 8009.253 | 2386.569 | 1261 |
| TPOT_ms | 232.695 | 577.052 | 959.088 | 315.918 | 1261 |
| e2e_ms | 7862.363 | 12789.134 | 18464.521 | 7441.255 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.853 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.737 |
| cached/prompt | 7607808 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.896 / 1.861 |
| req/s | 3.313 |
| output tok/s | 53.009 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.910 |
| per_req_hit p50/p90 | 0.970 / 0.990 |
| TTFT_ms p50/p90 | 478.869 / 813.335 |
| TPOT_ms p50 | 127.437 |
| cached/prompt | 7422464 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 710.027 / 1756.039 |
| TPOT_ms p50 | 125.049 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.917 |
| per_req_hit p50/p90 | 0.971 / 0.990 |
| TTFT_ms p50/p90 | 477.993 / 787.741 |
| TPOT_ms p50 | 127.661 |
| cached/prompt | 7405568 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.243 |
| per_req_hit p50/p90 | 0.000 / 0.428 |
| TTFT_ms p50/p90 | 2323.490 / 5547.842 |
| TPOT_ms p50 | 320.165 |
| cached/prompt | 185344 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3128.731 / 5719.127 |
| TPOT_ms p50 | 488.602 |
| cached/prompt | 0 / 174542 |
