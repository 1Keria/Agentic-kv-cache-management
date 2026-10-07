# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **635.461**
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
| TTFT_ms | 10542.743 | 18211.958 | 23075.543 | 10776.146 | 1261 |
| TPOT_ms | 142.879 | 361.671 | 719.872 | 202.953 | 1261 |
| e2e_ms | 13681.138 | 21916.445 | 26611.459 | 14023.394 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.277 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.964 |
| cached/prompt | 2471424 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.974 / 1.905 |
| req/s | 1.984 |
| output tok/s | 31.750 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.303 |
| per_req_hit p50/p90 | 0.000 / 0.974 |
| TTFT_ms p50/p90 | 6619.616 / 10557.176 |
| TPOT_ms p50 | 151.603 |
| cached/prompt | 2469376 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.217 |
| TTFT_ms p50/p90 | 6416.080 / 8843.229 |
| TPOT_ms p50 | 132.638 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.305 |
| per_req_hit p50/p90 | 0.000 / 0.975 |
| TTFT_ms p50/p90 | 6666.454 / 10561.006 |
| TPOT_ms p50 | 152.548 |
| cached/prompt | 2463744 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.003 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11067.548 / 19298.523 |
| TPOT_ms p50 | 142.690 |
| cached/prompt | 2048 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 12447.927 / 20394.863 |
| TPOT_ms p50 | 160.710 |
| cached/prompt | 0 / 174542 |
