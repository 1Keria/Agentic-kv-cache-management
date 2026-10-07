# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.917**
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
| TTFT_ms | 2849.318 | 7734.482 | 8185.118 | 3183.143 | 256 |
| TPOT_ms | 143.166 | 401.337 | 410.702 | 223.572 | 256 |
| e2e_ms | 6112.745 | 11731.613 | 12795.258 | 6760.288 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.800 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.656 |
| cached/prompt | 747264 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1011.219 / 1095.607 |
| req/s | 3.328 |
| output tok/s | 53.252 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2238.217 / 4162.637 |
| TPOT_ms p50 | 122.623 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 8000.033 / 10675.526 |
| TPOT_ms p50 | 316.108 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2213.651 / 3966.153 |
| TPOT_ms p50 | 120.735 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.382 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 2984.273 / 7965.390 |
| TPOT_ms p50 | 146.670 |
| cached/prompt | 56064 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3381.495 / 8175.591 |
| TPOT_ms p50 | 378.026 |
| cached/prompt | 0 / 30741 |
