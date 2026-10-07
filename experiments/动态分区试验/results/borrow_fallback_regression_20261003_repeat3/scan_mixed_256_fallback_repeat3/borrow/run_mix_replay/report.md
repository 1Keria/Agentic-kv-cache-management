# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **70.157**
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
| TTFT_ms | 3014.963 | 7862.088 | 8014.787 | 3049.712 | 256 |
| TPOT_ms | 166.767 | 287.293 | 307.148 | 197.024 | 256 |
| e2e_ms | 6365.128 | 10529.992 | 10584.897 | 6202.094 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.801 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.648 |
| cached/prompt | 747776 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 991.629 / 1077.015 |
| req/s | 3.649 |
| output tok/s | 58.383 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.871 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2235.277 / 4901.369 |
| TPOT_ms p50 | 125.648 |
| cached/prompt | 685568 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 7903.811 / 8052.655 |
| TPOT_ms p50 | 287.440 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2231.380 / 2999.437 |
| TPOT_ms p50 | 125.258 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.424 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 3136.077 / 7864.642 |
| TPOT_ms p50 | 239.800 |
| cached/prompt | 62208 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3533.657 / 7957.089 |
| TPOT_ms p50 | 256.485 |
| cached/prompt | 0 / 30741 |
