# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.709**
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
| TTFT_ms | 749.403 | 3519.715 | 6390.558 | 1485.708 | 1261 |
| TPOT_ms | 248.201 | 983.092 | 1451.845 | 460.731 | 1261 |
| e2e_ms | 6196.660 | 17959.150 | 28552.389 | 8857.404 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.869 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.735 |
| cached/prompt | 7751936 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.978 / 1.861 |
| req/s | 3.312 |
| output tok/s | 52.996 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.924 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 461.839 / 701.410 |
| TPOT_ms p50 | 127.906 |
| cached/prompt | 7539200 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 677.091 / 1368.742 |
| TPOT_ms p50 | 142.808 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.932 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 458.567 / 631.153 |
| TPOT_ms p50 | 127.857 |
| cached/prompt | 7522304 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.279 |
| per_req_hit p50/p90 | 0.000 / 0.474 |
| TTFT_ms p50/p90 | 1096.103 / 3845.241 |
| TPOT_ms p50 | 526.806 |
| cached/prompt | 212736 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1371.565 / 4805.823 |
| TPOT_ms p50 | 784.871 |
| cached/prompt | 0 / 174542 |
