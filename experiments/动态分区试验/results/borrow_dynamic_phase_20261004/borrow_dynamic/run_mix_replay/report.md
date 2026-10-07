# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.342**
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
| TTFT_ms | 527.488 | 4154.023 | 8006.070 | 1504.623 | 1261 |
| TPOT_ms | 281.627 | 806.257 | 1645.810 | 428.750 | 1261 |
| e2e_ms | 6459.293 | 16412.781 | 31578.328 | 8364.619 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.900 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.652 |
| cached/prompt | 8028160 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.960 / 1.940 |
| req/s | 3.315 |
| output tok/s | 53.047 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.947 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 460.356 / 671.265 |
| TPOT_ms p50 | 131.031 |
| cached/prompt | 7719936 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.212 / 0.346 |
| TTFT_ms p50/p90 | 684.399 / 1239.446 |
| TPOT_ms p50 | 133.369 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.954 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 458.725 / 617.064 |
| TPOT_ms p50 | 130.978 |
| cached/prompt | 7705856 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.405 |
| per_req_hit p50/p90 | 0.000 / 0.635 |
| TTFT_ms p50/p90 | 664.597 / 4498.410 |
| TPOT_ms p50 | 430.048 |
| cached/prompt | 308224 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 600.872 / 5759.072 |
| TPOT_ms p50 | 612.106 |
| cached/prompt | 0 / 174542 |
