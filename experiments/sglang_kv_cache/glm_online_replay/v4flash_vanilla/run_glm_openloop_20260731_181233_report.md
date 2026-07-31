# GLM online open-loop replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- scale_factor: **0.02**
- time_in_secs: **1200.0**
- wall_clock_s: **1200.1**
- dataset: `third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl`

## Integrity

| metric | value |
|---|---|
| n_issued | 329 |
| n_ok | 329 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 1055.497 | 1929.588 | 3738.484 | 1194.851 | 329 |
| TPOT_ms | 7.805 | 22.178 | 101.513 | 15.174 | 329 |
| e2e_ms | 2110.167 | 4801.413 | 7599.818 | 2598.268 | 329 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.191 |
| per_req_hit p50/p90 | 0.154 / 0.403 |
| cold_miss_rate | 0.292 |
| cached/prompt | 1477376 / 7751589 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 | 1.474 / 6.390 |
| req/s | 0.274 |
| output tok/s | 33.066 |
