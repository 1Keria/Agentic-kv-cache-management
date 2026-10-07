# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **359.214**
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
| TTFT_ms | 722.615 | 4918.968 | 7072.872 | 1654.280 | 1261 |
| TPOT_ms | 178.221 | 395.192 | 774.352 | 235.199 | 1261 |
| e2e_ms | 4375.918 | 9286.478 | 15238.248 | 5417.468 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.844 |
| per_req_hit p50/p90 | 0.000 / 0.955 |
| cold_miss_rate | 0.709 |
| cached/prompt | 7528704 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.674 / 12.121 |
| req/s | 3.510 |
| output tok/s | 56.167 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.897 |
| per_req_hit p50/p90 | 0.968 / 0.991 |
| TTFT_ms p50/p90 | 478.144 / 2492.740 |
| TPOT_ms p50 | 127.794 |
| cached/prompt | 7319552 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.137 |
| per_req_hit p50/p90 | 0.220 / 0.227 |
| TTFT_ms p50/p90 | 913.387 / 4217.934 |
| TPOT_ms p50 | 248.344 |
| cached/prompt | 11264 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.905 |
| per_req_hit p50/p90 | 0.969 / 0.992 |
| TTFT_ms p50/p90 | 476.739 / 2420.093 |
| TPOT_ms p50 | 127.303 |
| cached/prompt | 7308288 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.275 |
| per_req_hit p50/p90 | 0.000 / 0.498 |
| TTFT_ms p50/p90 | 830.699 / 5137.585 |
| TPOT_ms p50 | 193.887 |
| cached/prompt | 209152 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1266.284 / 5256.773 |
| TPOT_ms p50 | 231.424 |
| cached/prompt | 0 / 174542 |
