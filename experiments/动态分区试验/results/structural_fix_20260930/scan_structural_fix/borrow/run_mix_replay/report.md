# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **73.343**
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
| TTFT_ms | 3146.894 | 4557.515 | 5287.978 | 2926.157 | 256 |
| TPOT_ms | 166.228 | 456.262 | 465.542 | 261.357 | 256 |
| e2e_ms | 7240.787 | 10288.957 | 10307.593 | 7107.863 | 256 |

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
| s_time_drift_ms p50/p90 (session start) | 399.342 / 484.044 |
| req/s | 3.490 |
| output tok/s | 55.847 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2205.293 / 3984.952 |
| TPOT_ms p50 | 120.378 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 3207.224 / 4419.493 |
| TPOT_ms p50 | 382.508 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2150.515 / 3949.529 |
| TPOT_ms p50 | 117.339 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.438 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 3152.038 / 5160.232 |
| TPOT_ms p50 | 253.293 |
| cached/prompt | 64256 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3329.435 / 5177.019 |
| TPOT_ms p50 | 433.519 |
| cached/prompt | 0 / 30741 |
