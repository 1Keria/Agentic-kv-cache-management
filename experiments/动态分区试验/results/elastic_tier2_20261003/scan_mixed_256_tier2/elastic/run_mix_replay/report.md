# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30105`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **79.062**
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
| TTFT_ms | 2894.148 | 7792.494 | 10563.829 | 3477.878 | 256 |
| TPOT_ms | 147.462 | 428.103 | 437.390 | 227.816 | 256 |
| e2e_ms | 6091.855 | 12998.033 | 16102.569 | 7122.938 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.799 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.652 |
| cached/prompt | 745984 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 384.347 / 469.665 |
| req/s | 3.238 |
| output tok/s | 51.807 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.875 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2551.361 / 4718.367 |
| TPOT_ms p50 | 121.212 |
| cached/prompt | 688896 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7760.357 / 10422.220 |
| TPOT_ms p50 | 346.252 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2457.275 / 4113.099 |
| TPOT_ms p50 | 119.702 |
| cached/prompt | 683264 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.389 |
| per_req_hit p50/p90 | 0.000 / 0.633 |
| TTFT_ms p50/p90 | 2945.838 / 7794.303 |
| TPOT_ms p50 | 172.416 |
| cached/prompt | 57088 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3351.646 / 10240.646 |
| TPOT_ms p50 | 404.094 |
| cached/prompt | 0 / 30741 |
