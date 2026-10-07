# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30100`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **75.782**
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
| TTFT_ms | 3029.220 | 9335.262 | 9469.301 | 3471.605 | 256 |
| TPOT_ms | 248.932 | 398.254 | 430.185 | 255.769 | 256 |
| e2e_ms | 6903.785 | 13893.136 | 13925.829 | 7563.904 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.800 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.645 |
| cached/prompt | 747008 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 417.470 / 502.075 |
| req/s | 3.378 |
| output tok/s | 54.050 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.871 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2238.745 / 4834.364 |
| TPOT_ms p50 | 123.498 |
| cached/prompt | 685568 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 9361.781 / 9965.397 |
| TPOT_ms p50 | 406.303 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2214.493 / 4158.775 |
| TPOT_ms p50 | 120.503 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.418 |
| per_req_hit p50/p90 | 0.000 / 0.633 |
| TTFT_ms p50/p90 | 3201.339 / 9338.447 |
| TPOT_ms p50 | 277.841 |
| cached/prompt | 61440 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3679.691 / 9401.245 |
| TPOT_ms p50 | 373.146 |
| cached/prompt | 0 / 30741 |
