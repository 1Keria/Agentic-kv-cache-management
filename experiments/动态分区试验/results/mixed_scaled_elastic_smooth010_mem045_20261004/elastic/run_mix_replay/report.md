# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **345.726**
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
| TTFT_ms | 598.525 | 2924.652 | 8068.498 | 1498.958 | 1261 |
| TPOT_ms | 148.748 | 285.019 | 434.933 | 178.483 | 1261 |
| e2e_ms | 3241.104 | 7891.786 | 10676.531 | 4354.687 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.634 |
| cached/prompt | 8079616 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.663 / 1.066 |
| req/s | 3.647 |
| output tok/s | 58.358 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.952 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 451.106 / 1383.593 |
| TPOT_ms p50 | 126.245 |
| cached/prompt | 7761152 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 891.913 / 7204.642 |
| TPOT_ms p50 | 227.845 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.960 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 447.566 / 1086.290 |
| TPOT_ms p50 | 125.949 |
| cached/prompt | 7747072 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.418 |
| per_req_hit p50/p90 | 0.000 / 0.628 |
| TTFT_ms p50/p90 | 685.432 / 3069.933 |
| TPOT_ms p50 | 156.390 |
| cached/prompt | 318464 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 808.324 / 7797.950 |
| TPOT_ms p50 | 185.783 |
| cached/prompt | 0 / 174542 |
