# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_train_v4flash/agent_050`
- arrival: `frozen`
- request_gap_cap_s: 30.0
- wall_clock_s: **11055.343**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 2100 |
| n_ok | 2100 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 272.775 | 1265.589 | 5964.885 | 580.850 | 2100 |
| TPOT_ms | 9.925 | 40.606 | 116.672 | 19.701 | 2100 |
| e2e_ms | 3123.916 | 14095.229 | 29930.359 | 5783.861 | 2100 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.936 |
| per_req_hit p50/p90 | 0.661 / 0.991 |
| cold_miss_rate | 0.443 |
| cached/prompt | 41921024 / 44797936 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.770 / 2.080 |
| req/s | 0.190 |
| output tok/s | 66.309 |

## OpenHands

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.947 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 320.572 / 761.197 |
| TPOT_ms p50 | 8.415 |
| cached/prompt | 41718016 / 44036358 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 37 |
| token_weighted_hit | 0.164 |
| per_req_hit p50/p90 | 0.224 / 0.314 |
| TTFT_ms p50/p90 | 1835.632 / 3570.071 |
| TPOT_ms p50 | 95.774 |
| cached/prompt | 95744 / 582166 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 1013 |
| token_weighted_hit | 0.958 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 315.237 / 611.019 |
| TPOT_ms p50 | 8.300 |
| cached/prompt | 41622272 / 43454192 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.267 |
| per_req_hit p50/p90 | 0.000 / 0.450 |
| TTFT_ms p50/p90 | 171.965 / 1808.264 |
| TPOT_ms p50 | 17.845 |
| cached/prompt | 203008 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 174.101 / 3925.946 |
| TPOT_ms p50 | 29.549 |
| cached/prompt | 0 / 174542 |
