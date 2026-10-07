# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **385.965**
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
| TTFT_ms | 701.068 | 4509.909 | 8587.889 | 1687.428 | 1261 |
| TPOT_ms | 366.217 | 869.333 | 1915.587 | 479.259 | 1261 |
| e2e_ms | 7087.953 | 17986.145 | 32395.411 | 9355.564 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.857 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.774 |
| cached/prompt | 7641856 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.934 / 1.921 |
| req/s | 3.267 |
| output tok/s | 52.274 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.919 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 454.830 / 664.442 |
| TPOT_ms p50 | 129.281 |
| cached/prompt | 7498496 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 664.442 / 1488.445 |
| TPOT_ms p50 | 135.481 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.927 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 454.002 / 635.991 |
| TPOT_ms p50 | 129.251 |
| cached/prompt | 7481600 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.188 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1000.161 / 4706.367 |
| TPOT_ms p50 | 530.870 |
| cached/prompt | 143360 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1387.205 / 5559.462 |
| TPOT_ms p50 | 665.202 |
| cached/prompt | 0 / 174542 |
