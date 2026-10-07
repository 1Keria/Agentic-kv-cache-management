# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **379.68**
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
| TTFT_ms | 518.391 | 2954.524 | 5710.126 | 1170.981 | 1261 |
| TPOT_ms | 322.542 | 794.248 | 1499.258 | 419.017 | 1261 |
| e2e_ms | 5958.257 | 15416.910 | 26924.374 | 7875.253 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.893 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.642 |
| cached/prompt | 7961088 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.909 / 1.875 |
| req/s | 3.321 |
| output tok/s | 53.139 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.937 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 466.568 / 808.459 |
| TPOT_ms p50 | 124.434 |
| cached/prompt | 7644416 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 706.756 / 1489.051 |
| TPOT_ms p50 | 117.508 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 464.272 / 792.635 |
| TPOT_ms p50 | 124.472 |
| cached/prompt | 7627520 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.416 |
| per_req_hit p50/p90 | 0.000 / 0.630 |
| TTFT_ms p50/p90 | 551.098 / 3241.584 |
| TPOT_ms p50 | 457.496 |
| cached/prompt | 316672 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 452.539 / 3756.483 |
| TPOT_ms p50 | 634.966 |
| cached/prompt | 0 / 174542 |
