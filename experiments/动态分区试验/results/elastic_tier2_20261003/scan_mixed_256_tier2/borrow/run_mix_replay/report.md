# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30105`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **77.145**
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
| TTFT_ms | 4028.233 | 10832.340 | 11772.386 | 4457.588 | 256 |
| TPOT_ms | 237.161 | 400.392 | 530.133 | 244.805 | 256 |
| e2e_ms | 8088.028 | 13480.434 | 14559.073 | 8374.474 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.776 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.668 |
| cached/prompt | 724992 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 461.385 / 546.026 |
| req/s | 3.318 |
| output tok/s | 53.095 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 723.678 / 5735.949 |
| TPOT_ms p50 | 122.453 |
| cached/prompt | 672768 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11677.931 / 12243.913 |
| TPOT_ms p50 | 325.369 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 587.090 / 4016.034 |
| TPOT_ms p50 | 122.308 |
| cached/prompt | 672768 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.356 |
| per_req_hit p50/p90 | 0.000 / 0.617 |
| TTFT_ms p50/p90 | 5354.483 / 11623.212 |
| TPOT_ms p50 | 247.328 |
| cached/prompt | 52224 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5911.458 / 11673.148 |
| TPOT_ms p50 | 374.661 |
| cached/prompt | 0 / 30741 |
