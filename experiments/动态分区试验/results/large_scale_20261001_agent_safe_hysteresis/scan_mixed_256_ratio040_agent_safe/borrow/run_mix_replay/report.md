# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **75.587**
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
| TTFT_ms | 3555.849 | 11623.562 | 11864.915 | 4459.388 | 256 |
| TPOT_ms | 260.565 | 662.192 | 674.616 | 312.616 | 256 |
| e2e_ms | 8991.520 | 13977.984 | 14016.225 | 9461.238 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.805 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.645 |
| cached/prompt | 751872 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 492.452 / 577.626 |
| req/s | 3.387 |
| output tok/s | 54.189 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.874 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 1657.327 / 3997.148 |
| TPOT_ms p50 | 125.594 |
| cached/prompt | 688128 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 3814.668 / 10096.834 |
| TPOT_ms p50 | 714.892 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.905 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 1119.952 / 3985.517 |
| TPOT_ms p50 | 125.148 |
| cached/prompt | 685312 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.434 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 3616.637 / 11625.365 |
| TPOT_ms p50 | 316.876 |
| cached/prompt | 63744 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5566.863 / 11853.176 |
| TPOT_ms p50 | 524.106 |
| cached/prompt | 0 / 30741 |
