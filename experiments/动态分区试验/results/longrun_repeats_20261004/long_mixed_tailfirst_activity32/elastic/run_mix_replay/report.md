# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **344.315**
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
| TTFT_ms | 662.295 | 3007.139 | 5216.386 | 1150.918 | 1261 |
| TPOT_ms | 142.710 | 268.393 | 318.190 | 172.207 | 1261 |
| e2e_ms | 3548.717 | 5901.614 | 7645.802 | 3906.223 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.905 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.638 |
| cached/prompt | 8072448 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.705 / 33.083 |
| req/s | 3.662 |
| output tok/s | 58.597 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.952 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 467.273 / 2246.344 |
| TPOT_ms p50 | 125.217 |
| cached/prompt | 7763712 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 988.262 / 3812.596 |
| TPOT_ms p50 | 238.820 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.960 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 463.303 / 2233.313 |
| TPOT_ms p50 | 124.719 |
| cached/prompt | 7746816 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.405 |
| per_req_hit p50/p90 | 0.000 / 0.626 |
| TTFT_ms p50/p90 | 706.067 / 3143.192 |
| TPOT_ms p50 | 149.930 |
| cached/prompt | 308736 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 773.127 / 3348.694 |
| TPOT_ms p50 | 190.897 |
| cached/prompt | 0 / 174542 |
