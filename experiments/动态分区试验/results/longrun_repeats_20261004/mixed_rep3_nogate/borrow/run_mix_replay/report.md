# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **77.526**
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
| TTFT_ms | 2950.784 | 7279.221 | 10015.316 | 3544.680 | 256 |
| TPOT_ms | 142.075 | 394.073 | 403.334 | 215.285 | 256 |
| e2e_ms | 6096.086 | 12647.460 | 14077.839 | 6989.235 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.783 |
| per_req_hit p50/p90 | 0.000 / 0.899 |
| cold_miss_rate | 0.648 |
| cached/prompt | 730880 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 401.077 / 486.377 |
| req/s | 3.302 |
| output tok/s | 52.834 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2614.410 / 4722.558 |
| TPOT_ms p50 | 126.598 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7256.599 / 9921.375 |
| TPOT_ms p50 | 355.803 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.886 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2275.404 / 4135.239 |
| TPOT_ms p50 | 124.909 |
| cached/prompt | 670464 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.373 |
| per_req_hit p50/p90 | 0.000 / 0.605 |
| TTFT_ms p50/p90 | 2952.922 / 7281.968 |
| TPOT_ms p50 | 145.345 |
| cached/prompt | 54784 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3352.179 / 9965.379 |
| TPOT_ms p50 | 370.577 |
| cached/prompt | 0 / 30741 |
