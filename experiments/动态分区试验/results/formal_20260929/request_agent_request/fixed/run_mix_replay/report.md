# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.873**
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
| TTFT_ms | 614.979 | 3935.555 | 8075.173 | 1447.493 | 1261 |
| TPOT_ms | 329.067 | 857.884 | 1498.521 | 452.819 | 1261 |
| e2e_ms | 7534.860 | 16163.902 | 28209.200 | 8692.591 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.871 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.787 |
| cached/prompt | 7770624 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.100 / 2.045 |
| req/s | 3.311 |
| output tok/s | 52.973 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.938 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 462.257 / 700.959 |
| TPOT_ms p50 | 127.528 |
| cached/prompt | 7651072 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 704.448 / 2214.983 |
| TPOT_ms p50 | 144.600 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.946 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 460.060 / 661.792 |
| TPOT_ms p50 | 127.389 |
| cached/prompt | 7634176 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.157 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 834.148 / 4233.551 |
| TPOT_ms p50 | 455.464 |
| cached/prompt | 119552 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1067.081 / 5149.151 |
| TPOT_ms p50 | 667.242 |
| cached/prompt | 0 / 174542 |
