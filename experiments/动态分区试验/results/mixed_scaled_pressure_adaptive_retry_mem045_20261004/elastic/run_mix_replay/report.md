# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **349.222**
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
| TTFT_ms | 697.025 | 2798.045 | 5724.187 | 1300.772 | 1261 |
| TPOT_ms | 141.010 | 236.537 | 326.330 | 160.946 | 1261 |
| e2e_ms | 3455.800 | 5732.777 | 7789.363 | 3875.913 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.899 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.638 |
| cached/prompt | 8016384 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.753 / 4254.859 |
| req/s | 3.611 |
| output tok/s | 57.774 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 467.201 / 2356.225 |
| TPOT_ms p50 | 125.608 |
| cached/prompt | 7704064 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 995.901 / 7052.872 |
| TPOT_ms p50 | 223.267 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.952 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 456.542 / 2255.203 |
| TPOT_ms p50 | 125.120 |
| cached/prompt | 7687168 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.410 |
| per_req_hit p50/p90 | 0.000 / 0.626 |
| TTFT_ms p50/p90 | 820.480 / 2808.367 |
| TPOT_ms p50 | 143.486 |
| cached/prompt | 312320 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1260.339 / 3488.323 |
| TPOT_ms p50 | 175.095 |
| cached/prompt | 0 / 174542 |
