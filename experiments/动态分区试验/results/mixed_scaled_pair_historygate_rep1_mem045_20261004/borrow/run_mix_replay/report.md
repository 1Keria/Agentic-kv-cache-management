# Mix workload replay report

- model: `deepseek-v4-flash`
- base_url: `http://127.0.0.1:30000`
- workload: `/mnt/dai-sys/zhoulongsheng/agentkv/experiments/动态分区试验/data/mixed_scaled`
- arrival: `frozen`
- request_gap_cap_s: None
- wall_clock_s: **350.031**
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
| TTFT_ms | 603.813 | 3393.537 | 4316.265 | 1262.444 | 1261 |
| TPOT_ms | 155.130 | 293.139 | 400.312 | 182.491 | 1261 |
| e2e_ms | 4146.011 | 6191.779 | 8018.770 | 4182.308 | 1261 |

## KV

| metric | value |
|---|---|
| token_weighted_hit | 0.890 |
| per_req_hit p50/p90 | 0.000 / 0.965 |
| cold_miss_rate | 0.642 |
| cached/prompt | 7938816 / 8917410 |

## Schedule / throughput

| metric | value |
|---|---|
| s_time_drift_ms p50/p90 (session start) | 0.663 / 28.742 |
| req/s | 3.603 |
| output tok/s | 57.641 |

## OpenHands

| metric | value |
|---|---|
| n | 211 |
| token_weighted_hit | 0.937 |
| per_req_hit p50/p90 | 0.971 / 0.991 |
| TTFT_ms p50/p90 | 472.662 / 2303.606 |
| TPOT_ms p50 | 126.554 |
| cached/prompt | 7642368 / 8155832 |

## OpenHands turn0

| metric | value |
|---|---|
| n | 7 |
| token_weighted_hit | 0.137 |
| per_req_hit p50/p90 | 0.211 / 0.225 |
| TTFT_ms p50/p90 | 902.850 / 3573.737 |
| TPOT_ms p50 | 240.086 |
| cached/prompt | 11264 / 82103 |

## OpenHands within-session (turn>=1)

| metric | value |
|---|---|
| n | 204 |
| token_weighted_hit | 0.945 |
| per_req_hit p50/p90 | 0.972 / 0.992 |
| TTFT_ms p50/p90 | 468.009 / 2223.036 |
| TPOT_ms p50 | 126.158 |
| cached/prompt | 7631104 / 8073729 |

## Request

| metric | value |
|---|---|
| n | 1050 |
| token_weighted_hit | 0.389 |
| per_req_hit p50/p90 | 0.000 / 0.615 |
| TTFT_ms p50/p90 | 656.182 / 3447.394 |
| TPOT_ms p50 | 160.589 |
| cached/prompt | 296448 / 761578 |

## Request turn0

| metric | value |
|---|---|
| n | 548 |
| token_weighted_hit | 0.000 |
| per_req_hit p50/p90 | 0.000 / 0.000 |
| TTFT_ms p50/p90 | 739.036 / 3525.115 |
| TPOT_ms p50 | 184.276 |
| cached/prompt | 0 / 174542 |
