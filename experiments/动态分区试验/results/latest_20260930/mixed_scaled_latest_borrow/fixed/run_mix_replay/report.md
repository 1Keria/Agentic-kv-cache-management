# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **366.731**
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
| TTFT_ms | 651.079 | 4099.134 | 5062.442 | 1452.701 | 1261 |
| TPOT_ms | 155.480 | 366.714 | 466.205 | 205.715 | 1261 |
| e2e_ms | 4548.176 | 7354.887 | 9088.713 | 4744.135 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.840 |
| per_req_hit p50/p90 | 0.000 / 0.963 |
| cold_miss_rate | 0.655 |
| cached/prompt | 7494656 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.613 / 1.066 |
| req/s | 3.438 |
| output tok/s | 55.016 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.882 |
| per_req_hit p50/p90 | 0.970 / 0.991 |
| TTFT_ms p50/p90 | 463.248 / 2747.584 |
| TPOT_ms p50 | 125.380 |
| cached/prompt | 7189504 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.034 |
| per_req_hit p50/p90 | 0.000 / 0.211 |
| TTFT_ms p50/p90 | 913.067 / 3162.696 |
| TPOT_ms p50 | 289.862 |
| cached/prompt | 2816 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.890 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 456.889 / 2667.753 |
| TPOT_ms p50 | 125.252 |
| cached/prompt | 7186688 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.401 |
| per_req_hit p50/p90 | 0.000 / 0.626 |
| TTFT_ms p50/p90 | 703.876 / 4318.563 |
| TPOT_ms p50 | 165.630 |
| cached/prompt | 305152 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 753.759 / 4643.759 |
| TPOT_ms p50 | 248.162 |
| cached/prompt | 0 / 174542 |
