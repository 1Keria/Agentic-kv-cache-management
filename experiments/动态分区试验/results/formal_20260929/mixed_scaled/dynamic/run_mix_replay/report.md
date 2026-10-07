# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **352.029**
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
| TTFT_ms | 778.741 | 3436.156 | 5276.955 | 1428.585 | 1261 |
| TPOT_ms | 157.548 | 346.614 | 412.557 | 200.152 | 1261 |
| e2e_ms | 4728.666 | 7029.923 | 7784.462 | 4631.012 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.884 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.643 |
| cached/prompt | 7886080 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.651 / 30.834 |
| req/s | 3.582 |
| output tok/s | 57.313 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.930 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 451.766 / 2156.597 |
| TPOT_ms p50 | 128.776 |
| cached/prompt | 7586816 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.103 |
| per_req_hit p50/p90 | 0.000 / 0.346 |
| TTFT_ms p50/p90 | 915.009 / 4001.996 |
| TPOT_ms p50 | 321.892 |
| cached/prompt | 8448 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.939 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 449.115 / 2010.662 |
| TPOT_ms p50 | 128.154 |
| cached/prompt | 7578368 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.393 |
| per_req_hit p50/p90 | 0.000 / 0.621 |
| TTFT_ms p50/p90 | 860.355 / 3440.738 |
| TPOT_ms p50 | 165.355 |
| cached/prompt | 299264 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2242.816 / 3664.776 |
| TPOT_ms p50 | 270.149 |
| cached/prompt | 0 / 174542 |
