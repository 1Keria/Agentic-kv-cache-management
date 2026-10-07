# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **70.813**
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
| TTFT_ms | 3201.456 | 4225.398 | 4877.419 | 2818.154 | 256 |
| TPOT_ms | 285.260 | 409.584 | 439.890 | 281.624 | 256 |
| e2e_ms | 7362.363 | 9853.226 | 9867.736 | 7324.137 | 256 |

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
| s_time_drift_ms p50/p90 (session start) | 424.893 / 502.516 |
| req/s | 3.615 |
| output tok/s | 57.842 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2193.615 / 4019.655 |
| TPOT_ms p50 | 125.075 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.467 |
| TTFT_ms p50/p90 | 3736.065 / 4166.099 |
| TPOT_ms p50 | 352.724 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2187.652 / 4003.750 |
| TPOT_ms p50 | 122.429 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.438 |
| per_req_hit p50/p90 | 0.000 / 0.663 |
| TTFT_ms p50/p90 | 3265.199 / 4740.603 |
| TPOT_ms p50 | 352.514 |
| cached/prompt | 64256 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3779.323 / 4744.645 |
| TPOT_ms p50 | 379.499 |
| cached/prompt | 0 / 30741 |
