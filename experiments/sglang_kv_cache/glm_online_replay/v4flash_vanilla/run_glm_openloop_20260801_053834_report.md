# GLM online open-loop replay report

- model: `glm-5.1-fp8`
- base_url: `http://127.0.0.1:30000`
- scale_factor: **0.02**
- time_in_secs: **3600.0**
- wall_clock_s: **3600.105**
- dataset: `third_party/glm-5dot1_onlinedata/glm-5dot1_onlinedata_lt32k.jsonl`

## Integrity

| metric | value |
|---|---|
| n_issued | 620 |
| n_ok | 620 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 2702.774 | 7425.755 | 18519.911 | 3680.150 | 620 |
| TPOT_ms | 25.670 | 78.045 | 191.780 | 41.109 | 620 |
| e2e_ms | 6660.039 | 21481.349 | 43234.185 | 9615.084 | 620 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.347 |
| per_req_hit p50/p90 | 0.268 / 0.797 |
| cold_miss_rate | 0.245 |
| cached/prompt | 4862912 / 14017429 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 | 1.112 / 4.943 |
| req/s | 0.172 |
| output tok/s | 24.130 |


