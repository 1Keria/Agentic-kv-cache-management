# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **352.5**
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
| TTFT_ms | 928.351 | 4868.179 | 10462.528 | 1948.731 | 1261 |
| TPOT_ms | 153.682 | 488.406 | 600.053 | 219.549 | 1261 |
| e2e_ms | 3780.597 | 11774.667 | 18856.109 | 5461.509 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.856 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.765 |
| cached/prompt | 7629056 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.603 / 1.054 |
| req/s | 3.577 |
| output tok/s | 57.237 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.922 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 487.492 / 2206.446 |
| TPOT_ms p50 | 129.175 |
| cached/prompt | 7519488 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 1007.131 / 3549.405 |
| TPOT_ms p50 | 447.098 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.931 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 484.542 / 2132.100 |
| TPOT_ms p50 | 127.752 |
| cached/prompt | 7513856 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.144 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1247.897 / 5164.132 |
| TPOT_ms p50 | 160.978 |
| cached/prompt | 109568 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2855.914 / 7157.585 |
| TPOT_ms p50 | 219.950 |
| cached/prompt | 0 / 174542 |
