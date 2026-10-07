# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **347.394**
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
| TTFT_ms | 630.378 | 3208.181 | 5971.448 | 1291.871 | 1261 |
| TPOT_ms | 152.896 | 309.437 | 392.569 | 192.578 | 1261 |
| e2e_ms | 3968.031 | 7541.085 | 9133.355 | 4373.120 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.897 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.640 |
| cached/prompt | 8002560 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.716 / 1188.171 |
| req/s | 3.630 |
| output tok/s | 58.078 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 442.917 / 1473.127 |
| TPOT_ms p50 | 127.488 |
| cached/prompt | 7709184 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 829.332 / 4167.157 |
| TPOT_ms p50 | 288.253 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.953 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 440.139 / 1021.596 |
| TPOT_ms p50 | 127.296 |
| cached/prompt | 7692288 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.385 |
| per_req_hit p50/p90 | 0.000 / 0.625 |
| TTFT_ms p50/p90 | 685.304 / 3354.090 |
| TPOT_ms p50 | 166.149 |
| cached/prompt | 293376 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 698.044 / 3536.560 |
| TPOT_ms p50 | 214.611 |
| cached/prompt | 0 / 174542 |
