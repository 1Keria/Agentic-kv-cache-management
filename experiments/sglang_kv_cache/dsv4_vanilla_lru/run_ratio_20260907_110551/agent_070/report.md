# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_070`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **13394.706**
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
| TTFT_ms | 306.868 | 751.299 | 3134.714 | 460.178 | 2000 |
| TPOT_ms | 8.838 | 19.259 | 36.044 | 11.315 | 2000 |
| e2e_ms | 2190.753 | 9168.114 | 22162.816 | 4004.054 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.938 |
| per_req_hit p50/p90 | 0.958 / 0.994 |
| cold_miss_rate | 0.283 |
| cached/prompt | 62988544 / 67124076 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.841 / 2.574 |
| req/s | 0.149 |
| output tok/s | 48.744 |

## OpenHands

| metric | value |
|---|---|
| n | 1400 |
| token_weighted_hit | 0.944 |
| per_req_hit p50/p90 | 0.980 / 0.995 |
| TTFT_ms p50/p90 | 339.360 / 707.999 |
| TPOT_ms p50 | 8.212 |
| cached/prompt | 62947072 / 66693033 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 43 |
| token_weighted_hit | 0.147 |
| per_req_hit p50/p90 | 0.158 / 0.523 |
| TTFT_ms p50/p90 | 2379.792 / 3291.476 |
| TPOT_ms p50 | 25.533 |
| cached/prompt | 112640 / 765432 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 1357 |
| token_weighted_hit | 0.953 |
| per_req_hit p50/p90 | 0.981 / 0.996 |
| TTFT_ms p50/p90 | 334.288 / 617.376 |
| TPOT_ms p50 | 8.136 |
| cached/prompt | 62834432 / 65927601 |

## Request

| metric | value |
|---|---|
| n | 600 |
| token_weighted_hit | 0.096 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 168.268 / 1137.177 |
| TPOT_ms p50 | 12.738 |
| cached/prompt | 41472 / 431043 |

## Request turn0

| metric | value |
|---|---|
| n | 291 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 168.730 / 2040.772 |
| TPOT_ms p50 | 19.258 |
| cached/prompt | 0 / 89591 |
