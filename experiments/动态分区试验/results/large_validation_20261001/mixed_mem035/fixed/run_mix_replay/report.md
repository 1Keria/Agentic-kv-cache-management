# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **615.958**
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
| TTFT_ms | 13252.504 | 20860.161 | 23706.441 | 12873.161 | 1261 |
| TPOT_ms | 142.338 | 277.930 | 451.811 | 173.611 | 1261 |
| e2e_ms | 16335.831 | 23327.704 | 26936.022 | 15650.938 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.350 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.948 |
| cached/prompt | 3120640 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.625 / 1.049 |
| req/s | 2.047 |
| output tok/s | 32.755 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.383 |
| per_req_hit p50/p90 | 0.000 / 0.982 |
| TTFT_ms p50/p90 | 4465.846 / 16980.679 |
| TPOT_ms p50 | 152.378 |
| cached/prompt | 3120640 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.092 |
| TTFT_ms p50/p90 | 9396.069 / 15779.154 |
| TPOT_ms p50 | 158.420 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.386 |
| per_req_hit p50/p90 | 0.000 / 0.983 |
| TTFT_ms p50/p90 | 4221.963 / 17127.687 |
| TPOT_ms p50 | 152.311 |
| cached/prompt | 3117824 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 14503.419 / 20995.307 |
| TPOT_ms p50 | 142.206 |
| cached/prompt | 0 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 15795.594 / 21000.768 |
| TPOT_ms p50 | 142.505 |
| cached/prompt | 0 / 174542 |
