# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **383.316**
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
| TTFT_ms | 753.190 | 3654.476 | 5755.192 | 1382.161 | 1261 |
| TPOT_ms | 289.832 | 750.370 | 1716.586 | 417.520 | 1261 |
| e2e_ms | 5940.962 | 13971.019 | 29249.032 | 8062.478 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.839 |
| per_req_hit p50/p90 | 0.000 / 0.959 |
| cold_miss_rate | 0.682 |
| cached/prompt | 7478784 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.983 / 1.985 |
| req/s | 3.290 |
| output tok/s | 52.635 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.881 |
| per_req_hit p50/p90 | 0.969 / 0.990 |
| TTFT_ms p50/p90 | 465.284 / 2150.124 |
| TPOT_ms p50 | 131.531 |
| cached/prompt | 7183360 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 712.838 / 1817.831 |
| TPOT_ms p50 | 139.997 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.969 / 0.991 |
| TTFT_ms p50/p90 | 464.361 / 2015.582 |
| TPOT_ms p50 | 131.322 |
| cached/prompt | 7174912 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.388 |
| per_req_hit p50/p90 | 0.000 / 0.621 |
| TTFT_ms p50/p90 | 1024.591 / 3747.828 |
| TPOT_ms p50 | 435.658 |
| cached/prompt | 295424 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 870.745 / 3890.928 |
| TPOT_ms p50 | 613.637 |
| cached/prompt | 0 / 174542 |
