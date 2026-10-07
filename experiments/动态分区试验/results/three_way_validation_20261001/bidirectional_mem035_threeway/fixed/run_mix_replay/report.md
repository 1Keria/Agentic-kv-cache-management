# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/bidirectional_reuse`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **571.679**
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
| TTFT_ms | 5322.625 | 17490.125 | 21533.602 | 7278.061 | 275 |
| TPOT_ms | 173.179 | 346.985 | 687.685 | 209.490 | 275 |
| e2e_ms | 8632.392 | 21141.533 | 25342.391 | 10629.901 | 275 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.334 |
| per_req_hit p50/p90 | 0.000 / 0.974 |
| cold_miss_rate | 0.753 |
| cached/prompt | 3105536 / 9285414 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.875 / 1.606 |
| req/s | 0.481 |
| output tok/s | 7.697 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.381 |
| per_req_hit p50/p90 | 0.000 / 0.982 |
| TTFT_ms p50/p90 | 3795.916 / 15964.158 |
| TPOT_ms p50 | 169.783 |
| cached/prompt | 3105536 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.217 |
| TTFT_ms p50/p90 | 5099.533 / 11164.664 |
| TPOT_ms p50 | 163.250 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.384 |
| per_req_hit p50/p90 | 0.000 / 0.983 |
| TTFT_ms p50/p90 | 3779.444 / 16544.774 |
| TPOT_ms p50 | 170.798 |
| cached/prompt | 3099904 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 64 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 14378.084 / 18007.928 |
| TPOT_ms p50 | 203.897 |
| cached/prompt | 0 / 1129582 |

## Request turn0

| metric | value |
|---|---|
| n | 16 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 12548.016 / 16128.588 |
| TPOT_ms p50 | 281.184 |
| cached/prompt | 0 / 271218 |
