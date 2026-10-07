# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **74.605**
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
| TTFT_ms | 2854.642 | 7324.290 | 10603.421 | 3377.585 | 256 |
| TPOT_ms | 168.878 | 397.697 | 406.902 | 235.054 | 256 |
| e2e_ms | 6980.262 | 13273.861 | 13323.406 | 7138.450 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.792 |
| per_req_hit p50/p90 | 0.000 / 0.903 |
| cold_miss_rate | 0.668 |
| cached/prompt | 739584 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 409.805 / 493.906 |
| req/s | 3.431 |
| output tok/s | 54.903 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.875 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2237.705 / 3983.616 |
| TPOT_ms p50 | 124.107 |
| cached/prompt | 688896 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 7318.642 / 9985.786 |
| TPOT_ms p50 | 390.600 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.903 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2140.932 / 3202.566 |
| TPOT_ms p50 | 118.781 |
| cached/prompt | 683264 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.345 |
| per_req_hit p50/p90 | 0.000 / 0.617 |
| TTFT_ms p50/p90 | 2962.480 / 7327.213 |
| TPOT_ms p50 | 247.105 |
| cached/prompt | 50688 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3363.378 / 10579.562 |
| TPOT_ms p50 | 374.365 |
| cached/prompt | 0 / 30741 |
