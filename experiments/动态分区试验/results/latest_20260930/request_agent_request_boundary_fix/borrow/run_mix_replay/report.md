# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **382.37**
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
| TTFT_ms | 756.181 | 4650.576 | 7929.642 | 1811.487 | 1261 |
| TPOT_ms | 349.027 | 934.195 | 1346.639 | 465.575 | 1261 |
| e2e_ms | 8941.451 | 18229.654 | 24257.782 | 9260.681 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.880 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.671 |
| cached/prompt | 7850496 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.100 / 4.787 |
| req/s | 3.298 |
| output tok/s | 52.766 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.927 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 464.098 / 721.881 |
| TPOT_ms p50 | 129.601 |
| cached/prompt | 7560192 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 681.633 / 888.669 |
| TPOT_ms p50 | 146.268 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.934 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 461.309 / 674.255 |
| TPOT_ms p50 | 129.519 |
| cached/prompt | 7543296 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.381 |
| per_req_hit p50/p90 | 0.000 / 0.625 |
| TTFT_ms p50/p90 | 1060.612 / 4791.559 |
| TPOT_ms p50 | 555.999 |
| cached/prompt | 290304 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2182.183 / 5322.420 |
| TPOT_ms p50 | 686.446 |
| cached/prompt | 0 / 174542 |
