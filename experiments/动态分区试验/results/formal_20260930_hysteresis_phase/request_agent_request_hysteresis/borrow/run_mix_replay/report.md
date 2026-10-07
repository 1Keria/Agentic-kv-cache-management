# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.886**
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
| TTFT_ms | 780.464 | 4185.436 | 7405.368 | 1706.189 | 1261 |
| TPOT_ms | 288.090 | 900.724 | 1618.113 | 466.389 | 1261 |
| e2e_ms | 7235.738 | 18211.379 | 31231.130 | 9168.408 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.881 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.666 |
| cached/prompt | 7852288 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.043 / 1.946 |
| req/s | 3.311 |
| output tok/s | 52.971 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.927 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 461.283 / 703.188 |
| TPOT_ms p50 | 128.543 |
| cached/prompt | 7559168 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 691.531 / 989.165 |
| TPOT_ms p50 | 121.483 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.934 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 458.069 / 640.790 |
| TPOT_ms p50 | 128.704 |
| cached/prompt | 7542272 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.385 |
| per_req_hit p50/p90 | 0.000 / 0.626 |
| TTFT_ms p50/p90 | 1211.864 / 4512.904 |
| TPOT_ms p50 | 508.601 |
| cached/prompt | 293120 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1802.789 / 5269.977 |
| TPOT_ms p50 | 772.199 |
| cached/prompt | 0 / 174542 |
