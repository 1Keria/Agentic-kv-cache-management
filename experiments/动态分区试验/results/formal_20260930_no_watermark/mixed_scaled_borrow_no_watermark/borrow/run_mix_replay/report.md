# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **354.987**
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
| TTFT_ms | 636.595 | 3272.656 | 5750.994 | 1264.189 | 1261 |
| TPOT_ms | 156.510 | 296.371 | 477.527 | 186.142 | 1261 |
| e2e_ms | 3737.173 | 7771.461 | 8325.314 | 4242.463 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.893 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.653 |
| cached/prompt | 7962880 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.717 / 603.038 |
| req/s | 3.552 |
| output tok/s | 56.836 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.942 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 482.844 / 2395.424 |
| TPOT_ms p50 | 125.366 |
| cached/prompt | 7684096 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 875.918 / 5449.079 |
| TPOT_ms p50 | 241.038 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.951 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 479.530 / 2339.065 |
| TPOT_ms p50 | 125.097 |
| cached/prompt | 7675648 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.366 |
| per_req_hit p50/p90 | 0.000 / 0.610 |
| TTFT_ms p50/p90 | 716.138 / 3308.203 |
| TPOT_ms p50 | 169.231 |
| cached/prompt | 278784 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 652.944 / 3511.173 |
| TPOT_ms p50 | 209.765 |
| cached/prompt | 0 / 174542 |
