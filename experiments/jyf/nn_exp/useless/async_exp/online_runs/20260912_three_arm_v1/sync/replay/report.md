# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/experiments/nn_exp/cold_predictor_exp/workloads/agent050_decode32`
- arrival: `waves`
- request_gap_cap_s: None
- wall_clock_s: **953.388**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 2000 |
| n_ok | 2000 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 2662.994 | 26477.733 | 32152.138 | 9189.384 | 2000 |
| TPOT_ms | 97.235 | 600.905 | 913.992 | 228.463 | 2000 |
| e2e_ms | 6600.837 | 42085.619 | 51355.237 | 16202.386 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.619 |
| per_req_hit p50/p90 | 0.000 / 0.990 |
| cold_miss_rate | 0.552 |
| cached/prompt | 29191424 / 47192939 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.962 / 2.117 |
| req/s | 2.098 |
| output tok/s | 65.527 |

## OpenHands

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.627 |
| per_req_hit p50/p90 | 0.937 / 0.994 |
| TTFT_ms p50/p90 | 1493.837 / 22900.008 |
| TPOT_ms p50 | 89.320 |
| cached/prompt | 29037568 / 46293549 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.093 |
| per_req_hit p50/p90 | 0.110 / 0.365 |
| TTFT_ms p50/p90 | 4704.923 / 22342.167 |
| TPOT_ms p50 | 95.082 |
| cached/prompt | 56320 / 604033 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 967 |
| token_weighted_hit | 0.634 |
| per_req_hit p50/p90 | 0.947 / 0.994 |
| TTFT_ms p50/p90 | 1415.841 / 22888.719 |
| TPOT_ms p50 | 89.288 |
| cached/prompt | 28981248 / 45689516 |

## Request

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.000 / 0.239 |
| TTFT_ms p50/p90 | 4152.599 / 27901.352 |
| TPOT_ms p50 | 102.610 |
| cached/prompt | 153856 / 899390 |

## Request turn0

| metric | value |
|---|---|
| n | 500 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3820.136 / 26263.246 |
| TPOT_ms p50 | 97.183 |
| cached/prompt | 0 / 206573 |
