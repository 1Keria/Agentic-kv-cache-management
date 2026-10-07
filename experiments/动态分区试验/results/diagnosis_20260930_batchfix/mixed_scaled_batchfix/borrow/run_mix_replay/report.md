# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **350.709**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 1261 |
| n_ok | 1261 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 626.618 | 3653.878 | 8006.326 | 1475.710 | 1261 |
| TPOT_ms | 217.228 | 375.326 | 459.705 | 222.386 | 1261 |
| e2e_ms | 4691.131 | 8030.711 | 10489.850 | 5033.879 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.881 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.649 |
| cached/prompt | 7858688 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.655 / 10.180 |
| req/s | 3.596 |
| output tok/s | 57.529 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.928 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 448.124 / 2155.442 |
| TPOT_ms p50 | 129.124 |
| cached/prompt | 7571200 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 1160.207 / 6321.255 |
| TPOT_ms p50 | 297.298 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.937 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 440.639 / 1993.312 |
| TPOT_ms p50 | 127.936 |
| cached/prompt | 7565568 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.377 |
| per_req_hit p50/p90 | 0.000 / 0.610 |
| TTFT_ms p50/p90 | 677.758 / 4271.111 |
| TPOT_ms p50 | 234.047 |
| cached/prompt | 287488 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 758.871 / 5977.324 |
| TPOT_ms p50 | 281.414 |
| cached/prompt | 0 / 174542 |
