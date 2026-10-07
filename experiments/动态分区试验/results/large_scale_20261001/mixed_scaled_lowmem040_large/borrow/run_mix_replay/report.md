# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **357.613**
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
| TTFT_ms | 774.934 | 4112.181 | 12444.159 | 1690.160 | 1261 |
| TPOT_ms | 160.353 | 487.393 | 939.186 | 242.399 | 1261 |
| e2e_ms | 3612.207 | 12276.176 | 17878.493 | 5568.542 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.860 |
| per_req_hit p50/p90 | 0.000 / 0.963 |
| cold_miss_rate | 0.700 |
| cached/prompt | 7667200 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.643 / 1.116 |
| req/s | 3.526 |
| output tok/s | 56.419 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.914 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 468.049 / 2296.301 |
| TPOT_ms p50 | 127.265 |
| cached/prompt | 7456256 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.090 |
| TTFT_ms p50/p90 | 1561.495 / 3447.416 |
| TPOT_ms p50 | 383.652 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.923 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 463.831 / 2154.475 |
| TPOT_ms p50 | 126.124 |
| cached/prompt | 7453440 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.277 |
| per_req_hit p50/p90 | 0.000 / 0.497 |
| TTFT_ms p50/p90 | 957.023 / 4210.480 |
| TPOT_ms p50 | 166.908 |
| cached/prompt | 210944 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1350.055 / 6252.728 |
| TPOT_ms p50 | 209.207 |
| cached/prompt | 0 / 174542 |
