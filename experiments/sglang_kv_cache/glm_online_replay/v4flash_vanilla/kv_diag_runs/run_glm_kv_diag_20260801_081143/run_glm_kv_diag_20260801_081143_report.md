# GLM online open-loop replay report

- model: `glm-5.1-fp8`
- base_url: `http://127.0.0.1:30000`
- scale_factor: **0.02**
- time_in_secs: **600.0**
- wall_clock_s: **600.006**
- dataset: `third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl`

## Integrity

| metric | value |
|---|---|
| n_issued | 152 |
| n_ok | 152 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 2558.456 | 6402.955 | 10992.567 | 3283.873 | 152 |
| TPOT_ms | 25.919 | 80.227 | 190.511 | 43.564 | 152 |
| e2e_ms | 6985.358 | 18808.798 | 44558.365 | 9649.066 | 152 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.384 |
| per_req_hit p50/p90 | 0.387 / 0.812 |
| cold_miss_rate | 0.257 |
| cached/prompt | 1337152 / 3485374 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 | 1.104 / 3.108 |
| req/s | 0.253 |
| output tok/s | 38.738 |
