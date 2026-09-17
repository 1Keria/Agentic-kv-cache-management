# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_000`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **11048.374**
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
| TTFT_ms | 343.382 | 10149.852 | 29836.590 | 2659.419 | 2000 |
| TPOT_ms | 18.346 | 97.875 | 842.217 | 62.214 | 2000 |
| e2e_ms | 8405.416 | 21815.756 | 57639.044 | 11904.928 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.399 |
| per_req_hit p50/p90 | 0.000 / 0.630 |
| cold_miss_rate | 0.762 |
| cached/prompt | 661248 / 1656519 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.670 / 1.136 |
| req/s | 0.181 |
| output tok/s | 69.797 |

## Request

| metric | value |
|---|---|
| n | 2000 |
| token_weighted_hit | 0.399 |
| per_req_hit p50/p90 | 0.000 / 0.630 |
| TTFT_ms p50/p90 | 343.382 / 10149.852 |
| TPOT_ms p50 | 18.346 |
| cached/prompt | 661248 / 1656519 |

## Request turn0

| metric | value |
|---|---|
| n | 1037 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 389.308 / 12567.247 |
| TPOT_ms p50 | 30.406 |
| cached/prompt | 0 / 434781 |
