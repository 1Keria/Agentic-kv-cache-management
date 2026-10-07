# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **78.148**
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
| TTFT_ms | 3118.524 | 9261.926 | 11789.177 | 3732.624 | 256 |
| TPOT_ms | 141.492 | 425.494 | 435.145 | 224.331 | 256 |
| e2e_ms | 6298.159 | 14445.233 | 16343.184 | 7321.917 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.797 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.656 |
| cached/prompt | 744704 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1608.391 / 1692.839 |
| req/s | 3.276 |
| output tok/s | 52.413 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.875 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2247.425 / 4780.042 |
| TPOT_ms p50 | 125.657 |
| cached/prompt | 688896 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 9271.681 / 11935.151 |
| TPOT_ms p50 | 343.511 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2230.651 / 4466.401 |
| TPOT_ms p50 | 124.873 |
| cached/prompt | 683264 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.380 |
| per_req_hit p50/p90 | 0.000 / 0.617 |
| TTFT_ms p50/p90 | 3261.247 / 9268.735 |
| TPOT_ms p50 | 142.776 |
| cached/prompt | 55808 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3654.322 / 11745.008 |
| TPOT_ms p50 | 402.492 |
| cached/prompt | 0 / 30741 |
