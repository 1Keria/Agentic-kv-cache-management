# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **381.08**
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
| TTFT_ms | 519.484 | 3782.140 | 8666.720 | 1482.917 | 1261 |
| TPOT_ms | 374.200 | 925.346 | 1261.730 | 474.446 | 1261 |
| e2e_ms | 8530.045 | 17824.598 | 26812.125 | 9074.045 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.876 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.763 |
| cached/prompt | 7815424 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.954 / 2.026 |
| req/s | 3.309 |
| output tok/s | 52.944 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.938 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 456.879 / 722.759 |
| TPOT_ms p50 | 127.441 |
| cached/prompt | 7646464 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 662.646 / 738.068 |
| TPOT_ms p50 | 136.701 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 452.234 / 684.090 |
| TPOT_ms p50 | 127.412 |
| cached/prompt | 7629568 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.222 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 587.908 / 4062.134 |
| TPOT_ms p50 | 589.197 |
| cached/prompt | 168960 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 488.403 / 4684.265 |
| TPOT_ms p50 | 741.990 |
| cached/prompt | 0 / 174542 |
