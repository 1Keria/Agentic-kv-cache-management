# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.703**
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
| TTFT_ms | 2823.360 | 9089.274 | 11721.402 | 4212.199 | 256 |
| TPOT_ms | 149.077 | 354.573 | 405.247 | 212.870 | 256 |
| e2e_ms | 6872.250 | 10970.027 | 14004.228 | 7618.121 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.802 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.664 |
| cached/prompt | 749056 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 418.310 / 503.065 |
| req/s | 3.338 |
| output tok/s | 53.401 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2200.970 / 5041.111 |
| TPOT_ms p50 | 130.911 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 8958.181 / 11615.692 |
| TPOT_ms p50 | 142.757 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2185.535 / 3121.247 |
| TPOT_ms p50 | 127.175 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.394 |
| per_req_hit p50/p90 | 0.000 / 0.642 |
| TTFT_ms p50/p90 | 4988.805 / 9092.941 |
| TPOT_ms p50 | 158.858 |
| cached/prompt | 57856 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5600.014 / 9099.825 |
| TPOT_ms p50 | 334.912 |
| cached/prompt | 0 / 30741 |
