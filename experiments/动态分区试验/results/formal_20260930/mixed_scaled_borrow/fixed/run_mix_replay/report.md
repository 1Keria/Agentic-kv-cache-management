# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **354.421**
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
| TTFT_ms | 632.932 | 2768.292 | 8309.629 | 1458.030 | 1261 |
| TPOT_ms | 182.949 | 283.436 | 414.412 | 194.528 | 1261 |
| e2e_ms | 3934.812 | 7337.043 | 10697.733 | 4570.483 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.880 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.664 |
| cached/prompt | 7844096 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.691 / 54.575 |
| req/s | 3.558 |
| output tok/s | 56.927 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.927 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 460.992 / 2190.653 |
| TPOT_ms p50 | 128.020 |
| cached/prompt | 7556864 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.211 |
| TTFT_ms p50/p90 | 865.735 / 8741.859 |
| TPOT_ms p50 | 258.116 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.936 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 454.749 / 2161.846 |
| TPOT_ms p50 | 127.747 |
| cached/prompt | 7554048 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.377 |
| per_req_hit p50/p90 | 0.000 / 0.613 |
| TTFT_ms p50/p90 | 696.946 / 4293.593 |
| TPOT_ms p50 | 194.428 |
| cached/prompt | 287232 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 732.196 / 7581.075 |
| TPOT_ms p50 | 217.305 |
| cached/prompt | 0 / 174542 |
