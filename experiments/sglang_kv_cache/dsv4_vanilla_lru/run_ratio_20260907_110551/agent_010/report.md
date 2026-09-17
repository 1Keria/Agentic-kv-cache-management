# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_010`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **11000.304**
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
| TTFT_ms | 313.183 | 651.751 | 2059.024 | 391.602 | 2000 |
| TPOT_ms | 15.599 | 59.034 | 467.670 | 41.291 | 2000 |
| e2e_ms | 6232.154 | 16066.267 | 24705.702 | 7522.953 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.850 |
| per_req_hit p50/p90 | 0.000 / 0.867 |
| cold_miss_rate | 0.718 |
| cached/prompt | 8935680 / 10515202 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.653 / 1.171 |
| req/s | 0.182 |
| output tok/s | 70.940 |

## OpenHands

| metric | value |
|---|---|
| n | 200 |
| token_weighted_hit | 0.933 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 484.663 / 1121.268 |
| TPOT_ms p50 | 8.009 |
| cached/prompt | 8437760 / 9042962 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2077.040 / 2590.600 |
| TPOT_ms p50 | 53.215 |
| cached/prompt | 0 / 135810 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 193 |
| token_weighted_hit | 0.947 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 480.260 / 897.746 |
| TPOT_ms p50 | 7.967 |
| cached/prompt | 8437760 / 8907152 |

## Request

| metric | value |
|---|---|
| n | 1800 |
| token_weighted_hit | 0.338 |
| per_req_hit p50/p90 | 0.000 / 0.591 |
| TTFT_ms p50/p90 | 302.234 / 570.542 |
| TPOT_ms p50 | 16.784 |
| cached/prompt | 497920 / 1472240 |

## Request turn0

| metric | value |
|---|---|
| n | 916 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 367.526 / 949.786 |
| TPOT_ms p50 | 29.983 |
| cached/prompt | 0 / 361358 |
