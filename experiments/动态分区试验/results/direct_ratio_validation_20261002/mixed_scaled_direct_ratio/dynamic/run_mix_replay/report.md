# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **346.128**
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
| TTFT_ms | 601.002 | 4011.239 | 6041.542 | 1257.212 | 1261 |
| TPOT_ms | 142.644 | 249.069 | 321.101 | 163.575 | 1261 |
| e2e_ms | 3134.314 | 6305.085 | 8663.386 | 3874.420 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.896 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.639 |
| cached/prompt | 7991040 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.623 / 1.232 |
| req/s | 3.643 |
| output tok/s | 58.291 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.943 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 470.539 / 2249.313 |
| TPOT_ms p50 | 125.114 |
| cached/prompt | 7689984 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.184 |
| per_req_hit p50/p90 | 0.212 / 0.225 |
| TTFT_ms p50/p90 | 835.293 / 6232.719 |
| TPOT_ms p50 | 206.923 |
| cached/prompt | 15104 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.951 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 468.512 / 2209.366 |
| TPOT_ms p50 | 124.817 |
| cached/prompt | 7674880 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.395 |
| per_req_hit p50/p90 | 0.000 / 0.623 |
| TTFT_ms p50/p90 | 646.378 / 4249.747 |
| TPOT_ms p50 | 148.578 |
| cached/prompt | 301056 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 623.618 / 5723.044 |
| TPOT_ms p50 | 169.757 |
| cached/prompt | 0 / 174542 |
