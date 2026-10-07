# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **356.47**
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
| TTFT_ms | 779.662 | 3654.990 | 8766.560 | 1824.129 | 1261 |
| TPOT_ms | 178.919 | 496.019 | 620.153 | 229.191 | 1261 |
| e2e_ms | 3961.416 | 11267.181 | 16680.680 | 5491.179 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.845 |
| per_req_hit p50/p90 | 0.000 / 0.961 |
| cold_miss_rate | 0.825 |
| cached/prompt | 7533568 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.686 / 569.261 |
| req/s | 3.538 |
| output tok/s | 56.599 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.919 |
| per_req_hit p50/p90 | 0.969 / 0.991 |
| TTFT_ms p50/p90 | 476.934 / 2420.042 |
| TPOT_ms p50 | 134.284 |
| cached/prompt | 7494400 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.227 |
| TTFT_ms p50/p90 | 860.852 / 6883.914 |
| TPOT_ms p50 | 251.802 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.928 |
| per_req_hit p50/p90 | 0.970 / 0.992 |
| TTFT_ms p50/p90 | 475.293 / 2356.799 |
| TPOT_ms p50 | 132.755 |
| cached/prompt | 7488768 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.051 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 933.032 / 3904.712 |
| TPOT_ms p50 | 183.822 |
| cached/prompt | 39168 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1604.370 / 6398.579 |
| TPOT_ms p50 | 227.159 |
| cached/prompt | 0 / 174542 |
