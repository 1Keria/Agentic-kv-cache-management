# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.737**
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
| TTFT_ms | 690.122 | 6116.052 | 9382.182 | 2213.691 | 1261 |
| TPOT_ms | 350.924 | 624.900 | 849.502 | 350.214 | 1261 |
| e2e_ms | 6931.380 | 15506.273 | 19735.112 | 7817.114 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.868 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.822 |
| cached/prompt | 7736064 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.948 / 1.974 |
| req/s | 3.312 |
| output tok/s | 52.992 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.942 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 448.181 / 663.136 |
| TPOT_ms p50 | 128.837 |
| cached/prompt | 7681280 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 635.313 / 757.099 |
| TPOT_ms p50 | 139.472 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.949 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 445.706 / 629.983 |
| TPOT_ms p50 | 128.774 |
| cached/prompt | 7664384 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.072 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1192.053 / 6524.381 |
| TPOT_ms p50 | 388.431 |
| cached/prompt | 54784 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1732.738 / 6371.149 |
| TPOT_ms p50 | 470.887 |
| cached/prompt | 0 / 174542 |
