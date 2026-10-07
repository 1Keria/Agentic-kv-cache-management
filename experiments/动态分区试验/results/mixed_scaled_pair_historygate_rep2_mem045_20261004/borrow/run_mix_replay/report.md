# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **348.517**
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
| TTFT_ms | 575.668 | 3224.001 | 4982.141 | 1211.861 | 1261 |
| TPOT_ms | 149.927 | 327.854 | 379.774 | 184.760 | 1261 |
| e2e_ms | 3774.178 | 6430.293 | 7613.614 | 4168.023 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.898 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.643 |
| cached/prompt | 8012032 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.618 / 1.071 |
| req/s | 3.618 |
| output tok/s | 57.891 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.946 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 456.503 / 2254.144 |
| TPOT_ms p50 | 129.425 |
| cached/prompt | 7713536 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.171 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 850.609 / 3193.531 |
| TPOT_ms p50 | 289.574 |
| cached/prompt | 14080 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.954 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 451.039 / 2235.960 |
| TPOT_ms p50 | 128.899 |
| cached/prompt | 7699456 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.392 |
| per_req_hit p50/p90 | 0.000 / 0.620 |
| TTFT_ms p50/p90 | 627.712 / 3266.512 |
| TPOT_ms p50 | 154.593 |
| cached/prompt | 298496 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 662.239 / 4733.115 |
| TPOT_ms p50 | 209.403 |
| cached/prompt | 0 / 174542 |
