# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **77.282**
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
| TTFT_ms | 4067.530 | 13501.869 | 15516.681 | 5337.954 | 256 |
| TPOT_ms | 289.731 | 662.718 | 688.884 | 332.586 | 256 |
| e2e_ms | 11504.612 | 19942.454 | 19995.607 | 10659.329 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.792 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.676 |
| cached/prompt | 740096 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 991.563 / 1063.538 |
| req/s | 3.312 |
| output tok/s | 53.000 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.874 |
| per_req_hit p50/p90 | 0.933 / 0.987 |
| TTFT_ms p50/p90 | 2184.558 / 4777.369 |
| TPOT_ms p50 | 123.464 |
| cached/prompt | 687616 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 13206.096 / 13479.985 |
| TPOT_ms p50 | 403.027 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.905 |
| per_req_hit p50/p90 | 0.945 / 0.987 |
| TTFT_ms p50/p90 | 2182.715 / 2893.668 |
| TPOT_ms p50 | 123.442 |
| cached/prompt | 684800 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.357 |
| per_req_hit p50/p90 | 0.000 / 0.617 |
| TTFT_ms p50/p90 | 7577.538 / 13541.570 |
| TPOT_ms p50 | 439.259 |
| cached/prompt | 52480 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 8123.788 / 15496.610 |
| TPOT_ms p50 | 448.639 |
| cached/prompt | 0 / 30741 |
