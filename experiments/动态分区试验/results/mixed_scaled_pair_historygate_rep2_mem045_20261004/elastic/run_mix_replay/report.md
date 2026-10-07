# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **348.2**
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
| TTFT_ms | 573.227 | 2864.013 | 8000.985 | 1214.340 | 1261 |
| TPOT_ms | 149.029 | 343.318 | 686.742 | 206.959 | 1261 |
| e2e_ms | 3150.562 | 10435.402 | 11600.881 | 4525.683 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.904 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.635 |
| cached/prompt | 8064768 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.679 / 20.912 |
| req/s | 3.622 |
| output tok/s | 57.944 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.951 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 462.696 / 1307.571 |
| TPOT_ms p50 | 126.689 |
| cached/prompt | 7757312 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 837.733 / 6646.179 |
| TPOT_ms p50 | 253.618 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.959 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 457.990 / 1081.832 |
| TPOT_ms p50 | 126.507 |
| cached/prompt | 7740416 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.404 |
| per_req_hit p50/p90 | 0.000 / 0.621 |
| TTFT_ms p50/p90 | 627.029 / 3029.923 |
| TPOT_ms p50 | 155.990 |
| cached/prompt | 307456 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 670.337 / 6191.845 |
| TPOT_ms p50 | 210.322 |
| cached/prompt | 0 / 174542 |
