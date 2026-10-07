# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **81.209**
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
| TTFT_ms | 3066.694 | 8783.674 | 11581.049 | 3925.947 | 256 |
| TPOT_ms | 273.051 | 487.062 | 548.936 | 289.390 | 256 |
| e2e_ms | 7101.654 | 17276.787 | 20364.280 | 8556.185 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.801 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.648 |
| cached/prompt | 748032 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 401.232 / 485.928 |
| req/s | 3.152 |
| output tok/s | 50.438 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.875 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2269.387 / 4978.155 |
| TPOT_ms p50 | 125.099 |
| cached/prompt | 688896 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 8792.312 / 11457.251 |
| TPOT_ms p50 | 532.017 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2146.208 / 4974.453 |
| TPOT_ms p50 | 123.394 |
| cached/prompt | 683264 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.403 |
| per_req_hit p50/p90 | 0.000 / 0.655 |
| TTFT_ms p50/p90 | 3151.846 / 8788.508 |
| TPOT_ms p50 | 319.443 |
| cached/prompt | 59136 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3449.512 / 10787.933 |
| TPOT_ms p50 | 468.376 |
| cached/prompt | 0 / 30741 |
