# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **74.228**
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
| TTFT_ms | 2816.962 | 14390.076 | 14631.666 | 4686.564 | 256 |
| TPOT_ms | 173.735 | 676.123 | 830.316 | 326.223 | 256 |
| e2e_ms | 5630.744 | 16832.452 | 17725.626 | 9906.134 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.776 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.719 |
| cached/prompt | 724480 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1024.962 / 1110.115 |
| req/s | 3.449 |
| output tok/s | 55.181 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.933 / 0.987 |
| TTFT_ms p50/p90 | 1147.997 / 3818.559 |
| TPOT_ms p50 | 123.879 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 6382.660 / 12822.982 |
| TPOT_ms p50 | 831.464 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.945 / 0.987 |
| TTFT_ms p50/p90 | 800.384 / 2745.368 |
| TPOT_ms p50 | 119.862 |
| cached/prompt | 673280 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.329 |
| per_req_hit p50/p90 | 0.000 / 0.633 |
| TTFT_ms p50/p90 | 5249.066 / 14418.651 |
| TPOT_ms p50 | 246.031 |
| cached/prompt | 48384 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5814.259 / 14624.660 |
| TPOT_ms p50 | 651.033 |
| cached/prompt | 0 / 30741 |
