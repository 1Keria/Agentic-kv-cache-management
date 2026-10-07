# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **344.768**
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
| TTFT_ms | 749.223 | 3212.497 | 5036.346 | 1431.357 | 1261 |
| TPOT_ms | 142.962 | 262.544 | 323.890 | 167.260 | 1261 |
| e2e_ms | 3966.229 | 6300.656 | 7642.373 | 4107.517 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.905 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.636 |
| cached/prompt | 8066304 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.629 / 1.065 |
| req/s | 3.658 |
| output tok/s | 58.521 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.952 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 459.892 / 2235.165 |
| TPOT_ms p50 | 124.617 |
| cached/prompt | 7760896 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 1280.532 / 4169.657 |
| TPOT_ms p50 | 227.983 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.960 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 454.374 / 1902.669 |
| TPOT_ms p50 | 124.333 |
| cached/prompt | 7746816 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.401 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 929.476 / 3370.591 |
| TPOT_ms p50 | 147.665 |
| cached/prompt | 305408 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1975.692 / 4694.795 |
| TPOT_ms p50 | 167.793 |
| cached/prompt | 0 / 174542 |
