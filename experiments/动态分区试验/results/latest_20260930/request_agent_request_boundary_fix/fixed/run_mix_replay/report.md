# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **384.907**
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
| TTFT_ms | 628.201 | 3529.447 | 6358.429 | 1467.846 | 1261 |
| TPOT_ms | 296.297 | 930.539 | 1474.347 | 455.168 | 1261 |
| e2e_ms | 7659.863 | 15984.249 | 29012.019 | 8750.537 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.862 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.776 |
| cached/prompt | 7687424 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.957 / 1.893 |
| req/s | 3.276 |
| output tok/s | 52.418 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.924 |
| per_req_hit p50/p90 | 0.970 / 0.990 |
| TTFT_ms p50/p90 | 462.628 / 798.982 |
| TPOT_ms p50 | 124.250 |
| cached/prompt | 7536128 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 728.997 / 1529.409 |
| TPOT_ms p50 | 117.815 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.931 |
| per_req_hit p50/p90 | 0.971 / 0.990 |
| TTFT_ms p50/p90 | 457.622 / 735.730 |
| TPOT_ms p50 | 124.319 |
| cached/prompt | 7519232 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.199 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 973.122 / 3932.950 |
| TPOT_ms p50 | 476.249 |
| cached/prompt | 151296 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 785.580 / 4482.226 |
| TPOT_ms p50 | 723.460 |
| cached/prompt | 0 / 174542 |
