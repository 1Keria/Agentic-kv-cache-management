# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **344.191**
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
| TTFT_ms | 659.772 | 3128.236 | 5049.362 | 1386.376 | 1261 |
| TPOT_ms | 144.606 | 260.626 | 472.531 | 168.675 | 1261 |
| e2e_ms | 3655.822 | 6537.944 | 8214.106 | 4085.175 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.896 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.650 |
| cached/prompt | 7989248 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.637 / 1.063 |
| req/s | 3.664 |
| output tok/s | 58.619 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.946 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 450.578 / 2370.567 |
| TPOT_ms p50 | 126.000 |
| cached/prompt | 7713280 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 2370.567 / 5269.042 |
| TPOT_ms p50 | 201.472 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.953 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 447.803 / 2256.359 |
| TPOT_ms p50 | 125.303 |
| cached/prompt | 7696384 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.362 |
| per_req_hit p50/p90 | 0.000 / 0.610 |
| TTFT_ms p50/p90 | 751.028 / 3335.189 |
| TPOT_ms p50 | 150.690 |
| cached/prompt | 275968 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 2000.139 / 4614.934 |
| TPOT_ms p50 | 160.635 |
| cached/prompt | 0 / 174542 |
