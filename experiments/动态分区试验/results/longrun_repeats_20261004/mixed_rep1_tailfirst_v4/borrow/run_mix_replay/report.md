# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **79.35**
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
| TTFT_ms | 2946.736 | 7289.825 | 10584.310 | 3620.917 | 256 |
| TPOT_ms | 165.485 | 397.230 | 406.701 | 224.120 | 256 |
| e2e_ms | 6524.821 | 13293.603 | 13348.180 | 7206.830 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.784 |
| per_req_hit p50/p90 | 0.000 / 0.899 |
| cold_miss_rate | 0.656 |
| cached/prompt | 732672 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 395.207 / 480.714 |
| req/s | 3.226 |
| output tok/s | 51.619 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2304.228 / 4806.164 |
| TPOT_ms p50 | 123.650 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7285.548 / 9954.628 |
| TPOT_ms p50 | 394.162 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.886 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2227.373 / 4728.108 |
| TPOT_ms p50 | 122.162 |
| cached/prompt | 670464 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.385 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 2950.108 / 7292.496 |
| TPOT_ms p50 | 171.267 |
| cached/prompt | 56576 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3340.091 / 10561.487 |
| TPOT_ms p50 | 375.347 |
| cached/prompt | 0 / 30741 |
