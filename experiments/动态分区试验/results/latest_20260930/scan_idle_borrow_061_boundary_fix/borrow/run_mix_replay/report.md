# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.787**
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
| TTFT_ms | 3802.610 | 5974.495 | 6030.952 | 3741.787 | 256 |
| TPOT_ms | 139.452 | 319.809 | 462.043 | 210.410 | 256 |
| e2e_ms | 7824.131 | 10361.980 | 10401.606 | 7108.354 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.806 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.641 |
| cached/prompt | 752640 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1003.679 / 1088.841 |
| req/s | 3.334 |
| output tok/s | 53.342 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.874 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2295.856 / 5174.239 |
| TPOT_ms p50 | 119.977 |
| cached/prompt | 688384 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 5882.159 / 6241.692 |
| TPOT_ms p50 | 320.215 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2264.258 / 4827.712 |
| TPOT_ms p50 | 118.718 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.438 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 5219.002 / 5999.423 |
| TPOT_ms p50 | 254.675 |
| cached/prompt | 64256 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5779.564 / 6014.880 |
| TPOT_ms p50 | 286.625 |
| cached/prompt | 0 / 30741 |
