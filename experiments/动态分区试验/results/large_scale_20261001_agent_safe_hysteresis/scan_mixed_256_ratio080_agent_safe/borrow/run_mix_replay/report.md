# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **81.171**
- dry_run: False

## Integrity

| metric | value |
|---|---|
| n_issued | 256 |
| n_ok | 256 |
| n_err | 0 |
| error_breakdown | `{}` |

## Latency (ok)

| metric | p50 | p90 | p99 | mean | count |
|---|---:|---:|---:|---:|---:|
| TTFT_ms | 2845.886 | 8744.186 | 10538.876 | 3433.209 | 256 |
| TPOT_ms | 142.414 | 394.421 | 403.395 | 221.114 | 256 |
| e2e_ms | 5806.227 | 12815.735 | 15071.040 | 6971.039 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.784 |
| per_req_hit p50/p90 | 0.000 / 0.912 |
| cold_miss_rate | 0.711 |
| cached/prompt | 732416 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 4477.885 / 4563.053 |
| req/s | 3.154 |
| output tok/s | 50.461 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.878 |
| per_req_hit p50/p90 | 0.941 / 0.987 |
| TTFT_ms p50/p90 | 2313.010 / 4710.738 |
| TPOT_ms p50 | 124.044 |
| cached/prompt | 691200 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.187 |
| per_req_hit p50/p90 | 0.226 / 0.228 |
| TTFT_ms p50/p90 | 10019.333 / 14136.167 |
| TPOT_ms p50 | 315.174 |
| cached/prompt | 5632 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.906 |
| per_req_hit p50/p90 | 0.955 / 0.987 |
| TTFT_ms p50/p90 | 2303.226 / 3965.799 |
| TPOT_ms p50 | 121.926 |
| cached/prompt | 685568 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.281 |
| per_req_hit p50/p90 | 0.000 / 0.399 |
| TTFT_ms p50/p90 | 2913.930 / 10016.874 |
| TPOT_ms p50 | 143.152 |
| cached/prompt | 41216 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3371.729 / 10022.327 |
| TPOT_ms p50 | 371.166 |
| cached/prompt | 0 / 30741 |
