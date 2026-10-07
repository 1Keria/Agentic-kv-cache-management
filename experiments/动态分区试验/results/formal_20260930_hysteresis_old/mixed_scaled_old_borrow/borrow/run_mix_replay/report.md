# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **348.251**
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
| TTFT_ms | 678.602 | 2899.005 | 4249.598 | 1160.307 | 1261 |
| TPOT_ms | 147.459 | 281.475 | 375.141 | 181.735 | 1261 |
| e2e_ms | 4064.744 | 6001.507 | 6836.894 | 4068.070 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.889 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.642 |
| cached/prompt | 7928064 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.614 / 1.069 |
| req/s | 3.621 |
| output tok/s | 57.935 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.935 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 462.820 / 2221.375 |
| TPOT_ms p50 | 125.693 |
| cached/prompt | 7625472 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.090 |
| TTFT_ms p50/p90 | 1378.194 / 3209.969 |
| TPOT_ms p50 | 206.177 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.944 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 458.187 / 2175.778 |
| TPOT_ms p50 | 124.052 |
| cached/prompt | 7622656 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.397 |
| per_req_hit p50/p90 | 0.000 / 0.624 |
| TTFT_ms p50/p90 | 765.134 / 2918.833 |
| TPOT_ms p50 | 159.317 |
| cached/prompt | 302592 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 940.555 / 2905.686 |
| TPOT_ms p50 | 192.808 |
| cached/prompt | 0 / 174542 |
