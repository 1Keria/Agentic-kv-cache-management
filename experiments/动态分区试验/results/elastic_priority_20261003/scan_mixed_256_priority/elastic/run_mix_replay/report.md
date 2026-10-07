# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30101`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **83.189**
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
| TTFT_ms | 2983.845 | 8936.948 | 10039.358 | 3672.552 | 256 |
| TPOT_ms | 313.112 | 680.514 | 826.886 | 349.292 | 256 |
| e2e_ms | 8196.080 | 20899.372 | 22159.999 | 9261.231 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.803 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.648 |
| cached/prompt | 749568 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 2276.123 / 2361.067 |
| req/s | 3.077 |
| output tok/s | 49.237 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.875 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 443.760 / 4024.996 |
| TPOT_ms p50 | 136.459 |
| cached/prompt | 688896 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 8023.858 / 10680.004 |
| TPOT_ms p50 | 827.745 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 436.595 / 3105.566 |
| TPOT_ms p50 | 132.459 |
| cached/prompt | 683264 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.413 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 3172.878 / 9707.972 |
| TPOT_ms p50 | 313.459 |
| cached/prompt | 60672 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3381.258 / 10003.630 |
| TPOT_ms p50 | 324.810 |
| cached/prompt | 0 / 30741 |
