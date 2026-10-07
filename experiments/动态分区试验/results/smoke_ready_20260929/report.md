# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/smoke`
- arrival: `frozen`
- request_gap_cap_s: 0.0
- wall_clock_s: **14.197**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 8 |
| n_ok | 8 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 6943.192 | 12841.280 | 13009.979 | 7106.823 | 8 |
| TPOT_ms | 168.049 | 414.184 | 549.934 | 225.515 | 8 |
| e2e_ms | 7947.473 | 13849.425 | 14161.565 | 8008.883 | 8 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.132 |
| per_req_hit p50/p90 | 0.000 / 0.225 |
| cold_miss_rate | 0.750 |
| cached/prompt | 5632 / 42651 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 2.233 / 496.594 |
| req/s | 0.564 |
| output tok/s | 2.254 |

## OpenHands

| metric | value |
|---|---|
| n | 4 |
| token_weighted_hit | 0.132 |
| per_req_hit p50/p90 | 0.112 / 0.226 |
| TTFT_ms p50/p90 | 12530.741 / 12948.391 |
| TPOT_ms p50 | 292.055 |
| cached/prompt | 5632 / 42628 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 4 |
| token_weighted_hit | 0.132 |
| per_req_hit p50/p90 | 0.112 / 0.226 |
| TTFT_ms p50/p90 | 12530.741 / 12948.391 |
| TPOT_ms p50 | 292.055 |
| cached/prompt | 5632 / 42628 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 0 |
| token_weighted_hit | — |
| per_req_hit p50/p90 | — / — |
| TTFT_ms p50/p90 | — / — |
| TPOT_ms p50 | — |
| cached/prompt | 0 / 0 |

## Request

| metric | value |
|---|---|
| n | 4 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1677.041 / 1914.144 |
| TPOT_ms p50 | 129.434 |
| cached/prompt | 0 / 23 |

## Request turn0

| metric | value |
|---|---|
| n | 4 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1677.041 / 1914.144 |
| TPOT_ms p50 | 129.434 |
| cached/prompt | 0 / 23 |
