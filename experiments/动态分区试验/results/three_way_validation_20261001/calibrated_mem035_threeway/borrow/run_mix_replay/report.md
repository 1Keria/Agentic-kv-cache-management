# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/bidirectional_reuse_calibrated`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **570.838**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 1277 |
| n_ok | 1277 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 12574.879 | 16944.218 | 21494.458 | 11580.430 | 1277 |
| TPOT_ms | 145.572 | 357.694 | 926.751 | 205.084 | 1277 |
| e2e_ms | 15193.436 | 21842.044 | 25274.367 | 14861.776 | 1277 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.466 |
| per_req_hit p50/p90 | 0.000 / 0.102 |
| cold_miss_rate | 0.872 |
| cached/prompt | 4283392 / 9195538 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 1.011 / 1.918 |
| req/s | 2.237 |
| output tok/s | 35.793 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.525 |
| per_req_hit p50/p90 | 0.127 / 0.988 |
| TTFT_ms p50/p90 | 6162.248 / 11125.966 |
| TPOT_ms p50 | 133.001 |
| cached/prompt | 4283392 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 10888.960 / 13176.446 |
| TPOT_ms p50 | 140.639 |
| cached/prompt | 0 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.531 |
| per_req_hit p50/p90 | 0.130 / 0.989 |
| TTFT_ms p50/p90 | 6128.827 / 10950.878 |
| TPOT_ms p50 | 131.663 |
| cached/prompt | 4283392 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1066 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13096.549 / 17285.387 |
| TPOT_ms p50 | 147.743 |
| cached/prompt | 0 / 1039706 |

## Request turn0

| metric | value |
|---|---|
| n | 552 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 13523.398 / 17324.016 |
| TPOT_ms p50 | 172.192 |
| cached/prompt | 0 / 243357 |
