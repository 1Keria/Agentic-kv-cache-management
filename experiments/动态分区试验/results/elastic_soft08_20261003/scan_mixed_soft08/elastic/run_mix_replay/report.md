# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30108`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.311**
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
| TTFT_ms | 3003.494 | 8269.589 | 9358.008 | 3429.549 | 256 |
| TPOT_ms | 246.947 | 299.568 | 509.088 | 213.160 | 256 |
| e2e_ms | 5977.961 | 13909.918 | 16416.601 | 6840.106 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.789 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.656 |
| cached/prompt | 736768 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1001.984 / 1086.879 |
| req/s | 3.355 |
| output tok/s | 53.675 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.862 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2233.413 / 4737.049 |
| TPOT_ms p50 | 125.498 |
| cached/prompt | 678400 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 6094.704 / 8749.670 |
| TPOT_ms p50 | 491.398 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2222.131 / 4271.912 |
| TPOT_ms p50 | 124.778 |
| cached/prompt | 672768 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.397 |
| per_req_hit p50/p90 | 0.000 / 0.646 |
| TTFT_ms p50/p90 | 3013.895 / 8271.514 |
| TPOT_ms p50 | 261.907 |
| cached/prompt | 58368 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3342.105 / 9311.977 |
| TPOT_ms p50 | 274.031 |
| cached/prompt | 0 / 30741 |
