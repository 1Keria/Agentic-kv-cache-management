# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/scan_mixed_256`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **113.917**
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
| TTFT_ms | 9872.212 | 21605.861 | 21769.707 | 10915.863 | 256 |
| TPOT_ms | 137.582 | 414.139 | 490.128 | 204.872 | 256 |
| e2e_ms | 12905.007 | 23550.742 | 23571.864 | 14193.816 | 256 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.395 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| cold_miss_rate | 0.910 |
| cached/prompt | 369408 / 934029 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 409.782 / 495.055 |
| req/s | 2.247 |
| output tok/s | 35.956 |

## OpenHands

| metric | value |
|---|---|
| n | 42 |
| token_weighted_hit | 0.469 |
| per_req_hit p50/p90 | 0.125 / 0.977 |
| TTFT_ms p50/p90 | 4009.596 / 8444.928 |
| TPOT_ms p50 | 144.651 |
| cached/prompt | 369408 / 787177 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 3 |
| token_weighted_hit | 0.094 |
| per_req_hit p50/p90 | 0.000 / 0.422 |
| TTFT_ms p50/p90 | 5539.933 / 18096.991 |
| TPOT_ms p50 | 341.420 |
| cached/prompt | 2816 / 30106 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 39 |
| token_weighted_hit | 0.484 |
| per_req_hit p50/p90 | 0.127 / 0.977 |
| TTFT_ms p50/p90 | 3253.452 / 7594.564 |
| TPOT_ms p50 | 142.881 |
| cached/prompt | 366592 / 757071 |

## Request

| metric | value |
|---|---|
| n | 214 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 11932.942 / 21639.510 |
| TPOT_ms p50 | 137.515 |
| cached/prompt | 0 / 146852 |

## Request turn0

| metric | value |
|---|---|
| n | 116 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 16129.960 / 21762.859 |
| TPOT_ms p50 | 129.375 |
| cached/prompt | 0 / 30741 |
