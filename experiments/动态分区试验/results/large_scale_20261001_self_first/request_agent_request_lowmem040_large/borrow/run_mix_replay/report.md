# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **381.233**
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
| TTFT_ms | 795.815 | 5956.845 | 7754.527 | 2069.579 | 1261 |
| TPOT_ms | 289.785 | 604.450 | 1001.004 | 341.917 | 1261 |
| e2e_ms | 7284.767 | 14069.361 | 21704.223 | 7540.245 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.851 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.772 |
| cached/prompt | 7584768 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.910 / 1.881 |
| req/s | 3.308 |
| output tok/s | 52.923 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.912 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 472.989 / 792.581 |
| TPOT_ms p50 | 126.531 |
| cached/prompt | 7434240 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 646.140 / 2076.407 |
| TPOT_ms p50 | 119.160 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.919 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 471.398 / 788.990 |
| TPOT_ms p50 | 126.547 |
| cached/prompt | 7417344 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.198 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1285.837 / 6251.226 |
| TPOT_ms p50 | 349.090 |
| cached/prompt | 150528 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1876.405 / 5662.866 |
| TPOT_ms p50 | 471.028 |
| cached/prompt | 0 / 174542 |
