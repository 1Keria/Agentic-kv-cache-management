# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **447.469**
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
| TTFT_ms | 2277.596 | 4867.045 | 16471.498 | 2929.449 | 1261 |
| TPOT_ms | 285.613 | 807.330 | 1249.656 | 380.225 | 1261 |
| e2e_ms | 7597.735 | 18842.084 | 22779.753 | 9013.057 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.582 |
| per_req_hit p50/p90 | 0.000 / 0.872 |
| cold_miss_rate | 0.804 |
| cached/prompt | 5193728 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.009 / 1.890 |
| req/s | 2.818 |
| output tok/s | 45.089 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.624 |
| per_req_hit p50/p90 | 0.930 / 0.987 |
| TTFT_ms p50/p90 | 506.499 / 3973.585 |
| TPOT_ms p50 | 141.363 |
| cached/prompt | 5093120 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 696.659 / 747.540 |
| TPOT_ms p50 | 139.658 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.629 |
| per_req_hit p50/p90 | 0.934 / 0.987 |
| TTFT_ms p50/p90 | 496.204 / 3974.921 |
| TPOT_ms p50 | 141.758 |
| cached/prompt | 5076224 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.132 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2579.940 / 5313.453 |
| TPOT_ms p50 | 360.707 |
| cached/prompt | 100608 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2942.891 / 6644.941 |
| TPOT_ms p50 | 480.719 |
| cached/prompt | 0 / 174542 |
