# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **72.956**
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
| TTFT_ms | 3170.039 | 4678.090 | 4813.592 | 2815.894 | 256 |
| TPOT_ms | 251.251 | 415.058 | 428.641 | 273.993 | 256 |
| e2e_ms | 6870.914 | 9951.790 | 9971.068 | 7199.789 | 256 |

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
| s_time_drift_ms p50/p90 (session start) | 391.416 / 475.426 |
| req/s | 3.509 |
| output tok/s | 56.144 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2194.136 / 2815.349 |
| TPOT_ms p50 | 123.036 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.467 |
| TTFT_ms p50/p90 | 3670.888 / 4139.549 |
| TPOT_ms p50 | 359.437 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2190.642 / 2424.928 |
| TPOT_ms p50 | 120.188 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.438 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 3273.269 / 4680.580 |
| TPOT_ms p50 | 251.325 |
| cached/prompt | 64256 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3679.092 / 4682.771 |
| TPOT_ms p50 | 390.919 |
| cached/prompt | 0 / 30741 |
