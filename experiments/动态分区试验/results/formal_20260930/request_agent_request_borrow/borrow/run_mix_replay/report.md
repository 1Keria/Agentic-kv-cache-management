# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **381.127**
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
| TTFT_ms | 618.747 | 4408.106 | 10460.206 | 1739.937 | 1261 |
| TPOT_ms | 267.206 | 1106.335 | 1818.368 | 493.900 | 1261 |
| e2e_ms | 7077.787 | 21207.035 | 34411.164 | 9642.338 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.881 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.667 |
| cached/prompt | 7854848 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.027 / 1.923 |
| req/s | 3.309 |
| output tok/s | 52.938 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.927 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 450.301 / 643.023 |
| TPOT_ms p50 | 128.434 |
| cached/prompt | 7560192 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 646.124 / 674.969 |
| TPOT_ms p50 | 130.716 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.934 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 446.111 / 618.292 |
| TPOT_ms p50 | 128.414 |
| cached/prompt | 7543296 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.387 |
| per_req_hit p50/p90 | 0.000 / 0.627 |
| TTFT_ms p50/p90 | 859.311 / 4853.704 |
| TPOT_ms p50 | 512.991 |
| cached/prompt | 294656 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1583.383 / 6403.017 |
| TPOT_ms p50 | 762.380 |
| cached/prompt | 0 / 174542 |
