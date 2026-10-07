# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **77.84**
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
| TTFT_ms | 3104.450 | 10128.138 | 10419.730 | 3776.836 | 256 |
| TPOT_ms | 246.810 | 394.933 | 410.250 | 243.923 | 256 |
| e2e_ms | 8135.937 | 15366.620 | 15408.347 | 7679.603 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.776 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.695 |
| cached/prompt | 725248 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1682.265 / 1767.241 |
| req/s | 3.289 |
| output tok/s | 52.621 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.857 |
| per_req_hit p50/p90 | 0.933 / 0.987 |
| TTFT_ms p50/p90 | 2172.738 / 3955.662 |
| TPOT_ms p50 | 120.605 |
| cached/prompt | 674816 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 10295.661 / 11518.410 |
| TPOT_ms p50 | 403.442 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.884 |
| per_req_hit p50/p90 | 0.945 / 0.987 |
| TTFT_ms p50/p90 | 1180.563 / 3854.112 |
| TPOT_ms p50 | 117.491 |
| cached/prompt | 669184 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.343 |
| per_req_hit p50/p90 | 0.000 / 0.642 |
| TTFT_ms p50/p90 | 3108.278 / 10258.863 |
| TPOT_ms p50 | 249.163 |
| cached/prompt | 50432 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3320.744 / 10408.933 |
| TPOT_ms p50 | 371.615 |
| cached/prompt | 0 / 30741 |
