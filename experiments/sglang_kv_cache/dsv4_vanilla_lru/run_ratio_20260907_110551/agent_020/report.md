# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/share/dai-sys/zhoulongsheng/agentkv/workloads/ratio_sweep_v4flash_unseen/agent_020`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **11532.476**
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
| TTFT_ms | 308.840 | 841.460 | 2723.977 | 444.702 | 2000 |
| TPOT_ms | 13.729 | 53.604 | 424.724 | 37.033 | 2000 |
| e2e_ms | 5204.164 | 15406.478 | 24447.849 | 6964.918 | 2000 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.887 |
| per_req_hit p50/p90 | 0.000 / 0.978 |
| cold_miss_rate | 0.641 |
| cached/prompt | 15043584 / 16951525 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.692 / 1.186 |
| req/s | 0.173 |
| output tok/s | 65.689 |

## OpenHands

| metric | value |
|---|---|
| n | 400 |
| token_weighted_hit | 0.939 |
| per_req_hit p50/p90 | 0.979 / 0.994 |
| TTFT_ms p50/p90 | 324.533 / 784.156 |
| TPOT_ms p50 | 8.145 |
| cached/prompt | 14609664 / 15564682 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 17 |
| token_weighted_hit | 0.077 |
| per_req_hit p50/p90 | 0.067 / 0.519 |
| TTFT_ms p50/p90 | 2000.532 / 3088.085 |
| TPOT_ms p50 | 50.197 |
| cached/prompt | 25344 / 329902 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 383 |
| token_weighted_hit | 0.957 |
| per_req_hit p50/p90 | 0.980 / 0.994 |
| TTFT_ms p50/p90 | 320.501 / 627.196 |
| TPOT_ms p50 | 8.058 |
| cached/prompt | 14584320 / 15234780 |

## Request

| metric | value |
|---|---|
| n | 1600 |
| token_weighted_hit | 0.313 |
| per_req_hit p50/p90 | 0.000 / 0.609 |
| TTFT_ms p50/p90 | 303.127 / 872.673 |
| TPOT_ms p50 | 17.017 |
| cached/prompt | 433920 / 1386843 |

## Request turn0

| metric | value |
|---|---|
| n | 801 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 380.270 / 1713.576 |
| TPOT_ms p50 | 29.474 |
| cached/prompt | 0 / 329101 |
