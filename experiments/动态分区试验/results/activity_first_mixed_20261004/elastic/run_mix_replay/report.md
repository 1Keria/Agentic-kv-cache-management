# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **347.066**
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
| TTFT_ms | 635.649 | 3100.122 | 4677.845 | 1263.206 | 1261 |
| TPOT_ms | 148.556 | 282.870 | 400.602 | 179.914 | 1261 |
| e2e_ms | 3654.147 | 6608.818 | 7731.607 | 4141.822 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.904 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.638 |
| cached/prompt | 8061440 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.661 / 1.157 |
| req/s | 3.633 |
| output tok/s | 58.133 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.951 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 451.535 / 1148.638 |
| TPOT_ms p50 | 131.182 |
| cached/prompt | 7757056 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.212 / 0.225 |
| TTFT_ms p50/p90 | 853.588 / 3030.261 |
| TPOT_ms p50 | 287.302 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.959 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 445.391 / 1032.616 |
| TPOT_ms p50 | 129.625 |
| cached/prompt | 7742976 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.400 |
| per_req_hit p50/p90 | 0.000 / 0.626 |
| TTFT_ms p50/p90 | 703.672 / 3128.243 |
| TPOT_ms p50 | 157.720 |
| cached/prompt | 304384 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 837.594 / 3204.009 |
| TPOT_ms p50 | 199.522 |
| cached/prompt | 0 / 174542 |
