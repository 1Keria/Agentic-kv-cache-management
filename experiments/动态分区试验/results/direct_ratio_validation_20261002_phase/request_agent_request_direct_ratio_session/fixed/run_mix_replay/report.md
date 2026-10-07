# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.66**
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
| TTFT_ms | 514.298 | 3981.599 | 9269.033 | 1492.111 | 1261 |
| TPOT_ms | 279.061 | 830.209 | 1727.713 | 457.831 | 1261 |
| e2e_ms | 5901.506 | 18403.577 | 33008.916 | 8817.406 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.877 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.780 |
| cached/prompt | 7819008 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.015 / 1.976 |
| req/s | 3.313 |
| output tok/s | 53.003 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.942 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 459.752 / 677.461 |
| TPOT_ms p50 | 127.648 |
| cached/prompt | 7684096 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 669.633 / 1434.887 |
| TPOT_ms p50 | 134.528 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.950 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 456.884 / 669.903 |
| TPOT_ms p50 | 127.457 |
| cached/prompt | 7667200 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.177 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 629.275 / 4541.618 |
| TPOT_ms p50 | 448.610 |
| cached/prompt | 134912 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 499.070 / 6001.221 |
| TPOT_ms p50 | 688.823 |
| cached/prompt | 0 / 174542 |
