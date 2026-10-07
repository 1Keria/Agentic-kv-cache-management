# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **111.865**
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
| TTFT_ms | 9504.625 | 26435.736 | 28677.089 | 13023.656 | 256 |
| TPOT_ms | 132.677 | 282.274 | 797.173 | 203.075 | 256 |
| e2e_ms | 17406.078 | 28609.145 | 30646.008 | 16272.861 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.497 |
| per_req_hit p50/p90 | 0.000 / 0.136 |
| cold_miss_rate | 0.895 |
| cached/prompt | 463872 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 986.968 / 1071.370 |
| req/s | 2.288 |
| output tok/s | 36.616 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.581 |
| per_req_hit p50/p90 | 0.339 / 0.977 |
| TTFT_ms p50/p90 | 2570.063 / 7896.983 |
| TPOT_ms p50 | 143.875 |
| cached/prompt | 457216 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 7950.403 / 24336.215 |
| TPOT_ms p50 | 629.765 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.600 |
| per_req_hit p50/p90 | 0.454 / 0.979 |
| TTFT_ms p50/p90 | 2332.677 / 7396.758 |
| TPOT_ms p50 | 142.754 |
| cached/prompt | 454400 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.045 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13488.865 / 28401.293 |
| TPOT_ms p50 | 125.294 |
| cached/prompt | 6656 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 22092.924 / 28664.579 |
| TPOT_ms p50 | 125.022 |
| cached/prompt | 0 / 30741 |
