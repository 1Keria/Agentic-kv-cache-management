# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **75.755**
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
| TTFT_ms | 3141.838 | 11295.495 | 11429.829 | 3844.715 | 256 |
| TPOT_ms | 328.159 | 537.625 | 694.817 | 316.715 | 256 |
| e2e_ms | 8857.780 | 20019.362 | 22542.131 | 8912.156 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.783 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.664 |
| cached/prompt | 731648 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 994.077 / 1079.107 |
| req/s | 3.379 |
| output tok/s | 54.069 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 720.352 / 4023.245 |
| TPOT_ms p50 | 124.204 |
| cached/prompt | 672768 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11328.334 / 11417.276 |
| TPOT_ms p50 | 545.326 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 588.764 / 2528.883 |
| TPOT_ms p50 | 124.031 |
| cached/prompt | 672768 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.401 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 3280.818 / 11296.651 |
| TPOT_ms p50 | 396.870 |
| cached/prompt | 58880 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3711.944 / 11423.143 |
| TPOT_ms p50 | 473.610 |
| cached/prompt | 0 / 30741 |
