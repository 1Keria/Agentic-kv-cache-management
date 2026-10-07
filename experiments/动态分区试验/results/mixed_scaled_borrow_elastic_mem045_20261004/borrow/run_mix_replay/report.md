# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **353.131**
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
| TTFT_ms | 686.415 | 3081.826 | 5709.401 | 1232.480 | 1261 |
| TPOT_ms | 146.894 | 307.724 | 370.159 | 191.400 | 1261 |
| e2e_ms | 3985.950 | 6341.884 | 8289.212 | 4294.886 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.638 |
| cached/prompt | 7931904 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.690 / 558.760 |
| req/s | 3.571 |
| output tok/s | 57.135 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.936 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 466.594 / 2206.499 |
| TPOT_ms p50 | 126.097 |
| cached/prompt | 7632896 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.227 |
| TTFT_ms p50/p90 | 863.573 / 4761.630 |
| TPOT_ms p50 | 304.774 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.943 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 464.377 / 2168.969 |
| TPOT_ms p50 | 126.031 |
| cached/prompt | 7616000 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.393 |
| per_req_hit p50/p90 | 0.000 / 0.621 |
| TTFT_ms p50/p90 | 779.384 / 3131.755 |
| TPOT_ms p50 | 158.002 |
| cached/prompt | 299008 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 917.621 / 3132.141 |
| TPOT_ms p50 | 276.640 |
| cached/prompt | 0 / 174542 |
