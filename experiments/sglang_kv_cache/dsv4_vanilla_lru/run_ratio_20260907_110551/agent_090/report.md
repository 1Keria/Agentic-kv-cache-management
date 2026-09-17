# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_090`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **14729.485**
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
| TTFT_ms | 329.932 | 726.601 | 2515.650 | 442.764 | 2000 |
| TPOT_ms | 8.553 | 13.135 | 24.399 | 9.805 | 2000 |
| e2e_ms | 2025.308 | 7024.913 | 22547.396 | 3462.669 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.935 |
| per_req_hit p50/p90 | 0.976 / 0.995 |
| cold_miss_rate | 0.096 |
| cached/prompt | 79044352 / 84519864 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.786 / 1.674 |
| req/s | 0.136 |
| output tok/s | 42.383 |

## OpenHands

| metric | value |
|---|---|
| n | 1800 |
| token_weighted_hit | 0.937 |
| per_req_hit p50/p90 | 0.980 / 0.995 |
| TTFT_ms p50/p90 | 341.144 / 754.943 |
| TPOT_ms p50 | 8.441 |
| cached/prompt | 79021824 / 84371616 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 55 |
| token_weighted_hit | 0.159 |
| per_req_hit p50/p90 | 0.163 / 0.527 |
| TTFT_ms p50/p90 | 1087.581 / 2746.167 |
| TPOT_ms p50 | 15.971 |
| cached/prompt | 143616 / 903173 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 1745 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.981 / 0.995 |
| TTFT_ms p50/p90 | 337.840 / 666.403 |
| TPOT_ms p50 | 8.349 |
| cached/prompt | 78878208 / 83468443 |

## Request

| metric | value |
|---|---|
| n | 200 |
| token_weighted_hit | 0.152 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 165.873 / 389.990 |
| TPOT_ms p50 | 10.967 |
| cached/prompt | 22528 / 148248 |

## Request turn0

| metric | value |
|---|---|
| n | 86 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 166.229 / 511.847 |
| TPOT_ms p50 | 12.875 |
| cached/prompt | 0 / 22774 |
