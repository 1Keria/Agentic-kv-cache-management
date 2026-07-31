# GLM online open-loop replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- scale_factor: **0.02**
- time_in_secs: **600.0**
- wall_clock_s: **600.012**
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
| TTFT_ms | 978.018 | 1661.847 | 2747.805 | 1093.507 | 152 |
| TPOT_ms | 7.793 | 19.635 | 83.160 | 15.449 | 152 |
| e2e_ms | 1921.775 | 4480.962 | 6436.995 | 2379.293 | 152 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.212 |
| per_req_hit p50/p90 | 0.179 / 0.422 |
| cold_miss_rate | 0.316 |
| cached/prompt | 755712 / 3566340 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 | 1.371 / 7.034 |
| req/s | 0.253 |
| output tok/s | 28.849 |
