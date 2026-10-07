# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.943**
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
| TTFT_ms | 686.681 | 4894.223 | 7649.032 | 1769.191 | 1261 |
| TPOT_ms | 284.488 | 569.704 | 769.483 | 313.905 | 1261 |
| e2e_ms | 6419.993 | 12341.212 | 18241.686 | 6791.678 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.855 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.820 |
| cached/prompt | 7622400 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.921 / 1.955 |
| req/s | 3.310 |
| output tok/s | 52.963 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.927 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 470.248 / 796.780 |
| TPOT_ms p50 | 128.112 |
| cached/prompt | 7557120 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 667.296 / 1190.612 |
| TPOT_ms p50 | 131.853 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.934 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 468.198 / 793.632 |
| TPOT_ms p50 | 127.937 |
| cached/prompt | 7540224 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.086 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 902.158 / 5131.643 |
| TPOT_ms p50 | 335.216 |
| cached/prompt | 65280 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 966.085 / 5202.985 |
| TPOT_ms p50 | 416.467 |
| cached/prompt | 0 / 174542 |
