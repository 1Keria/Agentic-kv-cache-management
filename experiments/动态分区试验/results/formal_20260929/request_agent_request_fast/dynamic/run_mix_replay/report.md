# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **381.169**
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
| TTFT_ms | 515.483 | 4027.263 | 10299.387 | 1483.013 | 1261 |
| TPOT_ms | 330.629 | 1132.000 | 1801.736 | 478.295 | 1261 |
| e2e_ms | 7030.223 | 20693.435 | 34248.358 | 9135.737 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.888 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.680 |
| cached/prompt | 7918336 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.993 / 1.914 |
| req/s | 3.308 |
| output tok/s | 52.932 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.938 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 466.308 / 727.920 |
| TPOT_ms p50 | 126.444 |
| cached/prompt | 7646208 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.137 |
| per_req_hit p50/p90 | 0.211 / 0.346 |
| TTFT_ms p50/p90 | 688.990 / 2057.653 |
| TPOT_ms p50 | 134.113 |
| cached/prompt | 11264 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.946 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 464.586 / 703.086 |
| TPOT_ms p50 | 126.400 |
| cached/prompt | 7634944 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.357 |
| per_req_hit p50/p90 | 0.000 / 0.624 |
| TTFT_ms p50/p90 | 624.082 / 4574.162 |
| TPOT_ms p50 | 430.418 |
| cached/prompt | 272128 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 929.646 / 6218.226 |
| TPOT_ms p50 | 683.005 |
| cached/prompt | 0 / 174542 |
