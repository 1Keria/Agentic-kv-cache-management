# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **577.338**
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
| TTFT_ms | 10964.779 | 18711.918 | 21932.176 | 10972.036 | 1261 |
| TPOT_ms | 136.101 | 388.048 | 716.755 | 200.736 | 1261 |
| e2e_ms | 13789.040 | 23031.104 | 26196.406 | 14183.817 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.415 |
| per_req_hit p50/p90 | 0.000 / 0.100 |
| cold_miss_rate | 0.864 |
| cached/prompt | 3698432 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.960 / 1.902 |
| req/s | 2.184 |
| output tok/s | 34.947 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.453 |
| per_req_hit p50/p90 | 0.119 / 0.983 |
| TTFT_ms p50/p90 | 6016.447 / 10188.948 |
| TPOT_ms p50 | 132.846 |
| cached/prompt | 3691264 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.217 |
| TTFT_ms p50/p90 | 4724.098 / 6002.052 |
| TPOT_ms p50 | 134.593 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.456 |
| per_req_hit p50/p90 | 0.120 / 0.983 |
| TTFT_ms p50/p90 | 6213.019 / 10279.730 |
| TPOT_ms p50 | 129.471 |
| cached/prompt | 3682816 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.009 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11806.822 / 19151.278 |
| TPOT_ms p50 | 136.377 |
| cached/prompt | 7168 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13093.383 / 20196.350 |
| TPOT_ms p50 | 159.245 |
| cached/prompt | 0 / 174542 |
