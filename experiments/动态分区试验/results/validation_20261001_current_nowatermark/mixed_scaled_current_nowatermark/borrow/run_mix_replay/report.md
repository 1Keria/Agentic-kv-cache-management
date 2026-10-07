# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **348.167**
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
| TTFT_ms | 621.674 | 3323.964 | 5034.404 | 1249.605 | 1261 |
| TPOT_ms | 143.147 | 242.893 | 346.181 | 164.593 | 1261 |
| e2e_ms | 3174.544 | 6989.460 | 8126.341 | 3883.092 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.904 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.641 |
| cached/prompt | 8059648 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.627 / 1.058 |
| req/s | 3.622 |
| output tok/s | 57.949 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.952 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 455.333 / 2715.509 |
| TPOT_ms p50 | 128.084 |
| cached/prompt | 7760896 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 1133.398 / 5246.905 |
| TPOT_ms p50 | 224.932 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.960 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 452.666 / 2287.901 |
| TPOT_ms p50 | 127.243 |
| cached/prompt | 7746816 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.392 |
| per_req_hit p50/p90 | 0.000 / 0.621 |
| TTFT_ms p50/p90 | 675.817 / 3459.420 |
| TPOT_ms p50 | 145.310 |
| cached/prompt | 298752 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 715.472 / 4614.805 |
| TPOT_ms p50 | 188.858 |
| cached/prompt | 0 / 174542 |
