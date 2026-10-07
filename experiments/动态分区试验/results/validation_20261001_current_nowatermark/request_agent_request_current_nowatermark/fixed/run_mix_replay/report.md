# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **380.581**
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
| TTFT_ms | 550.703 | 3880.781 | 7284.980 | 1451.007 | 1261 |
| TPOT_ms | 321.294 | 813.151 | 1637.736 | 455.426 | 1261 |
| e2e_ms | 6767.361 | 16549.836 | 30578.950 | 8737.816 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.873 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.778 |
| cached/prompt | 7783936 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.844 / 1.904 |
| req/s | 3.313 |
| output tok/s | 53.014 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.937 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 473.568 / 678.466 |
| TPOT_ms p50 | 126.862 |
| cached/prompt | 7644928 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 672.676 / 925.224 |
| TPOT_ms p50 | 130.247 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 471.071 / 664.256 |
| TPOT_ms p50 | 126.808 |
| cached/prompt | 7628032 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.183 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 773.035 / 4135.377 |
| TPOT_ms p50 | 484.890 |
| cached/prompt | 139008 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 487.069 / 4465.218 |
| TPOT_ms p50 | 682.903 |
| cached/prompt | 0 / 174542 |
