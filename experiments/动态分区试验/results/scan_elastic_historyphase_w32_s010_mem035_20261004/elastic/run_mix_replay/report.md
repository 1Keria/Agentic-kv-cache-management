# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30142`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **98.356**
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
| TTFT_ms | 9949.660 | 18895.042 | 20416.694 | 9668.213 | 256 |
| TPOT_ms | 137.534 | 486.697 | 623.186 | 209.906 | 256 |
| e2e_ms | 15788.496 | 22237.057 | 23194.061 | 13026.711 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.508 |
| per_req_hit p50/p90 | 0.000 / 0.356 |
| cold_miss_rate | 0.871 |
| cached/prompt | 474368 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 412.803 / 498.371 |
| req/s | 2.603 |
| output tok/s | 41.645 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.595 |
| per_req_hit p50/p90 | 0.451 / 0.977 |
| TTFT_ms p50/p90 | 2258.966 / 9549.552 |
| TPOT_ms p50 | 135.022 |
| cached/prompt | 468480 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 9815.521 / 16689.498 |
| TPOT_ms p50 | 241.627 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.615 |
| per_req_hit p50/p90 | 0.454 / 0.979 |
| TTFT_ms p50/p90 | 2171.113 / 7072.297 |
| TPOT_ms p50 | 129.874 |
| cached/prompt | 465664 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.040 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11899.462 / 18897.527 |
| TPOT_ms p50 | 138.053 |
| cached/prompt | 5888 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 14411.815 / 20312.401 |
| TPOT_ms p50 | 134.557 |
| cached/prompt | 0 / 30741 |
