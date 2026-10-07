# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30137`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **109.776**
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
| TTFT_ms | 7282.706 | 20022.983 | 20246.108 | 9278.605 | 256 |
| TPOT_ms | 160.347 | 412.687 | 534.495 | 220.446 | 256 |
| e2e_ms | 11136.118 | 21850.561 | 22180.786 | 12805.746 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.491 |
| per_req_hit p50/p90 | 0.000 / 0.206 |
| cold_miss_rate | 0.887 |
| cached/prompt | 458240 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 421.724 / 506.657 |
| req/s | 2.332 |
| output tok/s | 37.312 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.576 |
| per_req_hit p50/p90 | 0.319 / 0.977 |
| TTFT_ms p50/p90 | 3667.787 / 8649.582 |
| TPOT_ms p50 | 155.835 |
| cached/prompt | 453632 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.181 |
| TTFT_ms p50/p90 | 19816.906 / 20308.363 |
| TPOT_ms p50 | 127.668 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.595 |
| per_req_hit p50/p90 | 0.375 / 0.979 |
| TTFT_ms p50/p90 | 3513.997 / 6848.051 |
| TPOT_ms p50 | 160.906 |
| cached/prompt | 450816 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.031 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 9279.618 / 20031.443 |
| TPOT_ms p50 | 162.175 |
| cached/prompt | 4608 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13287.519 / 20239.787 |
| TPOT_ms p50 | 260.609 |
| cached/prompt | 0 / 30741 |
