# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **346.178**
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
| TTFT_ms | 694.117 | 3252.027 | 4985.522 | 1293.157 | 1261 |
| TPOT_ms | 143.446 | 249.788 | 312.001 | 163.607 | 1261 |
| e2e_ms | 3448.797 | 6239.731 | 7596.835 | 3910.876 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.905 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.637 |
| cached/prompt | 8068096 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.662 / 1.111 |
| req/s | 3.643 |
| output tok/s | 58.282 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.951 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 443.253 / 2157.247 |
| TPOT_ms p50 | 126.056 |
| cached/prompt | 7752960 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 893.479 / 5198.335 |
| TPOT_ms p50 | 217.243 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.959 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 436.000 / 1873.007 |
| TPOT_ms p50 | 125.687 |
| cached/prompt | 7744512 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.414 |
| per_req_hit p50/p90 | 0.000 / 0.627 |
| TTFT_ms p50/p90 | 799.536 / 3434.155 |
| TPOT_ms p50 | 151.683 |
| cached/prompt | 315136 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1172.762 / 4611.291 |
| TPOT_ms p50 | 166.654 |
| cached/prompt | 0 / 174542 |
