# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/bidirectional_reuse`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **427.091**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 275 |
| n_ok | 275 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 2139.275 | 14873.027 | 18273.773 | 4709.663 | 275 |
| TPOT_ms | 127.578 | 337.228 | 662.995 | 191.530 | 275 |
| e2e_ms | 4262.623 | 17909.267 | 24406.979 | 7774.149 | 275 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.631 |
| per_req_hit p50/p90 | 0.226 / 0.986 |
| cold_miss_rate | 0.440 |
| cached/prompt | 5863680 / 9285414 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.227 / 1.778 |
| req/s | 0.644 |
| output tok/s | 10.302 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.719 |
| per_req_hit p50/p90 | 0.949 / 0.989 |
| TTFT_ms p50/p90 | 485.391 / 10562.965 |
| TPOT_ms p50 | 125.031 |
| cached/prompt | 5863680 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.137 |
| per_req_hit p50/p90 | 0.211 / 0.222 |
| TTFT_ms p50/p90 | 1249.576 / 5773.460 |
| TPOT_ms p50 | 138.607 |
| cached/prompt | 11264 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.725 |
| per_req_hit p50/p90 | 0.955 / 0.989 |
| TTFT_ms p50/p90 | 478.857 / 10657.269 |
| TPOT_ms p50 | 124.899 |
| cached/prompt | 5852416 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 64 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11321.474 / 16414.629 |
| TPOT_ms p50 | 233.523 |
| cached/prompt | 0 / 1129582 |

## Request turn0

| metric | value |
|---|---|
| n | 16 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 9697.174 / 14653.884 |
| TPOT_ms p50 | 260.066 |
| cached/prompt | 0 / 271218 |
