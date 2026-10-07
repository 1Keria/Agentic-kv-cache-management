# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **72.137**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 256 |
| n_ok | 256 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 3228.544 | 7380.569 | 8094.602 | 3255.532 | 256 |
| TPOT_ms | 252.228 | 394.460 | 551.311 | 230.099 | 256 |
| e2e_ms | 7442.465 | 13830.701 | 16915.607 | 6937.114 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.797 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.652 |
| cached/prompt | 744192 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 413.944 / 499.296 |
| req/s | 3.549 |
| output tok/s | 56.781 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.871 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2083.827 / 3216.214 |
| TPOT_ms p50 | 119.995 |
| cached/prompt | 685568 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 7429.265 / 7991.008 |
| TPOT_ms p50 | 402.989 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 1065.354 / 3039.328 |
| TPOT_ms p50 | 118.858 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.399 |
| per_req_hit p50/p90 | 0.000 / 0.646 |
| TTFT_ms p50/p90 | 3305.412 / 7382.858 |
| TPOT_ms p50 | 252.275 |
| cached/prompt | 58624 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3636.957 / 7524.637 |
| TPOT_ms p50 | 264.338 |
| cached/prompt | 0 / 30741 |
