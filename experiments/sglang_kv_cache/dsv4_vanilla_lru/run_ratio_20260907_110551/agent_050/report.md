# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_050`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **11034.467**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 2000 |
| n_ok | 2000 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 281.086 | 896.767 | 3683.214 | 489.036 | 2000 |
| TPOT_ms | 9.797 | 31.900 | 76.206 | 16.061 | 2000 |
| e2e_ms | 2953.834 | 12438.601 | 22194.876 | 5114.933 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.929 |
| per_req_hit p50/p90 | 0.579 / 0.993 |
| cold_miss_rate | 0.463 |
| cached/prompt | 43843840 / 47192939 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.769 / 2.739 |
| req/s | 0.181 |
| output tok/s | 63.311 |

## OpenHands

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.944 |
| per_req_hit p50/p90 | 0.982 / 0.995 |
| TTFT_ms p50/p90 | 329.915 / 769.459 |
| TPOT_ms p50 | 8.286 |
| cached/prompt | 43714048 / 46293549 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.126 |
| per_req_hit p50/p90 | 0.121 / 0.506 |
| TTFT_ms p50/p90 | 2561.524 / 3498.013 |
| TPOT_ms p50 | 39.362 |
| cached/prompt | 76032 / 604033 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 967 |
| token_weighted_hit | 0.955 |
| per_req_hit p50/p90 | 0.983 / 0.995 |
| TTFT_ms p50/p90 | 324.483 / 678.775 |
| TPOT_ms p50 | 8.204 |
| cached/prompt | 43638016 / 45689516 |

## Request

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.144 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 170.226 / 1438.034 |
| TPOT_ms p50 | 14.686 |
| cached/prompt | 129792 / 899390 |

## Request turn0

| metric | value |
|---|---|
| n | 500 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 174.450 / 2334.043 |
| TPOT_ms p50 | 24.804 |
| cached/prompt | 0 / 206573 |
