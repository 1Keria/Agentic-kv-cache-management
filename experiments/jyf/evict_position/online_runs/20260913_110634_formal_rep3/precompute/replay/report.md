# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position/workload`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **391.377**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 1970 |
| n_ok | 1970 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 502.437 | 1831.815 | 4344.517 | 753.821 | 1970 |
| TPOT_ms | 20.733 | 53.196 | 188.060 | 30.028 | 1970 |
| e2e_ms | 1274.011 | 2844.948 | 8065.992 | 1689.021 | 1970 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.943 |
| per_req_hit p50/p90 | 0.585 / 0.990 |
| cold_miss_rate | 0.440 |
| cached/prompt | 38242816 / 40548772 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.683 / 1.353 |
| req/s | 5.034 |
| output tok/s | 157.779 |

## OpenHands

| metric | value |
|---|---|
| n | 943 |
| token_weighted_hit | 0.955 |
| per_req_hit p50/p90 | 0.978 / 0.994 |
| TTFT_ms p50/p90 | 558.405 / 1184.535 |
| TPOT_ms p50 | 16.472 |
| cached/prompt | 38018304 / 39792804 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.202 |
| per_req_hit p50/p90 | 0.189 / 0.229 |
| TTFT_ms p50/p90 | 765.611 / 2663.955 |
| TPOT_ms p50 | 24.354 |
| cached/prompt | 107776 / 532640 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 910 |
| token_weighted_hit | 0.966 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 539.958 / 1149.588 |
| TPOT_ms p50 | 16.271 |
| cached/prompt | 37910528 / 39260164 |

## Request

| metric | value |
|---|---|
| n | 1027 |
| token_weighted_hit | 0.297 |
| per_req_hit p50/p90 | 0.000 / 0.525 |
| TTFT_ms p50/p90 | 424.686 / 2147.134 |
| TPOT_ms p50 | 24.602 |
| cached/prompt | 224512 / 755968 |

## Request turn0

| metric | value |
|---|---|
| n | 539 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 354.434 / 2042.757 |
| TPOT_ms p50 | 24.600 |
| cached/prompt | 0 / 174496 |
