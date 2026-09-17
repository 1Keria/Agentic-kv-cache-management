# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_050`
- arrival: `frozen`
- request_gap_cap_s: 30.0
- wall_clock_s: **11033.813**
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
| TTFT_ms | 292.144 | 1286.072 | 4313.502 | 562.187 | 2000 |
| TPOT_ms | 9.789 | 36.696 | 87.948 | 17.239 | 2000 |
| e2e_ms | 3068.763 | 13031.706 | 24960.784 | 5388.754 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.936 |
| per_req_hit p50/p90 | 0.109 / 0.993 |
| cold_miss_rate | 0.495 |
| cached/prompt | 44185600 / 47192939 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.817 / 2.490 |
| req/s | 0.181 |
| output tok/s | 62.304 |

## OpenHands

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.954 |
| per_req_hit p50/p90 | 0.982 / 0.995 |
| TTFT_ms p50/p90 | 328.398 / 699.645 |
| TPOT_ms p50 | 8.295 |
| cached/prompt | 44169728 / 46293549 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 33 |
| token_weighted_hit | 0.131 |
| per_req_hit p50/p90 | 0.149 / 0.512 |
| TTFT_ms p50/p90 | 2527.236 / 3755.274 |
| TPOT_ms p50 | 44.265 |
| cached/prompt | 78848 / 604033 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 967 |
| token_weighted_hit | 0.965 |
| per_req_hit p50/p90 | 0.983 / 0.995 |
| TTFT_ms p50/p90 | 324.402 / 591.552 |
| TPOT_ms p50 | 8.204 |
| cached/prompt | 44090880 / 45689516 |

## Request

| metric | value |
|---|---|
| n | 1000 |
| token_weighted_hit | 0.018 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 180.387 / 2220.987 |
| TPOT_ms p50 | 15.157 |
| cached/prompt | 15872 / 899390 |

## Request turn0

| metric | value |
|---|---|
| n | 500 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 207.977 / 3249.760 |
| TPOT_ms p50 | 26.538 |
| cached/prompt | 0 / 206573 |
