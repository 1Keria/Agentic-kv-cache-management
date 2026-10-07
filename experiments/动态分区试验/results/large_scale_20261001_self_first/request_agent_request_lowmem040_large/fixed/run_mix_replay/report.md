# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **381.789**
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
| TTFT_ms | 606.178 | 5783.765 | 12031.665 | 2093.963 | 1261 |
| TPOT_ms | 324.325 | 778.288 | 939.768 | 350.987 | 1261 |
| e2e_ms | 6843.524 | 15577.140 | 21512.711 | 7709.750 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.836 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.829 |
| cached/prompt | 7457280 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.882 / 1.921 |
| req/s | 3.303 |
| output tok/s | 52.846 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.909 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 472.119 / 778.712 |
| TPOT_ms p50 | 128.424 |
| cached/prompt | 7411968 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 665.885 / 945.848 |
| TPOT_ms p50 | 125.914 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.916 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 466.284 / 752.555 |
| TPOT_ms p50 | 128.425 |
| cached/prompt | 7395072 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.059 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 791.775 / 6234.242 |
| TPOT_ms p50 | 347.893 |
| cached/prompt | 45312 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 842.867 / 7066.039 |
| TPOT_ms p50 | 435.283 |
| cached/prompt | 0 / 174542 |
