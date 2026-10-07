# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **108.778**
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
| TTFT_ms | 9764.056 | 26069.138 | 27212.361 | 11075.204 | 256 |
| TPOT_ms | 176.284 | 494.392 | 624.798 | 273.311 | 256 |
| e2e_ms | 13829.881 | 28398.190 | 31108.692 | 15448.182 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.482 |
| per_req_hit p50/p90 | 0.000 / 0.207 |
| cold_miss_rate | 0.891 |
| cached/prompt | 450304 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 404.985 / 481.213 |
| req/s | 2.353 |
| output tok/s | 37.655 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.563 |
| per_req_hit p50/p90 | 0.283 / 0.977 |
| TTFT_ms p50/p90 | 3052.343 / 10572.335 |
| TPOT_ms p50 | 126.704 |
| cached/prompt | 443392 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.183 |
| TTFT_ms p50/p90 | 11110.748 / 23080.378 |
| TPOT_ms p50 | 136.603 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.582 |
| per_req_hit p50/p90 | 0.426 / 0.979 |
| TTFT_ms p50/p90 | 2295.631 / 6667.965 |
| TPOT_ms p50 | 126.357 |
| cached/prompt | 440576 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.047 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 10647.052 / 26172.297 |
| TPOT_ms p50 | 247.630 |
| cached/prompt | 6912 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 15531.507 / 26321.797 |
| TPOT_ms p50 | 337.947 |
| cached/prompt | 0 / 30741 |
