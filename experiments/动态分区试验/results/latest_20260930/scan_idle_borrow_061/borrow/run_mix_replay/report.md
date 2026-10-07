# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **74.54**
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
| TTFT_ms | 2912.723 | 4252.146 | 4993.538 | 2670.728 | 256 |
| TPOT_ms | 147.000 | 404.829 | 496.305 | 250.076 | 256 |
| e2e_ms | 6344.026 | 9372.291 | 10285.105 | 6671.939 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.809 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.637 |
| cached/prompt | 755456 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 424.533 / 509.232 |
| req/s | 3.434 |
| output tok/s | 54.950 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2190.282 / 4546.987 |
| TPOT_ms p50 | 120.959 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 2781.514 / 4345.344 |
| TPOT_ms p50 | 324.203 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2180.911 / 4544.958 |
| TPOT_ms p50 | 119.259 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.438 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 2918.829 / 4244.271 |
| TPOT_ms p50 | 344.197 |
| cached/prompt | 64256 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3319.404 / 4263.859 |
| TPOT_ms p50 | 375.505 |
| cached/prompt | 0 / 30741 |
