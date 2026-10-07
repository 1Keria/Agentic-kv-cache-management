# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **353.516**
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
| TTFT_ms | 606.677 | 3224.034 | 8067.604 | 1453.467 | 1261 |
| TPOT_ms | 186.970 | 372.514 | 392.912 | 223.636 | 1261 |
| e2e_ms | 4913.043 | 7212.800 | 10671.428 | 5031.640 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.877 |
| per_req_hit p50/p90 | 0.000 / 0.963 |
| cold_miss_rate | 0.660 |
| cached/prompt | 7816192 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.665 / 1.106 |
| req/s | 3.567 |
| output tok/s | 57.072 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.924 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 456.229 / 2139.243 |
| TPOT_ms p50 | 125.849 |
| cached/prompt | 7535104 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.211 |
| TTFT_ms p50/p90 | 907.111 / 8281.447 |
| TPOT_ms p50 | 390.881 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.933 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 453.130 / 1752.104 |
| TPOT_ms p50 | 125.126 |
| cached/prompt | 7532288 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.369 |
| per_req_hit p50/p90 | 0.000 / 0.610 |
| TTFT_ms p50/p90 | 658.692 / 4356.845 |
| TPOT_ms p50 | 241.318 |
| cached/prompt | 281088 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 699.034 / 7683.338 |
| TPOT_ms p50 | 316.954 |
| cached/prompt | 0 / 174542 |
