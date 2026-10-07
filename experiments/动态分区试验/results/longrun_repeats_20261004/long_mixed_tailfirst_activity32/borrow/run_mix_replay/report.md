# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **346.555**
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
| TTFT_ms | 657.132 | 2854.629 | 5203.759 | 1213.782 | 1261 |
| TPOT_ms | 139.349 | 251.939 | 340.145 | 164.334 | 1261 |
| e2e_ms | 3326.987 | 6314.599 | 9108.081 | 3843.126 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.902 |
| per_req_hit p50/p90 | 0.000 / 0.964 |
| cold_miss_rate | 0.631 |
| cached/prompt | 8045568 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.677 / 19.990 |
| req/s | 3.639 |
| output tok/s | 58.219 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.947 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 467.350 / 1748.525 |
| TPOT_ms p50 | 130.245 |
| cached/prompt | 7721472 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.206 |
| per_req_hit p50/p90 | 0.220 / 0.227 |
| TTFT_ms p50/p90 | 801.599 / 3533.071 |
| TPOT_ms p50 | 234.426 |
| cached/prompt | 16896 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.954 |
| per_req_hit p50/p90 | 0.971 / 0.992 |
| TTFT_ms p50/p90 | 464.446 / 1593.082 |
| TPOT_ms p50 | 129.548 |
| cached/prompt | 7704576 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.426 |
| per_req_hit p50/p90 | 0.000 / 0.635 |
| TTFT_ms p50/p90 | 723.175 / 2863.827 |
| TPOT_ms p50 | 141.879 |
| cached/prompt | 324096 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 694.959 / 3093.874 |
| TPOT_ms p50 | 174.189 |
| cached/prompt | 0 / 174542 |
