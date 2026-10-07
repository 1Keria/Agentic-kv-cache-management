# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **78.737**
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
| TTFT_ms | 3690.044 | 8210.764 | 11555.180 | 3915.123 | 256 |
| TPOT_ms | 147.076 | 408.901 | 418.603 | 223.049 | 256 |
| e2e_ms | 6208.383 | 14307.458 | 14345.102 | 7483.913 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.781 |
| per_req_hit p50/p90 | 0.000 / 0.899 |
| cold_miss_rate | 0.656 |
| cached/prompt | 729344 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 400.537 / 485.963 |
| req/s | 3.251 |
| output tok/s | 52.021 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2294.483 / 4777.088 |
| TPOT_ms p50 | 132.828 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 8246.517 / 10911.786 |
| TPOT_ms p50 | 398.200 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.886 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2219.819 / 4244.816 |
| TPOT_ms p50 | 130.923 |
| cached/prompt | 670464 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.363 |
| per_req_hit p50/p90 | 0.000 / 0.617 |
| TTFT_ms p50/p90 | 3694.632 / 8211.137 |
| TPOT_ms p50 | 148.050 |
| cached/prompt | 53248 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 4091.476 / 11545.215 |
| TPOT_ms p50 | 385.629 |
| cached/prompt | 0 / 30741 |
