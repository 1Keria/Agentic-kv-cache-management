# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **366.592**
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
| TTFT_ms | 1199.932 | 5203.593 | 8940.887 | 2191.749 | 1261 |
| TPOT_ms | 190.110 | 479.612 | 625.240 | 244.495 | 1261 |
| e2e_ms | 4627.903 | 11693.006 | 13064.904 | 6103.668 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.818 |
| per_req_hit p50/p90 | 0.000 / 0.955 |
| cold_miss_rate | 0.767 |
| cached/prompt | 7294208 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.712 / 3532.145 |
| req/s | 3.440 |
| output tok/s | 55.037 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.879 |
| per_req_hit p50/p90 | 0.966 / 0.991 |
| TTFT_ms p50/p90 | 480.262 / 3035.893 |
| TPOT_ms p50 | 133.126 |
| cached/prompt | 7165696 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.069 |
| per_req_hit p50/p90 | 0.000 / 0.222 |
| TTFT_ms p50/p90 | 1852.497 / 9238.750 |
| TPOT_ms p50 | 433.862 |
| cached/prompt | 5632 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.887 |
| per_req_hit p50/p90 | 0.969 / 0.991 |
| TTFT_ms p50/p90 | 472.471 / 2826.927 |
| TPOT_ms p50 | 130.943 |
| cached/prompt | 7160064 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.169 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 1688.559 / 6115.658 |
| TPOT_ms p50 | 201.042 |
| cached/prompt | 128512 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 3147.154 / 7272.557 |
| TPOT_ms p50 | 292.377 |
| cached/prompt | 0 / 174542 |
