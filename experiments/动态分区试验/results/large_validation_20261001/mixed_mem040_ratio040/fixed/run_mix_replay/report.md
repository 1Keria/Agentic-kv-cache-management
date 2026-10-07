# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **405.663**
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
| TTFT_ms | 740.796 | 3619.520 | 7137.391 | 1633.712 | 1261 |
| TPOT_ms | 183.190 | 443.801 | 731.170 | 252.468 | 1261 |
| e2e_ms | 4717.646 | 11908.189 | 14567.024 | 5673.202 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.745 |
| per_req_hit p50/p90 | 0.000 / 0.947 |
| cold_miss_rate | 0.688 |
| cached/prompt | 6644480 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.653 / 18.517 |
| req/s | 3.108 |
| output tok/s | 49.736 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.781 |
| per_req_hit p50/p90 | 0.964 / 0.989 |
| TTFT_ms p50/p90 | 487.845 / 3782.364 |
| TPOT_ms p50 | 129.256 |
| cached/prompt | 6372864 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 966.703 / 4253.146 |
| TPOT_ms p50 | 314.530 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.789 |
| per_req_hit p50/p90 | 0.965 / 0.989 |
| TTFT_ms p50/p90 | 486.523 / 3674.830 |
| TPOT_ms p50 | 127.731 |
| cached/prompt | 6367232 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.357 |
| per_req_hit p50/p90 | 0.000 / 0.608 |
| TTFT_ms p50/p90 | 816.510 / 3600.660 |
| TPOT_ms p50 | 219.553 |
| cached/prompt | 271616 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 947.697 / 5375.948 |
| TPOT_ms p50 | 247.306 |
| cached/prompt | 0 / 174542 |
