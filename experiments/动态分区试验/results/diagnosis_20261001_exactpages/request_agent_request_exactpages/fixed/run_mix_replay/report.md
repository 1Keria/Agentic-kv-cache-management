# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **381.142**
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
| TTFT_ms | 521.210 | 3900.253 | 6710.320 | 1477.971 | 1261 |
| TPOT_ms | 374.448 | 916.003 | 1266.587 | 458.541 | 1261 |
| e2e_ms | 8539.911 | 17108.359 | 26821.652 | 8814.619 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.881 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.791 |
| cached/prompt | 7855104 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.946 / 1.973 |
| req/s | 3.308 |
| output tok/s | 52.936 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.949 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 463.246 / 640.830 |
| TPOT_ms p50 | 128.548 |
| cached/prompt | 7743744 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 725.728 / 2654.830 |
| TPOT_ms p50 | 144.407 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.957 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 461.825 / 622.895 |
| TPOT_ms p50 | 128.531 |
| cached/prompt | 7726848 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.146 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 684.847 / 4164.889 |
| TPOT_ms p50 | 502.299 |
| cached/prompt | 111360 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 501.772 / 4644.799 |
| TPOT_ms p50 | 731.773 |
| cached/prompt | 0 / 174542 |
