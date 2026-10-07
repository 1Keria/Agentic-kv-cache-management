# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **74.681**
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
| TTFT_ms | 4923.217 | 6992.948 | 7575.782 | 4292.985 | 256 |
| TPOT_ms | 292.775 | 413.137 | 433.207 | 269.912 | 256 |
| e2e_ms | 9488.981 | 12551.769 | 12570.642 | 8611.574 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.809 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.637 |
| cached/prompt | 755456 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 397.828 / 483.158 |
| req/s | 3.428 |
| output tok/s | 54.847 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2171.869 / 3947.641 |
| TPOT_ms p50 | 127.389 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.467 |
| TTFT_ms p50/p90 | 6421.796 / 6902.374 |
| TPOT_ms p50 | 348.170 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2150.517 / 3120.549 |
| TPOT_ms p50 | 123.965 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.438 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 5918.268 / 7446.769 |
| TPOT_ms p50 | 348.321 |
| cached/prompt | 64256 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 6456.241 / 7463.604 |
| TPOT_ms p50 | 380.737 |
| cached/prompt | 0 / 30741 |
