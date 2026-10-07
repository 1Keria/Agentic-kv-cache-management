# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/request_agent_request`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **379.959**
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
| TTFT_ms | 484.764 | 3219.478 | 9413.692 | 1233.577 | 1261 |
| TPOT_ms | 313.409 | 970.242 | 1838.067 | 461.258 | 1261 |
| e2e_ms | 6222.408 | 16696.058 | 33150.702 | 8613.703 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.905 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.653 |
| cached/prompt | 8068352 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.966 / 1.974 |
| req/s | 3.319 |
| output tok/s | 53.100 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.952 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 443.270 / 595.817 |
| TPOT_ms p50 | 128.522 |
| cached/prompt | 7763712 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.346 |
| TTFT_ms p50/p90 | 672.908 / 881.158 |
| TPOT_ms p50 | 152.326 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.960 |
| per_req_hit p50/p90 | 0.973 / 0.992 |
| TTFT_ms p50/p90 | 438.750 / 578.316 |
| TPOT_ms p50 | 128.152 |
| cached/prompt | 7746816 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.400 |
| per_req_hit p50/p90 | 0.000 / 0.627 |
| TTFT_ms p50/p90 | 526.951 / 3442.366 |
| TPOT_ms p50 | 356.817 |
| cached/prompt | 304640 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 410.832 / 4358.644 |
| TPOT_ms p50 | 692.406 |
| cached/prompt | 0 / 174542 |
