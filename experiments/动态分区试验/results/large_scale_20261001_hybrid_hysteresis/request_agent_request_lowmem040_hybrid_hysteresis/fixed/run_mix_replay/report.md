# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.444**
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
| TTFT_ms | 585.369 | 5257.220 | 12353.672 | 2008.582 | 1261 |
| TPOT_ms | 315.977 | 636.583 | 897.734 | 355.956 | 1261 |
| e2e_ms | 6701.116 | 16238.923 | 21762.166 | 7703.880 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.863 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.825 |
| cached/prompt | 7692032 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.986 / 1.936 |
| req/s | 3.314 |
| output tok/s | 53.033 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.937 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 459.752 / 692.256 |
| TPOT_ms p50 | 127.314 |
| cached/prompt | 7644928 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 677.231 / 714.012 |
| TPOT_ms p50 | 133.207 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 455.160 / 676.072 |
| TPOT_ms p50 | 127.089 |
| cached/prompt | 7628032 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.062 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 825.206 / 5923.494 |
| TPOT_ms p50 | 354.338 |
| cached/prompt | 47104 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 828.274 / 6374.059 |
| TPOT_ms p50 | 476.590 |
| cached/prompt | 0 / 174542 |
