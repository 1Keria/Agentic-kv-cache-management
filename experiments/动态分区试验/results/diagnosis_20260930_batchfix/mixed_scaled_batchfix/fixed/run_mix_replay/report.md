# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **348.514**
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
| TTFT_ms | 645.610 | 2804.671 | 3378.111 | 1076.223 | 1261 |
| TPOT_ms | 152.029 | 340.048 | 637.154 | 204.092 | 1261 |
| e2e_ms | 3789.156 | 6355.819 | 10941.255 | 4341.688 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.886 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.654 |
| cached/prompt | 7903744 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.640 / 1.157 |
| req/s | 3.618 |
| output tok/s | 57.892 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.934 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 463.387 / 2212.469 |
| TPOT_ms p50 | 126.766 |
| cached/prompt | 7615744 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.006 |
| per_req_hit p50/p90 | 0.000 / 0.017 |
| TTFT_ms p50/p90 | 920.269 / 3441.443 |
| TPOT_ms p50 | 242.661 |
| cached/prompt | 512 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.943 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 456.682 / 2189.897 |
| TPOT_ms p50 | 126.335 |
| cached/prompt | 7615232 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.378 |
| per_req_hit p50/p90 | 0.000 / 0.610 |
| TTFT_ms p50/p90 | 711.707 / 2825.598 |
| TPOT_ms p50 | 156.269 |
| cached/prompt | 288000 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 779.242 / 2943.558 |
| TPOT_ms p50 | 218.476 |
| cached/prompt | 0 / 174542 |
