# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_reuse_probe_v3`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **44.889**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 16 |
| n_ok | 16 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 301.719 | 2926.515 | 4962.433 | 1019.478 | 16 |
| TPOT_ms | 111.139 | 112.829 | 116.547 | 111.613 | 16 |
| e2e_ms | 2081.514 | 4731.106 | 6827.191 | 2805.282 | 16 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.744 |
| per_req_hit p50/p90 | 0.987 / 0.996 |
| cold_miss_rate | 0.250 |
| cached/prompt | 208896 / 280880 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.092 / 0.092 |
| req/s | 0.356 |
| output tok/s | 5.703 |

## Request

| metric | value |
|---|---|
| n | 16 |
| token_weighted_hit | 0.744 |
| per_req_hit p50/p90 | 0.987 / 0.996 |
| TTFT_ms p50/p90 | 301.719 / 2926.515 |
| TPOT_ms p50 | 111.139 |
| cached/prompt | 208896 / 280880 |

## Request turn0

| metric | value |
|---|---|
| n | 1 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 5291.548 / 5291.548 |
| TPOT_ms p50 | 117.077 |
| cached/prompt | 0 / 17381 |
