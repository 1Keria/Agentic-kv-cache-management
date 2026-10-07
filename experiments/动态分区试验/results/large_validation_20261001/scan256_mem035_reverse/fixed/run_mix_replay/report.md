# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **106.613**
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
| TTFT_ms | 9653.238 | 20114.253 | 20302.248 | 10041.797 | 256 |
| TPOT_ms | 148.396 | 503.671 | 811.579 | 250.234 | 256 |
| e2e_ms | 17497.447 | 22544.589 | 27553.178 | 14045.549 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.431 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.910 |
| cached/prompt | 402688 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 952.865 / 1037.326 |
| req/s | 2.401 |
| output tok/s | 38.419 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.512 |
| per_req_hit p50/p90 | 0.136 / 0.977 |
| TTFT_ms p50/p90 | 2114.162 / 16730.986 |
| TPOT_ms p50 | 130.155 |
| cached/prompt | 402688 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 19882.902 / 21067.543 |
| TPOT_ms p50 | 142.016 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.532 |
| per_req_hit p50/p90 | 0.195 / 0.979 |
| TTFT_ms p50/p90 | 1904.052 / 9101.214 |
| TPOT_ms p50 | 125.074 |
| cached/prompt | 402688 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 10520.181 / 20147.396 |
| TPOT_ms p50 | 197.258 |
| cached/prompt | 0 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11584.669 / 20242.278 |
| TPOT_ms p50 | 273.519 |
| cached/prompt | 0 / 30741 |
