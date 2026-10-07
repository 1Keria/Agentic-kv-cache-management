# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **75.357**
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
| TTFT_ms | 2849.082 | 7321.252 | 7487.786 | 3170.539 | 256 |
| TPOT_ms | 247.883 | 399.045 | 412.110 | 252.260 | 256 |
| e2e_ms | 7044.744 | 12141.123 | 13713.106 | 7206.698 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.798 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.648 |
| cached/prompt | 745728 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 400.528 / 485.687 |
| req/s | 3.397 |
| output tok/s | 54.354 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 915.527 / 3929.309 |
| TPOT_ms p50 | 125.679 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7295.476 / 9968.250 |
| TPOT_ms p50 | 417.630 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 534.121 / 3481.274 |
| TPOT_ms p50 | 124.877 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.371 |
| per_req_hit p50/p90 | 0.000 / 0.604 |
| TTFT_ms p50/p90 | 2949.601 / 7322.900 |
| TPOT_ms p50 | 273.456 |
| cached/prompt | 54528 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3352.454 / 7468.368 |
| TPOT_ms p50 | 386.548 |
| cached/prompt | 0 / 30741 |
