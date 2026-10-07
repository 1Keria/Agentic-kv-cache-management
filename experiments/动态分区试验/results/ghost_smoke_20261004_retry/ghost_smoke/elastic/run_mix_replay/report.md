# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30124`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/smoke`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **12.75**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 8 |
| n_ok | 8 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 1727.720 | 7689.441 | 8057.252 | 3105.028 | 8 |
| TPOT_ms | 92.100 | 342.518 | 630.076 | 176.270 | 8 |
| e2e_ms | 2929.742 | 8371.908 | 8445.974 | 3810.109 | 8 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.132 |
| per_req_hit p50/p90 | 0.000 / 0.225 |
| cold_miss_rate | 0.750 |
| cached/prompt | 5632 / 42651 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 5.498 / 493.182 |
| req/s | 0.627 |
| output tok/s | 2.510 |

## OpenHands

| metric | value |
|---|---|
| n | 4 |
| token_weighted_hit | 0.132 |
| per_req_hit p50/p90 | 0.112 / 0.226 |
| TTFT_ms p50/p90 | 6123.687 / 7922.972 |
| TPOT_ms p50 | 150.301 |
| cached/prompt | 5632 / 42628 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 4 |
| token_weighted_hit | 0.132 |
| per_req_hit p50/p90 | 0.112 / 0.226 |
| TTFT_ms p50/p90 | 6123.687 / 7922.972 |
| TPOT_ms p50 | 150.301 |
| cached/prompt | 5632 / 42628 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 0 |
| token_weighted_hit | — |
| per_req_hit p50/p90 | — / — |
| TTFT_ms p50/p90 | — / — |
| TPOT_ms p50 | — |
| cached/prompt | 0 / 0 |

## Request

| metric | value |
|---|---|
| n | 4 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 388.147 / 469.517 |
| TPOT_ms p50 | 89.120 |
| cached/prompt | 0 / 23 |

## Request turn0

| metric | value |
|---|---|
| n | 4 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 388.147 / 469.517 |
| TPOT_ms p50 | 89.120 |
| cached/prompt | 0 / 23 |
