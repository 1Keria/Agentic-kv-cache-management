# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **111.886**
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
| TTFT_ms | 9179.932 | 23711.454 | 33633.043 | 11443.411 | 256 |
| TPOT_ms | 215.863 | 721.558 | 897.702 | 327.098 | 256 |
| e2e_ms | 11451.044 | 34966.832 | 42329.217 | 16676.977 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.363 |
| per_req_hit p50/p90 | 0.000 / 0.054 |
| cold_miss_rate | 0.898 |
| cached/prompt | 338688 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1745.657 / 1830.491 |
| req/s | 2.288 |
| output tok/s | 36.609 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.430 |
| per_req_hit p50/p90 | 0.123 / 0.963 |
| TTFT_ms p50/p90 | 3736.788 / 6828.897 |
| TPOT_ms p50 | 133.027 |
| cached/prompt | 338688 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 6932.561 / 18763.204 |
| TPOT_ms p50 | 407.068 |
| cached/prompt | 0 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.447 |
| per_req_hit p50/p90 | 0.150 / 0.966 |
| TTFT_ms p50/p90 | 3686.282 / 5893.956 |
| TPOT_ms p50 | 129.611 |
| cached/prompt | 338688 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11683.055 / 24341.422 |
| TPOT_ms p50 | 263.977 |
| cached/prompt | 0 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13619.165 / 30574.683 |
| TPOT_ms p50 | 416.014 |
| cached/prompt | 0 / 30741 |
