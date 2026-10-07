# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **76.139**
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
| TTFT_ms | 4536.226 | 10560.994 | 13296.676 | 4803.244 | 256 |
| TPOT_ms | 250.596 | 425.651 | 540.074 | 264.261 | 256 |
| e2e_ms | 6458.017 | 18833.717 | 21938.501 | 9031.413 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.785 |
| per_req_hit p50/p90 | 0.000 / 0.899 |
| cold_miss_rate | 0.648 |
| cached/prompt | 732928 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 396.423 / 481.641 |
| req/s | 3.362 |
| output tok/s | 53.797 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.859 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2167.030 / 4913.648 |
| TPOT_ms p50 | 126.090 |
| cached/prompt | 676096 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 10499.537 / 13166.851 |
| TPOT_ms p50 | 522.952 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.886 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2153.787 / 3498.173 |
| TPOT_ms p50 | 125.560 |
| cached/prompt | 670464 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.387 |
| per_req_hit p50/p90 | 0.000 / 0.620 |
| TTFT_ms p50/p90 | 5603.011 / 10563.945 |
| TPOT_ms p50 | 271.364 |
| cached/prompt | 56832 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 6133.400 / 12482.773 |
| TPOT_ms p50 | 407.891 |
| cached/prompt | 0 / 30741 |
